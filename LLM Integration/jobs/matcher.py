"""Score job postings against a resume by weighted skill overlap."""

from __future__ import annotations

import re

from integration import ResumeAnalysis

from .models import JobMatch, JobPosting

REQUIRED_WEIGHT = 2
PREFERRED_WEIGHT = 1

# Normalised skill -> other forms that count as the same skill.
ALIASES: dict[str, tuple[str, ...]] = {
    "js": ("javascript",),
    "javascript": ("js",),
    "postgres": ("postgresql",),
    "postgresql": ("postgres",),
    "golang": ("go",),
    "go": ("golang",),
    "ms sql": ("sql",),
    "sql server": ("sql",),
    "ml": ("machine learning",),
    "machine learning": ("ml",),
}


def _norm(text: str) -> str:
    return " ".join(text.lower().split())


def resume_skill_terms(resume: ResumeAnalysis) -> set[str]:
    """Lowercase skills, project technologies, certifications and resume.keywords()."""
    raw = [*resume.skills, *resume.certifications,
           *(t for p in resume.projects for t in p.technologies), *resume.keywords()]
    return {n for n in map(_norm, raw) if n}


def _in_text(term: str, text: str) -> bool:
    # Boundaries treat + # . as part of a word so `c` doesn't hit `c++`/`c#` and `js` doesn't
    # hit `node.js`; a trailing "." is still allowed (end of sentence).
    pattern = r"(?<![\w+#.])" + re.escape(term) + r"(?![\w+#])"
    return re.search(pattern, text) is not None


def skill_matches(skill: str, terms: set[str], resume_text: str) -> bool:
    norm = _norm(skill)
    if not norm:
        return False
    text = resume_text.lower()
    return any(c in terms or _in_text(c, text) for c in (norm, *ALIASES.get(norm, ())))


def _company_ok(company: str, wanted: list[str]) -> bool:
    c = _norm(company)
    return any(w in c or c in w for w in wanted)


def match_jobs(resume: ResumeAnalysis, jobs: list[JobPosting],
               companies: list[str] | None = None, top_n: int = 5) -> list[JobMatch]:
    """Best `top_n` postings by weighted skill match (required x2, preferred x1).

    `companies` (None or empty = no filter) keeps postings whose company equals or
    contains / is contained in one of the names, case-insensitively.
    """
    wanted = [n for n in (_norm(c) for c in companies or []) if n]
    terms = resume_skill_terms(resume)
    text = resume.to_prompt_text()
    scored: list[tuple[JobMatch, int]] = []
    for job in jobs:
        if wanted and not _company_ok(job.company, wanted):
            continue
        matched: list[str] = []
        missing: list[str] = []
        matched_weight = total_weight = req_hits = 0
        for skills, weight in ((job.required_skills, REQUIRED_WEIGHT),
                               (job.preferred_skills, PREFERRED_WEIGHT)):
            for skill in skills:
                total_weight += weight
                if skill_matches(skill, terms, text):
                    matched.append(skill)
                    matched_weight += weight
                    req_hits += weight == REQUIRED_WEIGHT
                else:
                    missing.append(skill)
        percent = round(100 * matched_weight / total_weight, 1) if total_weight else 0.0
        scored.append((JobMatch(job, percent, matched, missing), req_hits))
    scored.sort(key=lambda s: (-s[0].skill_match_percent, -s[1], s[0].job.title))
    return [m for m, _ in scored[:max(0, top_n)]]
