"""Job posting shapes (mirroring JobPosting / JobMatch in Resume.h) and their JSON loader."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from typing import Any


class JobDataError(ValueError):
    """Job data is missing, malformed, or has a field of the wrong type."""


@dataclass
class JobPosting:
    id: str
    title: str
    company: str
    type: str = ""  # internship | full-time | co-op
    location: str = ""
    url: str = ""
    description: str = ""
    required_skills: list[str] = field(default_factory=list)
    preferred_skills: list[str] = field(default_factory=list)
    retrieved_on: str = ""

    def to_prompt_text(self) -> str:
        """Compact plain text for LLM prompts; empty fields are omitted."""
        head = f"{self.title} at {self.company}"
        if self.type:
            head += f" ({self.type})"
        lines = [head]
        if self.location:
            lines.append("Location: " + self.location)
        if self.description:
            lines.append("Description: " + self.description)
        if self.required_skills:
            lines.append("Required skills: " + ", ".join(self.required_skills))
        if self.preferred_skills:
            lines.append("Preferred skills: " + ", ".join(self.preferred_skills))
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class JobMatch:
    job: JobPosting
    skill_match_percent: float  # 0-100, rounded to 1 decimal
    matched_skills: list[str]
    missing_skills: list[str]  # required first, then preferred

    def to_dict(self) -> dict:
        return {
            "job": self.job.to_dict(),
            "skill_match_percent": self.skill_match_percent,
            "matched_skills": self.matched_skills,
            "missing_skills": self.missing_skills,
        }


_OPTIONAL_STR = ("type", "location", "url", "description", "retrieved_on")
_SKILL_LISTS = ("required_skills", "preferred_skills")


def _req_str(item: dict, key: str, where: str) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise JobDataError(f"{where}: '{key}' is required and must be a non-empty string")
    return value.strip()


def _opt_str(item: dict, key: str, where: str) -> str:
    value = item.get(key)
    if value is None:
        return ""
    if not isinstance(value, str):
        raise JobDataError(f"{where}: '{key}' must be a string, not {type(value).__name__}")
    return value.strip()


def _skills(item: dict, key: str, where: str) -> list[str]:
    value = item.get(key)
    if value is None:
        return []
    if not isinstance(value, list):
        raise JobDataError(f"{where}: '{key}' must be a list, not {type(value).__name__}")
    out = []
    for i, skill in enumerate(value):
        if not isinstance(skill, str):
            raise JobDataError(
                f"{where}: '{key}[{i}]' must be a string, not {type(skill).__name__}"
            )
        if skill.strip():
            out.append(skill.strip())
    return out


def _parse_job(item: Any, index: int, origin: str) -> JobPosting:
    where = f"{origin} job #{index}"
    if not isinstance(item, dict):
        raise JobDataError(f"{where} must be an object, not {type(item).__name__}")
    fields: dict[str, Any] = {k: _req_str(item, k, where) for k in ("id", "title", "company")}
    for key in _OPTIONAL_STR:
        fields[key] = _opt_str(item, key, where)
    for key in _SKILL_LISTS:
        fields[key] = _skills(item, key, where)
    return JobPosting(**fields)


def load_jobs(src: str | os.PathLike | list) -> list[JobPosting]:
    """Load postings from a JSON file ({"jobs": [...]} or a bare list) or a list of dicts."""
    if isinstance(src, (str, os.PathLike)):
        origin = f"jobs file {os.fspath(src)!r}"
        try:
            with open(src, encoding="utf-8-sig") as fh:
                text = fh.read()
        except UnicodeDecodeError as exc:
            raise JobDataError(f"{origin} is not valid UTF-8: {exc}") from exc
        except (OSError, ValueError) as exc:
            raise JobDataError(f"Cannot read {origin}: {exc}") from exc
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, RecursionError) as exc:
            raise JobDataError(f"Invalid JSON in {origin}: {type(exc).__name__}: {exc}") from exc
    elif isinstance(src, list):
        origin, data = "jobs list", src
    else:
        raise JobDataError(
            f"jobs must be a file path or a list of dicts, not {type(src).__name__}"
        )
    if isinstance(data, dict):
        if "jobs" not in data:
            raise JobDataError(f"{origin} must be a list or an object with a 'jobs' key")
        data = data["jobs"]
    if not isinstance(data, list):
        raise JobDataError(f"{origin}: 'jobs' must be a list, not {type(data).__name__}")
    jobs, seen = [], set()
    for i, item in enumerate(data):
        job = _parse_job(item, i, origin)
        if job.id in seen:
            raise JobDataError(f"{origin}: duplicate job id {job.id!r}")
        seen.add(job.id)
        jobs.append(job)
    return jobs
