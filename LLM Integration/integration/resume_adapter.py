"""C++ resume-analyser JSON -> ResumeAnalysis. Provisional schema: edit the key tuples below to change it."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from . import ValidationError, opt_str, opt_str_list, read_json_object, split_extra

TOP_KEYS = ("education", "skills", "experience", "projects")
EDUCATION_KEYS = ("degree", "institution")
EXPERIENCE_KEYS = ("role", "description")
PROJECT_KEYS = ("name", "description")


@dataclass
class Education:
    degree: str = ""
    institution: str = ""
    extra: dict = field(default_factory=dict)


@dataclass
class Experience:
    role: str = ""
    description: str = ""
    extra: dict = field(default_factory=dict)


@dataclass
class Project:
    name: str = ""
    description: str = ""
    extra: dict = field(default_factory=dict)


def _items(data: dict, key: str, cls, keys: tuple[str, ...], str_field: str) -> list:
    """Parse a list of dicts; a plain string item fills `str_field`."""
    value = data.get(key)
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValidationError(f"Field '{key}' must be a list, not {type(value).__name__}")
    out = []
    for i, item in enumerate(value):
        if item is None:
            continue
        if isinstance(item, str):
            if item.strip():
                out.append(cls(**{str_field: item.strip()}))
        elif isinstance(item, dict):
            try:
                fields = {k: opt_str(item, k) for k in keys}
            except ValidationError as exc:
                raise ValidationError(f"In '{key}[{i}]': {exc}") from exc
            out.append(cls(**fields, extra=split_extra(item, keys)))
        else:
            raise ValidationError(
                f"Field '{key}[{i}]' must be a string or object, not {type(item).__name__}"
            )
    return out


@dataclass
class ResumeAnalysis:
    education: list[Education] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    experience: list[Experience] = field(default_factory=list)
    projects: list[Project] = field(default_factory=list)
    extra: dict = field(default_factory=dict)

    def to_prompt_text(self) -> str:
        lines = []
        if self.education:
            lines.append("Education:")
            for e in self.education:
                lines.append("- " + ", ".join(p for p in (e.degree, e.institution) if p))
        if self.skills:
            lines.append("Skills: " + ", ".join(self.skills))
        if self.experience:
            lines.append("Experience:")
            for x in self.experience:
                lines.append("- " + ": ".join(p for p in (x.role, x.description) if p))
        if self.projects:
            lines.append("Projects:")
            for p in self.projects:
                lines.append("- " + ": ".join(s for s in (p.name, p.description) if s))
        return "\n".join(lines)

    def keywords(self) -> list[str]:
        """Deduped lowercase terms from skills, degrees, roles, project names (first-seen order)."""
        terms = [*self.skills, *(e.degree for e in self.education),
                 *(x.role for x in self.experience), *(p.name for p in self.projects)]
        seen: dict[str, None] = {}
        for t in terms:
            t = t.strip().lower()
            if t:
                seen.setdefault(t)
        return list(seen)


def load_resume(src: dict | str | os.PathLike) -> ResumeAnalysis:
    data = read_json_object(src, "resume")
    resume = ResumeAnalysis(
        education=_items(data, "education", Education, EDUCATION_KEYS, "degree"),
        skills=opt_str_list(data, "skills"),
        experience=_items(data, "experience", Experience, EXPERIENCE_KEYS, "description"),
        projects=_items(data, "projects", Project, PROJECT_KEYS, "description"),
        extra=split_extra(data, TOP_KEYS),
    )
    if not (resume.education or resume.skills or resume.experience or resume.projects):
        raise ValidationError(
            "Resume must have at least one non-empty field of: " + ", ".join(TOP_KEYS)
        )
    return resume
