"""End-to-end tests of the CLI (`main.main`) with scripted input; no network, no real LLM."""
import json
from pathlib import Path

import pytest

import main
from ai import ConfigError, LLMError
from ai.question_bank import HR_QUESTIONS, TECHNICAL_QUESTIONS

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
RESUME = str(FIXTURES / "sample_resume_cpp.json")
JOB_2 = "arthrex-technical-artist-intern"  # 2nd in the menu for sample_resume_cpp.json

FEEDBACK = json.dumps({
    "totalScore": 7, "overallFeedback": "Solid answers overall.",
    "strengths": ["Clear structure"], "improvements": ["Add metrics"],
    "recommendations": ["Practice STAR stories"], "weakAreas": ["Depth"],
    "communication": "Clear.", "relevance": "On topic.", "examples": "Needs more.",
})
LONG_ANSWER = "I built a service that parsed resumes and matched them to events. " * 3


def script_input(monkeypatch, answers):
    answers = list(answers)

    def fake(prompt=""):
        if not answers:
            raise EOFError
        return answers.pop(0)

    monkeypatch.setattr("builtins.input", fake)
    return answers


class FakeClient:
    """Stands in for LLMClient; each reply is a string, or an exception to raise."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0

    def chat(self, messages, **kwargs):
        self.calls += 1
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def interview(*extra):
    return main.main(["interview", "--resume", RESUME, *extra])


# -- jobs ---------------------------------------------------------------------------------

def test_jobs_lists_postings_with_urls(capsys):
    assert main.main(["jobs", "--resume", RESUME]) == 0
    out = capsys.readouterr().out
    assert out.count("https://") >= 2
    assert "Arthrex" in out and "Gartner" in out


def test_jobs_json(capsys):
    assert main.main(["jobs", "--resume", RESUME, "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["employers"]
    assert len(data["matches"]) >= 2


def test_jobs_invalid_resume(capsys, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("[]")
    assert main.main(["jobs", "--resume", str(bad)]) == 2
    assert "Resume JSON is invalid" in capsys.readouterr().err


# -- offline interviews ---------------------------------------------------------------------

def test_interview_offline_technical(monkeypatch, capsys):
    script_input(monkeypatch, ["2", LONG_ANSWER, LONG_ANSWER])
    assert interview("--offline", "--type", "technical", "--questions", "2") == 0
    out = capsys.readouterr().out
    assert "Technical Artist Intern at Arthrex" in out
    assert TECHNICAL_QUESTIONS[0] in out and TECHNICAL_QUESTIONS[1] in out
    assert TECHNICAL_QUESTIONS[2] not in out
    assert "Score: 10/10" in out  # 4 of 4 points, scaled
    assert "Interview ended early" not in out


def test_interview_both_runs_technical_then_hr(monkeypatch, capsys):
    script_input(monkeypatch, ["1", "short", "short"])
    assert interview("--offline", "--type", "both", "--questions", "1") == 0
    out = capsys.readouterr().out
    tech, hr = out.index("Technical interview:"), out.index("HR / personal interview:")
    assert tech < hr
    assert TECHNICAL_QUESTIONS[0] in out and HR_QUESTIONS[0] in out


def test_interview_job_flag_skips_menu(monkeypatch, capsys):
    inputs = script_input(monkeypatch, [LONG_ANSWER])
    assert interview("--offline", "--type", "hr", "--questions", "1", "--job", JOB_2) == 0
    out = capsys.readouterr().out
    assert "Choose a posting" not in out
    assert "Technical Artist Intern at Arthrex" in out
    assert inputs == []


def test_interview_unknown_job(monkeypatch, capsys):
    script_input(monkeypatch, [])
    assert interview("--offline", "--job", "nope") == 2
    err = capsys.readouterr().err
    assert "Unknown job id 'nope'" in err
    assert JOB_2 in err and "gartner-lead-qualification-specialist" in err


def test_invalid_menu_input_then_valid(monkeypatch, capsys):
    script_input(monkeypatch, ["abc", "99", "0", "1", "hello"])
    assert interview("--offline", "--type", "technical", "--questions", "1") == 0
    out = capsys.readouterr().out
    assert out.count("Please enter one of the numbers above") == 3
    assert "Score:" in out


def test_quit_at_menu(monkeypatch, capsys):
    script_input(monkeypatch, ["quit"])
    assert interview("--offline") == 0
    out = capsys.readouterr().out
    assert "Recruiter" not in out and "Score:" not in out


def test_quit_mid_interview_scores_only_answered(monkeypatch, capsys):
    script_input(monkeypatch, ["1", LONG_ANSWER, "quit"])
    assert interview("--offline", "--type", "both", "--questions", "3") == 0
    out = capsys.readouterr().out
    assert "Interview ended early." in out
    assert "Score: 3/10" in out  # 2 of 6 points, scaled
    assert "HR / personal interview:" not in out


def test_quit_before_any_answer_prints_no_feedback(monkeypatch, capsys):
    script_input(monkeypatch, ["1", "quit"])
    assert interview("--offline", "--type", "both") == 0
    out = capsys.readouterr().out
    assert "Interview ended early." in out
    assert "Score:" not in out and "Feedback" not in out
    assert "HR / personal interview:" not in out


def test_eof_behaves_like_quit(monkeypatch, capsys):
    script_input(monkeypatch, ["1", LONG_ANSWER])  # then input is exhausted
    assert interview("--offline", "--type", "both", "--questions", "3") == 0
    out = capsys.readouterr().out
    assert "Interview ended early." in out
    assert "Score: 3/10" in out  # 2 of 6 points, scaled
    assert "HR / personal interview:" not in out


def test_eof_at_menu(monkeypatch, capsys):
    script_input(monkeypatch, [])
    assert interview("--offline") == 0
    assert "Recruiter" not in capsys.readouterr().out


def test_interview_invalid_resume(monkeypatch, capsys, tmp_path):
    script_input(monkeypatch, [])
    bad = tmp_path / "bad.json"
    bad.write_text("not json")
    assert main.main(["interview", "--resume", str(bad), "--offline"]) == 2
    assert "Resume JSON is invalid" in capsys.readouterr().err


@pytest.mark.parametrize("n", ["0", "11"])
def test_questions_out_of_range_rejected(n):
    with pytest.raises(SystemExit):
        interview("--questions", n)


# -- LLM path (fake client) -------------------------------------------------------------------

def test_llm_path_uses_fake_questions_and_feedback(monkeypatch, capsys):
    client = FakeClient(["Recruiter: Walk me through your Unity pipeline.", FEEDBACK])
    monkeypatch.setattr(main, "LLMClient", lambda: client)
    script_input(monkeypatch, [LONG_ANSWER])
    assert interview("--type", "technical", "--questions", "1", "--job", JOB_2) == 0
    captured = capsys.readouterr()
    assert "Walk me through your Unity pipeline." in captured.out
    assert TECHNICAL_QUESTIONS[0] not in captured.out
    assert "Score: 7/10" in captured.out
    assert "Clear structure" in captured.out
    assert "Add metrics" in captured.out
    assert "Practice STAR stories" in captured.out
    assert captured.err == ""


def test_config_error_falls_back_to_offline(monkeypatch, capsys):
    def boom():
        raise ConfigError("NRP_API_KEY is not set.")

    monkeypatch.setattr(main, "LLMClient", boom)
    script_input(monkeypatch, [LONG_ANSWER])
    assert interview("--type", "technical", "--questions", "1", "--job", JOB_2) == 0
    captured = capsys.readouterr()
    assert "NRP_API_KEY is not set." in captured.err
    assert "offline" in captured.err.lower()
    assert TECHNICAL_QUESTIONS[0] in captured.out
    assert "Score: 10/10" in captured.out  # 2 of 2 points, scaled


def test_llm_error_mid_interview_continues_with_standard_questions(monkeypatch, capsys):
    client = FakeClient(["Fake question one?", LLMError("timeout")])
    monkeypatch.setattr(main, "LLMClient", lambda: client)
    script_input(monkeypatch, [LONG_ANSWER, LONG_ANSWER])
    assert interview("--type", "technical", "--questions", "2", "--job", JOB_2) == 0
    captured = capsys.readouterr()
    assert "continuing with standard questions" in captured.err
    assert "Fake question one?" in captured.out
    # Falls back to the first bank question not asked yet.
    assert TECHNICAL_QUESTIONS[0] in captured.out
    assert "Score: 10/10" in captured.out
    assert "Interview ended early" not in captured.out


# -- demo command ---------------------------------------------------------------------------

def test_demo_offline_runs_all_steps(monkeypatch, capsys):
    script_input(monkeypatch, [LONG_ANSWER, LONG_ANSWER])  # technical answers; HR then hits EOF
    assert main.main(["demo", "--offline", "--no-pause", "--type", "technical"]) == 0
    out = capsys.readouterr().out
    for n in range(1, 5):
        assert f"Step {n}/4" in out
    assert '"skills"' in out                       # step 1 printed the parser JSON
    assert "Employers at matching events: Arthrex" in out
    assert "Technical interview: Technical Artist Intern at Arthrex" in out  # best internship
    assert "Score:" in out


def test_demo_falls_back_when_parser_missing(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(main, "PARSER_DIR", tmp_path)  # no resume_parser binary here
    script_input(monkeypatch, [])
    assert main.main(["demo", "--offline", "--no-pause", "--type", "hr", "--questions", "1"]) == 0
    captured = capsys.readouterr()
    assert "C++ parser not built" in captured.err
    assert "sample_resume_cpp.json" in captured.err
    assert "Step 4/4" in captured.out


def test_demo_fast_skips_rerank_and_runs_technical_only(monkeypatch, capsys):
    called = []
    monkeypatch.setattr(main, "rerank_with_llm", lambda *a, **k: called.append(1))
    client = FakeClient(["Fake question?", FEEDBACK])
    monkeypatch.setattr(main, "LLMClient", lambda: client)
    monkeypatch.setattr(main, "load_events", lambda live, snapshot: (main.load_events_file(snapshot), "snapshot"))
    script_input(monkeypatch, [LONG_ANSWER])
    assert main.main(["demo", "--fast", "--no-pause", "--questions", "1"]) == 0
    out = capsys.readouterr().out
    assert not called
    assert "Technical interview:" in out and "HR / personal interview:" not in out
