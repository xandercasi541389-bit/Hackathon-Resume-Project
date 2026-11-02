"""Adapters that turn teammates' JSON (company research, C++ resume analyser) into typed objects."""
from __future__ import annotations

import json
import os
from typing import Any


class ValidationError(ValueError):
    """Input JSON is missing, malformed, or has a field of the wrong type."""


def read_json_object(src: Any, what: str) -> dict:
    """Return a dict from a dict, a JSON string (starts with '{'), or a path to a UTF-8 JSON file."""
    if isinstance(src, dict):
        return src
    if isinstance(src, str) and src.lstrip("\ufeff \t\r\n").startswith("{"):
        text, origin = src.lstrip("\ufeff \t\r\n"), f"{what} JSON string"
    elif isinstance(src, (str, os.PathLike)):
        origin = f"{what} file {os.fspath(src)!r}"
        try:
            with open(src, encoding="utf-8-sig") as fh:  # tolerate a BOM (Windows tools)
                text = fh.read()
        except UnicodeDecodeError as exc:  # before ValueError: it's a subclass
            raise ValidationError(f"{origin} is not valid UTF-8: {exc}") from exc
        except (OSError, ValueError) as exc:  # ValueError: e.g. NUL byte in path
            raise ValidationError(f"Cannot read {origin}: {exc}") from exc
    else:
        raise ValidationError(
            f"{what} must be a dict, JSON string, or file path, not {type(src).__name__}"
        )
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, RecursionError) as exc:
        raise ValidationError(f"Invalid JSON in {origin}: {type(exc).__name__}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValidationError(f"{origin} must contain a JSON object, not {type(data).__name__}")
    return data


def opt_str(data: dict, key: str) -> str:
    """Optional string field; None -> ''."""
    value = data.get(key)
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValidationError(f"Field '{key}' must be a string, not {type(value).__name__}")
    return value.strip()


def opt_str_list(data: dict, key: str) -> list[str]:
    """Optional list of strings; None -> []. Blank entries are dropped."""
    value = data.get(key)
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValidationError(f"Field '{key}' must be a list, not {type(value).__name__}")
    out = []
    for i, item in enumerate(value):
        if not isinstance(item, str):
            raise ValidationError(
                f"Field '{key}[{i}]' must be a string, not {type(item).__name__}"
            )
        if item.strip():
            out.append(item.strip())
    return out


def split_extra(data: dict, known: tuple[str, ...]) -> dict:
    return {k: v for k, v in data.items() if k not in known}


from .company_adapter import CompanyProfile, load_company  # noqa: E402
from .resume_adapter import ResumeAnalysis, load_resume  # noqa: E402

__all__ = ["load_company", "load_resume", "CompanyProfile", "ResumeAnalysis", "ValidationError"]
