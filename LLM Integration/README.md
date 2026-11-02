# AI integration module

Python module for the career-fair prep assistant: NRP LLM client, adapters for the
company-research and C++ resume-analysis JSON, and EagleLink event search.
The interview engine is added once the prompts branch lands.

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
| `NRP_TIMEOUT` / `NRP_MAX_RETRIES` | `60` / `2` | Per-request timeout (s) and SDK retries |

## Demo: events matching a resume
```bash
.venv/bin/python main.py events                       # sample resume + saved EagleLink snapshot
.venv/bin/python main.py events --live --rerank       # live EagleLink + LLM re-scoring
.venv/bin/python main.py events --resume path/to/cpp_output.json --json
```
`--live` makes at most two small, cached requests to EagleLink with an identifying
User-Agent (its robots.txt disallows `/api/`, so keep it to explicit user searches).
If the live search or the LLM fails, the CLI says so and falls back to the snapshot or keyword ranking.

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
