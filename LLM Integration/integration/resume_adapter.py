"""C++ resume-analyser JSON -> ResumeAnalysis.

The schema follows the structs in Resume.h (keys = struct field names), e.g.
`experience[{company, position, startDate, endDate, responsibilities[]}]`.
The earlier provisional keys (`role`, `description`) are still accepted.
Edit the key maps below to follow schema changes.

Personal details (name, email, phone, location, fileName, rawText) are kept in
`extra` and never included in to_prompt_text(), so they aren't sent to the LLM.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from . import ValidationError, opt_str, opt_str_list, read_json_object, split_extra

# JSON key -> dataclass field. Several JSON keys may feed one field (first non-empty wins).
EDUCATION_STR = {"degree": "degree", "institution": "institution", "major": "major",
                 "graduationDate": "graduation_date"}
EXPERIENCE_STR = {"position": "role", "role": "role", "company": "company",
                  "startDate": "start_date", "endDate": "end_date", "description": "description"}
EXPERIENCE_LIST = {"responsibilities": "responsibilities"}
PROJECT_STR = {"name": "name", "description": "description"}
PROJECT_LIST = {"technologies": "technologies"}
TOP_LISTS = ("skills", "certifications")
TOP_STR = ("summary",)
SECTIONS = ("education", "skills", "experience", "projects")  # at least one must be non-empty
PERSONAL_KEYS = ("fileName", "rawText", "name", "email", "phone", "location")  # -> extra only


@dataclass
class Education:
    degree: str = ""
    institution: str = ""
    major: str = ""
    graduation_date: str = ""
    extra: dict = field(default_factory=dict)


@dataclass
class Experience:
    role: str = ""
    description: str = ""
    company: str = ""
    start_date: str = ""
    end_date: str = ""
    responsibilities: list[str] = field(default_factory=list)
    extra: dict = field(default_factory=dict)


@dataclass
class Project:
    name: str = ""
    description: str = ""
    technologies: list[str] = field(default_factory=list)
    extra: dict = field(default_factory=dict)


def _items(data: dict, key: str, cls, str_map: dict, list_map: dict, str_field: str) -> list:
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
            fields: dict = {}
            try:
                for json_key, attr in str_map.items():
                    text = opt_str(item, json_key)
                    if text and not fields.get(attr):
                        fields[attr] = text
                for json_key, attr in list_map.items():
                    fields[attr] = opt_str_list(item, json_key)
            except ValidationError as exc:
                raise ValidationError(f"In '{key}[{i}]': {exc}") from exc
            out.append(cls(**fields, extra=split_extra(item, (*str_map, *list_map))))
        else:
            raise ValidationError(
                f"Field '{key}[{i}]' must be a string or object, not {type(item).__name__}"
            )
    return out


def _join(*parts: str, sep: str = ", ") -> str:
    return sep.join(p for p in parts if p)


@dataclass
class ResumeAnalysis:
    education: list[Education] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    experience: list[Experience] = field(default_factory=list)
    projects: list[Project] = field(default_factory=list)
    certifications: list[str] = field(default_factory=list)
    summary: str = ""
    extra: dict = field(default_factory=dict)

    def to_prompt_text(self) -> str:
        lines = []
        if self.summary:
            lines.append("Summary: " + self.summary)
        if self.education:
            lines.append("Education:")
            for e in self.education:
                degree = _join(e.degree, e.major and f"in {e.major}", sep=" ")
                lines.append("- " + _join(degree, e.institution, e.graduation_date))
        if self.skills:
            lines.append("Skills: " + ", ".join(self.skills))
        if self.experience:
            lines.append("Experience:")
            for x in self.experience:
                dates = _join(x.start_date, x.end_date, sep=" - ")
                head = _join(x.role, x.company and f"at {x.company}", sep=" ")
                head = _join(head, dates and f"({dates})", sep=" ")
                lines.append("- " + _join(head, x.description, sep=": "))
                lines.extend(f"  * {r}" for r in x.responsibilities)
        if self.projects:
            lines.append("Projects:")
            for p in self.projects:
                tech = f"({', '.join(p.technologies)})" if p.technologies else ""
                name = _join(p.name, tech, sep=" ")
                lines.append("- " + _join(name, p.description, sep=": "))
        if self.certifications:
            lines.append("Certifications: " + ", ".join(self.certifications))
        return "\n".join(lines)

    def keywords(self) -> list[str]:
        """Deduped lowercase terms (first-seen order) from skills, degrees, majors, roles,
        project names and technologies, and certifications."""
        terms = [*self.skills,
                 *(t for e in self.education for t in (e.degree, e.major)),
                 *(x.role for x in self.experience),
                 *(t for p in self.projects for t in (p.name, *p.technologies)),
                 *self.certifications]
        seen: dict[str, None] = {}
        for t in terms:
            t = t.strip().lower()
            if t:
                seen.setdefault(t)
        return list(seen)


def load_resume(src: dict | str | os.PathLike) -> ResumeAnalysis:
    data = read_json_object(src, "resume")
    resume = ResumeAnalysis(
        education=_items(data, "education", Education, EDUCATION_STR, {}, "degree"),
        skills=opt_str_list(data, "skills"),
        experience=_items(data, "experience", Experience, EXPERIENCE_STR, EXPERIENCE_LIST,
                          "description"),
        projects=_items(data, "projects", Project, PROJECT_STR, PROJECT_LIST, "description"),
        certifications=opt_str_list(data, "certifications"),
        summary=opt_str(data, "summary"),
        extra=split_extra(data, (*SECTIONS, *TOP_LISTS, *TOP_STR)),
    )
    if not (resume.education or resume.skills or resume.experience or resume.projects):
        raise ValidationError(
            "Resume must have at least one non-empty field of: " + ", ".join(SECTIONS)
        )
    return resume
