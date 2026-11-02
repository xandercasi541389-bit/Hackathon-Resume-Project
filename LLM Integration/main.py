"""Command-line demo for the AI integration module.

  python main.py events [--resume PATH] [--live] [--rerank] [--top N] [--json]
  python main.py jobs   [--resume PATH] [--live] [--top N] [--json]
  python main.py interview [--resume PATH] [--job ID] [--type technical|hr|both]
                           [--questions N] [--offline] [--live]
  python main.py demo   [--resume-file PDF|DOCX|TXT] [--fast] [--offline] [--no-pause]

`events` ranks EagleLink events for a resume analysis (the C++ module's JSON).
`jobs` finds the employers named in those events and ranks their (curated, real)
job and internship postings against the resume.
`interview` runs an interactive mock interview (Technical and/or HR) for one of
those postings and prints a feedback report. Type `quit` to stop early.
`demo` runs the whole flow for a presentation: parse a resume file with the C++
parser, then events, jobs and a short interview.
Without --live both read the saved snapshot in fixtures/; with --live they query
EagleLink once (small, cached) and tell you if they have to use the snapshot instead.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import textwrap
from datetime import datetime
from pathlib import Path

from ai import ConfigError, LLMClient, LLMError
from eventsearch import match_events, rerank_with_llm
from eventsearch.eaglelink_client import EagleLinkClient, EventSearchError, load_events_file
from ai.interview_engine import InterviewSession
from integration import CompanyProfile, ValidationError, load_company, load_resume
from jobs import JobDataError, load_jobs, match_jobs

APP_NAME = "Hackathon Resume Project"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
PARSER_DIR = Path(__file__).resolve().parent.parent / "Resume Parser"


def banner(title: str) -> None:
    line = "=" * 40
    print(f"{line}\n{title.center(40)}\n{line}\n")


def warn(message: str) -> None:
    print(f"[warning] {message}", file=sys.stderr)


def load_events(live: bool, snapshot: Path):
    if live:
        try:
            events = EagleLinkClient().career_events()
            return events, "EagleLink (live)"
        except EventSearchError as exc:
            warn(f"Live EagleLink search failed ({exc}); using the saved snapshot instead.")
    return load_events_file(snapshot), f"saved snapshot {snapshot.name}"


def format_when(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).astimezone().strftime("%a %b %d, %I:%M %p")
    except ValueError:
        return iso


def cmd_events(args) -> int:
    try:
        resume = load_resume(args.resume)
    except ValidationError as exc:
        warn(f"Resume JSON is invalid: {exc}")
        return 2
    try:
        events, source = load_events(args.live, args.snapshot)
    except EventSearchError as exc:
        warn(str(exc))
        return 1
    matches = match_events(resume, events, top_n=args.top)

    ranking = "keyword match"
    if args.rerank and matches:
        try:
            matches = rerank_with_llm(LLMClient(), resume, matches)
            ranking = "LLM rerank"
        except (ConfigError, LLMError) as exc:
            warn(f"LLM rerank unavailable ({exc}); showing keyword ranking.")

    if args.json:
        print(json.dumps({"source": source, "ranking": ranking,
                          "matches": [m.to_dict() for m in matches]}, indent=2))
        return 0

    banner(APP_NAME)
    print(f"Resume: {args.resume}\nEvents: {len(events)} from {source}\nRanking: {ranking}\n")
    if not matches:
        print("No matching events found.")
    for i, m in enumerate(matches, 1):
        e = m.event
        print(f"{i}. {e.name}  (score {m.score:g})")
        print(f"   {format_when(e.starts_on)} | {e.location or 'location TBA'}")
        if e.organization:
            print(f"   Host: {e.organization}")
        for reason in m.reasons:
            print(f"   - {reason}")
        print(f"   {e.url}\n")
    return 0


def load_company_profiles(folder: Path = FIXTURES / "companies") -> dict:
    """Company research profiles keyed by lowercase company name."""
    profiles = {}
    for path in sorted(folder.glob("*.json")):
        try:
            profile = load_company(path)
        except ValidationError as exc:
            warn(f"Skipping company profile {path.name}: {exc}")
            continue
        profiles[profile.company_name.lower()] = profile
    return profiles


def employers_in_events(events, names) -> list[str]:
    """Known employer names mentioned in event titles, descriptions or hosts."""
    found = []
    for name in names:
        needle = name.lower()
        if any(needle in f"{e.name} {e.description_text} {e.organization}".lower() for e in events):
            found.append(name)
    return found


def find_jobs(resume, live: bool, snapshot: Path, top_n: int):
    """Events -> employers in them -> ranked postings. Returns (matches, employers, source)."""
    events, source = load_events(live, snapshot)
    # Use every resume-relevant career event, not just the few shown by `events`.
    relevant = [m.event for m in match_events(resume, events, top_n=len(events))]
    jobs = load_jobs(FIXTURES / "jobs.json")
    names = sorted({j.company for j in jobs} | {p.company_name for p in load_company_profiles().values()})
    employers = employers_in_events(relevant, names)
    if not employers:
        warn("No known employers found in the current events; showing all curated postings.")
    return match_jobs(resume, jobs, companies=employers or None, top_n=top_n), employers, source


def cmd_jobs(args) -> int:
    try:
        resume = load_resume(args.resume)
    except ValidationError as exc:
        warn(f"Resume JSON is invalid: {exc}")
        return 2
    try:
        matches, employers, source = find_jobs(resume, args.live, args.snapshot, args.top)
    except (EventSearchError, JobDataError) as exc:
        warn(str(exc))
        return 1

    if args.json:
        print(json.dumps({"source": source, "employers": employers,
                          "matches": [m.to_dict() for m in matches]}, indent=2))
        return 0

    banner(APP_NAME)
    print(f"Resume: {args.resume}\nEvents: {source}")
    print(f"Employers at matching events: {', '.join(employers) or 'none found'}\n")
    if not matches:
        print("No matching postings found.")
    for i, m in enumerate(matches, 1):
        j = m.job
        kind = f" ({j.type})" if j.type else ""
        print(f"{i}. {j.title}{kind} - {j.company}  [{m.skill_match_percent:g}% skill match]")
        if j.location:
            print(f"   {j.location}")
        if m.matched_skills:
            print(f"   You have: {', '.join(m.matched_skills)}")
        if m.missing_skills:
            print(f"   To work on: {', '.join(m.missing_skills)}")
        print(f"   {j.url}  (id: {j.id})\n")
    return 0


QUIT_WORDS = {"quit", "exit", "q"}
KIND_LABELS = {"technical": "Technical interview", "hr": "HR / personal interview"}


def say(speaker: str, text: str) -> None:
    print(f"\n{speaker}:")
    print(textwrap.fill(text, width=72, initial_indent="  ", subsequent_indent="  "))


def choose_job(matches):
    """Ask which posting to interview for; returns a JobPosting or None."""
    print("Postings at employers from your matching events:\n")
    for i, m in enumerate(matches, 1):
        kind = f" ({m.job.type})" if m.job.type else ""
        print(f"  {i}. {m.job.title}{kind} - {m.job.company}  [{m.skill_match_percent:g}% skill match]")
    while True:
        try:
            raw = input(f"\nChoose a posting [1-{len(matches)}]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        if raw in QUIT_WORDS:
            return None
        if raw.isdigit() and 1 <= int(raw) <= len(matches):
            return matches[int(raw) - 1].job
        print("Please enter one of the numbers above, or 'quit'.")


def load_interview_content(job_id: str) -> dict | None:
    path = FIXTURES / "interview_content" / f"{job_id}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    except (OSError, ValueError) as exc:
        warn(f"Ignoring interview notes {path.name}: {exc}")
        return None


def print_report(result: dict) -> None:
    print(f"\nScore: {result.get('totalScore', 0)}/10")
    if result.get("overallFeedback"):
        say("Overall", result["overallFeedback"])
    for key, title in (("strengths", "Strengths"), ("improvements", "Improvements"),
                       ("recommendations", "Practice before the career fair"), ("weakAreas", "Weak areas")):
        if result.get(key):
            print(f"\n{title}:")
            for item in result[key]:
                print(textwrap.fill(item, width=72, initial_indent="  - ", subsequent_indent="    "))
    for key in ("communication", "relevance", "examples"):
        if result.get(key):
            say(key.capitalize(), result[key])


def run_interview(session: InterviewSession) -> bool:
    """Ask questions until done or the student quits. Returns False if they quit."""
    warned_offline = session.offline
    while session.has_more_questions():
        number = len(session.history) + 1
        say(f"Recruiter (question {number}/{session.get_question_count()})", session.get_current_question())
        try:
            answer = input("\n> ")
        except (EOFError, KeyboardInterrupt):
            print()
            return False
        if answer.strip().lower() in QUIT_WORDS:
            return False
        if not session.offline and len(session.history) + 1 < session.get_question_count():
            print("  (The recruiter is thinking...)")
        try:
            session.submit_answer(answer)
        except KeyboardInterrupt:
            print()
            return False
        if session.offline and not warned_offline:
            warn(f"The LLM stopped responding ({session.llm_error}); continuing with standard questions.")
            warned_offline = True
    return True


def cmd_interview(args) -> int:
    try:
        resume = load_resume(args.resume)
    except ValidationError as exc:
        warn(f"Resume JSON is invalid: {exc}")
        return 2
    try:
        if args.job:
            by_id = {j.id: j for j in load_jobs(FIXTURES / "jobs.json")}
            if args.job not in by_id:
                warn(f"Unknown job id {args.job!r}. Known ids: {', '.join(sorted(by_id))}")
                return 2
            job = by_id[args.job]
        else:
            matches, _, _ = find_jobs(resume, args.live, args.snapshot, top_n=5)
            if not matches:
                warn("No postings found to interview for.")
                return 1
            banner(APP_NAME)
            job = choose_job(matches)
            if job is None:
                return 0
    except (EventSearchError, JobDataError) as exc:
        warn(str(exc))
        return 1

    company = load_company_profiles().get(job.company.lower()) or CompanyProfile(company_name=job.company)
    content = load_interview_content(job.id)
    client = None
    if not args.offline:
        try:
            client = LLMClient()
        except ConfigError as exc:
            warn(f"{exc} Running offline with the standard questions.")

    kinds = ["technical", "hr"] if args.type == "both" else [args.type]
    for kind in kinds:
        print(f"\n{'=' * 72}\n{KIND_LABELS[kind]}: {job.title} at {job.company}\n{'=' * 72}")
        print("Answer in a few sentences and press Enter. Type 'quit' to stop.")
        if client:
            print("(The recruiter is thinking...)")
        session = InterviewSession(company, resume, job, content, client, kind=kind,
                                   max_questions=args.questions)
        if session.offline and client:
            warn(f"LLM unavailable ({session.llm_error}); using the standard questions.")
        if session.offline:
            print("(Offline: standard practice questions, not tailored to this posting or your resume.)")
        finished = run_interview(session)
        if session.history:
            print("\nPreparing your feedback...")
            try:
                result = session.evaluate_interview()
            except KeyboardInterrupt:
                print("\nInterview ended early.")
                break
            basic = not result.get("strengths")
            if basic and not session.offline:
                warn(f"AI feedback unavailable ({session.llm_error}); showing the basic length-based score.")
            print(f"\n--- Feedback: {KIND_LABELS[kind]} ---")
            print(f"Answered {len(session.history)} of {session.get_question_count()} questions.")
            if basic:
                print("(Basic length-based score from the standard InterviewSession rules.)")
            print_report(result)
        if not finished:
            print("\nInterview ended early.")
            break
    return 0


def step(number: int, title: str, pause: bool) -> None:
    if pause and number > 1:
        try:
            input(f"\n[Press Enter for step {number}: {title}] ")
        except EOFError:
            pass
    print(f"\n{'#' * 72}\n#  Step {number}/4: {title}\n{'#' * 72}\n")


def parse_resume_file(path: Path, out: Path) -> bool:
    """Run the C++ parser on a resume file, writing its JSON to `out`."""
    binary = PARSER_DIR / "resume_parser"
    if not binary.exists():
        warn(f"C++ parser not built ({binary}); run `make` in '{PARSER_DIR}'.")
        return False
    try:
        result = subprocess.run([str(binary), str(path)], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        warn(f"Resume parser failed: {exc}")
        return False
    if result.returncode != 0:
        warn(f"Resume parser failed: {result.stderr.strip()}")
        return False
    out.write_text(result.stdout, encoding="utf-8")
    return True


def demo_job_id(resume, live: bool, snapshot: Path) -> str | None:
    """The best-matching internship (else the best posting) for the interview step."""
    matches, _, _ = find_jobs(resume, live, snapshot, top_n=10)
    for m in matches:
        if m.job.type == "internship":
            return m.job.id
    return matches[0].job.id if matches else None


def cmd_demo(args) -> int:
    live = not args.offline
    pause = not args.no_pause
    banner(f"{APP_NAME}: demo")
    print("Resume file -> C++ parser -> FGCU events -> jobs -> mock interview")
    if args.fast:
        print("(--fast: no AI event reranking; one technical interview)")
    if args.offline:
        print("(--offline: saved events and standard interview questions; no network)")

    with tempfile.TemporaryDirectory() as tmp:  # parsed JSON has personal details: never kept
        resume_json = Path(tmp) / "resume.json"
        step(1, "Parse the resume (C++ module)", pause)
        print(f"Resume file: {args.resume_file}\n")
        if parse_resume_file(args.resume_file, resume_json):
            print(resume_json.read_text(encoding="utf-8"))
        else:
            fallback = FIXTURES / "sample_resume_cpp.json"
            warn(f"Using the saved parser output {fallback.name} instead.")
            resume_json.write_text(fallback.read_text(encoding="utf-8"), encoding="utf-8")
        try:
            resume = load_resume(resume_json)
        except ValidationError as exc:
            warn(f"Resume JSON is invalid: {exc}")
            return 2

        common = {"resume": str(resume_json), "snapshot": FIXTURES / "sample_events.json", "live": live}
        step(2, "Find matching FGCU events (EagleLink)", pause)
        cmd_events(argparse.Namespace(**common, rerank=not (args.fast or args.offline), top=args.top,
                                      json=False))

        step(3, "Find jobs at employers from those events", pause)
        cmd_jobs(argparse.Namespace(**common, top=args.top, json=False))

        step(4, "Mock interview", pause)
        try:
            job_id = args.job or demo_job_id(resume, live, common["snapshot"])
        except (EventSearchError, JobDataError) as exc:
            warn(str(exc))
            return 1
        if not job_id:
            warn("No posting to interview for.")
            return 1
        kind = "technical" if args.fast else args.type
        return cmd_interview(argparse.Namespace(**common, job=job_id, type=kind,
                                                questions=args.questions, offline=args.offline))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=f"{APP_NAME}: AI integration demo")
    sub = parser.add_subparsers(dest="command", required=True)
    events = sub.add_parser("events", help="Find EagleLink events matching a resume")
    events.add_argument("--resume", default=str(FIXTURES / "sample_resume.json"),
                        help="Resume analysis JSON (C++ module output)")
    events.add_argument("--snapshot", type=Path, default=FIXTURES / "sample_events.json",
                        help="Saved EagleLink response used offline")
    events.add_argument("--live", action="store_true", help="Query EagleLink live (cached, polite)")
    events.add_argument("--rerank", action="store_true", help="Re-score top matches with the LLM")
    events.add_argument("--top", type=int, default=5, help="Number of events to show")
    events.add_argument("--json", action="store_true", help="Print JSON instead of text")
    events.set_defaults(func=cmd_events)

    jobs = sub.add_parser("jobs", help="Find jobs/internships at employers from matching events")
    jobs.add_argument("--resume", default=str(FIXTURES / "sample_resume.json"),
                      help="Resume analysis JSON (C++ module output)")
    jobs.add_argument("--snapshot", type=Path, default=FIXTURES / "sample_events.json",
                      help="Saved EagleLink response used offline")
    jobs.add_argument("--live", action="store_true", help="Query EagleLink live (cached, polite)")
    jobs.add_argument("--top", type=int, default=5, help="Number of postings to show")
    jobs.add_argument("--json", action="store_true", help="Print JSON instead of text")
    jobs.set_defaults(func=cmd_jobs)

    interview = sub.add_parser("interview", help="Interactive mock interview for a matched posting")
    interview.add_argument("--resume", default=str(FIXTURES / "sample_resume.json"),
                           help="Resume analysis JSON (C++ module output)")
    interview.add_argument("--snapshot", type=Path, default=FIXTURES / "sample_events.json",
                           help="Saved EagleLink response used offline")
    interview.add_argument("--live", action="store_true", help="Query EagleLink live (cached, polite)")
    interview.add_argument("--job", help="Posting id to skip the menu (see `main.py jobs`)")
    interview.add_argument("--type", choices=["technical", "hr", "both"], default="both",
                           help="Which interview(s) to run (default: both, technical first)")
    interview.add_argument("--questions", type=int, default=5, choices=range(1, 11), metavar="N",
                           help="Questions per interview, 1-10 (default 5)")
    interview.add_argument("--offline", action="store_true",
                           help="No LLM: standard questions and basic length-based scoring")
    interview.set_defaults(func=cmd_interview)

    demo = sub.add_parser("demo", help="Run the whole flow for a presentation")
    demo.add_argument("--resume-file", type=Path, default=PARSER_DIR / "samples" / "sample_resume.pdf",
                      help="Resume file (.pdf/.docx/.txt) for the C++ parser (default: sample PDF)")
    demo.add_argument("--job", help="Posting id for the interview (default: best-matching internship)")
    demo.add_argument("--type", choices=["technical", "hr", "both"], default="both",
                      help="Interview(s) to run (default: both)")
    demo.add_argument("--questions", type=int, default=2, choices=range(1, 11), metavar="N",
                      help="Questions per interview (default 2)")
    demo.add_argument("--top", type=int, default=5, help="Events and postings to show (default 5)")
    demo.add_argument("--fast", action="store_true",
                      help="Quicker: no AI event reranking and a technical interview only")
    demo.add_argument("--offline", action="store_true",
                      help="No network: saved events, standard questions, basic scoring")
    demo.add_argument("--no-pause", action="store_true", help="Don't wait for Enter between steps")
    demo.set_defaults(func=cmd_demo)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
