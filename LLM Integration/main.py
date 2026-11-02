"""Command-line demo for the AI integration module.

  python main.py events [--resume PATH] [--live] [--rerank] [--top N] [--json]
  python main.py jobs   [--resume PATH] [--live] [--top N] [--json]

`events` ranks EagleLink events for a resume analysis (the C++ module's JSON).
`jobs` finds the employers named in those events and ranks their (curated, real)
job and internship postings against the resume.
Without --live both read the saved snapshot in fixtures/; with --live they query
EagleLink once (small, cached) and tell you if they have to use the snapshot instead.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from ai import ConfigError, LLMClient, LLMError
from eventsearch import match_events, rerank_with_llm
from eventsearch.eaglelink_client import EagleLinkClient, EventSearchError, load_events_file
from integration import ValidationError, load_company, load_resume
from jobs import JobDataError, load_jobs, match_jobs

APP_NAME = "Hackathon Resume Project"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


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
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
