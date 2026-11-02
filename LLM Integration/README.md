# AI integration module

Python module for the career-fair prep assistant: NRP LLM client, adapters for the
company-research and C++ resume-analysis JSON, and EagleLink event search.
It also finds real jobs at those employers and runs Technical and HR mock interviews.

## Setup
```bash
cd hackathon_resume_project
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env   # then set NRP_API_KEY; .env is git-ignored
```

| Variable | Default | |
|---|---|---|
| `NRP_API_KEY` | (required) | NRP LLM token |
| `NRP_BASE_URL` | `https://ellm.nrp-nautilus.io/v1` | OpenAI-compatible endpoint |
| `NRP_MODEL` | `gpt-oss` | Any id from `LLMClient().list_models()`; never switched automatically |
| `NRP_TIMEOUT` / `NRP_MAX_RETRIES` | `120` / `2` | Per-request timeout (s) and SDK retries |

## Demo: events matching a resume
```bash
.venv/bin/python main.py events                       # sample resume + saved EagleLink snapshot
.venv/bin/python main.py events --live --rerank       # live EagleLink + LLM re-scoring
.venv/bin/python main.py events --resume path/to/cpp_output.json --json
```
`--live` makes at most two small, cached requests to EagleLink with an identifying
User-Agent (its robots.txt disallows `/api/`, so keep it to explicit user searches).
If the live search or the LLM fails, the CLI says so and falls back to the snapshot or keyword ranking.

## Find jobs

```bash
.venv/bin/python main.py jobs --resume fixtures/sample_resume_cpp.json
```

Finds the employers named in your matching EagleLink events, then ranks their curated
job and internship postings against your resume (skills you have / skills to work on,
posting URL and id). Options: `--top N` (default 5), `--json`, `--live` (query EagleLink
once instead of the saved snapshot), `--snapshot PATH`.

## Mock interviews

```bash
.venv/bin/python main.py interview --resume fixtures/sample_resume_cpp.json
```

Pick a posting from the menu (or skip it with `--job <id>`), then answer a recruiter's
questions in the terminal. When you finish you get a score and written feedback.
Type `quit` (or press Ctrl-D / Ctrl-C) at any time to stop early; you still get feedback for the
questions you answered.

| Option | Meaning |
| --- | --- |
| `--resume PATH` | Resume analysis JSON (parser output) |
| `--job ID` | Skip the menu; ids are shown by `main.py jobs` |
| `--type technical\|hr\|both` | Which interview(s) to run (default `both`, technical first) |
| `--questions N` | Questions per interview, 1-10 (default 5) |
| `--offline` | No LLM: standard questions and basic length-based scoring |
| `--live` | Use live EagleLink events instead of the snapshot |
| `--snapshot PATH` | Saved EagleLink response to use offline |

Example session:

```text
Postings at employers from your matching events:

  1. Lead Software Integration Developer (full-time) - Arthrex  [13% skill match]
  2. Technical Artist Intern (internship) - Arthrex  [6.7% skill match]

Choose a posting [1-5]: 2

Recruiter (question 1/5):
  Explain the difference between a stack and a queue.

> A stack is last-in first-out, a queue is first-in first-out...

Score: 7/10
Strengths:
  - Clear structure
```

**Offline mode.** With `--offline` (or if no API key is configured, or the LLM stops
responding mid-interview) the session continues with the standard question bank and the
length-based score, and prints a warning explaining why.

**Mirrors the C++ module.** The question bank and the offline scoring in
`ai/question_bank.py` mirror `InterviewSession.cpp`; the Python session exposes the same
interface (`get_current_question`, `submit_answer`, `has_more_questions`,
`get_question_count`, `evaluate_interview`). Keep them in sync.

**Speed.** For snappier replies set `NRP_MODEL=gpt-oss`.

**Privacy.** Personal resume fields (name, email, phone, location) are never sent to the
LLM; only the skills/experience text from `ResumeAnalysis.to_prompt_text()` is.

## End to end: resume file to interview

```bash
# 1. Parse a resume (C++ parser; build it once with `make` in ../Resume Parser) into JSON.
#    Keep resume.json out of git: it contains your name and contact details.
"../Resume Parser/resume_parser" path/to/resume.pdf > /tmp/resume.json
# 2. Find matching events and the jobs at the employers attending
.venv/bin/python main.py jobs --resume /tmp/resume.json
# 3. Practice interviewing for one of them
.venv/bin/python main.py interview --resume /tmp/resume.json --job <id>
```

## Integration contract (teammates' modules)
- **Resume (C++ module):** `load_resume(src)` accepts a dict, a path to a JSON file, or a JSON
  string (e.g. the C++ program's stdout). Keys: `education[{degree, institution}]`, `skills[]`,
  `experience[{role, description}]`, `projects[{name, description}]`; at least one non-empty.
  Unknown keys are kept in `.extra`. See `fixtures/sample_resume.json`.
- **Company (research module):** `load_company(src)`, same input forms; `company_name` required.
  See `fixtures/sample_company.json`.
- Both raise `integration.ValidationError` with the offending field named.
  Field names live in key tuples at the top of each adapter for easy schema changes.

## Code
```python
from ai import LLMClient                      # one shared client; reads NRP_* from .env
from integration import load_resume
from eventsearch import match_events, rerank_with_llm
from eventsearch.eaglelink_client import EagleLinkClient

resume = load_resume("fixtures/sample_resume.json")
matches = match_events(resume, EagleLinkClient().career_events())
matches = rerank_with_llm(LLMClient(), resume, matches)   # optional
```

## Tests
```bash
.venv/bin/python -m pytest tests -q                                   # mocked, no network
RUN_LIVE_TESTS=1 .venv/bin/python -m pytest tests/test_live_api.py -v  # real NRP API (uses quota)
```
