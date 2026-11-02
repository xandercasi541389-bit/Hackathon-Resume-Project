"""Company research JSON -> CompanyProfile. Provisional schema: edit the key tuples below to change it."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from . import ValidationError, opt_str, opt_str_list, read_json_object, split_extra

STR_KEYS = ("company_name", "industry", "description")
LIST_KEYS = ("business_activities", "relevant_departments")


@dataclass
class CompanyProfile:
    company_name: str
    industry: str = ""
    description: str = ""
    business_activities: list[str] = field(default_factory=list)
    relevant_departments: list[str] = field(default_factory=list)
    extra: dict = field(default_factory=dict)

    def to_prompt_text(self) -> str:
        lines = [f"Company: {self.company_name}"]
        if self.industry:
            lines.append(f"Industry: {self.industry}")
        if self.description:
            lines.append(f"Description: {self.description}")
        if self.business_activities:
            lines.append("Business activities: " + "; ".join(self.business_activities))
        if self.relevant_departments:
            lines.append("Relevant departments: " + "; ".join(self.relevant_departments))
        return "\n".join(lines)


def load_company(src: dict | str | os.PathLike) -> CompanyProfile:
    data = read_json_object(src, "company")
    name = opt_str(data, "company_name")
    if not name:
        raise ValidationError("Missing required field 'company_name' (must be a non-empty string)")
    return CompanyProfile(
        company_name=name,
        industry=opt_str(data, "industry"),
        description=opt_str(data, "description"),
        business_activities=opt_str_list(data, "business_activities"),
        relevant_departments=opt_str_list(data, "relevant_departments"),
        extra=split_extra(data, STR_KEYS + LIST_KEYS),
    )
