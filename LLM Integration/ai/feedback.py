"""Post-interview feedback: ask the LLM to evaluate the transcript and normalise its JSON reply."""

from __future__ import annotations

import json
import math
import re

from . import prompts
from .llm_client import LLMError

FEEDBACK_KEYS = ("totalScore", "overallFeedback", "weakAreas", "strengths", "improvements",
                 "recommendations", "communication", "relevance", "examples")
_LIST_KEYS = ("weakAreas", "strengths", "improvements", "recommendations")
_STR_KEYS = ("overallFeedback", "communication", "relevance", "examples")
_RETRY_MESSAGE = "Your previous reply was not valid JSON. Reply with only the JSON object."


def _score(value) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, str):
        match = re.search(r"-?\d+(?:\.\d+)?", value)
        if not match:
            return 0
        value = float(match.group())
    if not isinstance(value, (int, float)) or (isinstance(value, float) and not math.isfinite(value)):
        return 0
    return max(0, min(10, int(round(value))))


def _str_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (str, int, float)):
        value = [value]
    if not isinstance(value, list):
        return []
    return [s for s in (str(v).strip() for v in value if v is not None) if s]


def _normalise(data: dict) -> dict:
    out: dict = {"totalScore": _score(data.get("totalScore"))}
    for key in _STR_KEYS:
        value = data.get(key)
        out[key] = "" if value is None else str(value).strip()
    for key in _LIST_KEYS:
        out[key] = _str_list(data.get(key))
    return {key: out[key] for key in FEEDBACK_KEYS}


def parse_feedback(text: str) -> dict:
    """Parse the model's reply into a dict with exactly FEEDBACK_KEYS.

    Raises ValueError if the reply holds no JSON object.
    """
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end < start:
        raise ValueError("No JSON object found in the reply.")
    data = json.loads(text[start:end + 1])
    if not isinstance(data, dict):
        raise ValueError("Feedback JSON must be an object.")
    return _normalise(data)


def generate_feedback(client, transcript: list[tuple[str, str]], kind: str,
                      company: str, job_title: str, job_text: str) -> dict:
    if not transcript:
        return _normalise({"totalScore": 0, "overallFeedback": "No answers were given."})
    messages = [
        {"role": "system", "content": prompts.feedback_system_prompt(kind, company, job_title)},
        {"role": "user", "content": prompts.transcript_message(transcript, job_text)},
    ]
    reply = client.chat(messages, temperature=0.2, max_tokens=2048)
    try:
        return parse_feedback(reply)
    except ValueError:  # includes json.JSONDecodeError
        pass
    retry = messages + [{"role": "assistant", "content": reply},
                        {"role": "user", "content": _RETRY_MESSAGE}]
    reply = client.chat(retry, temperature=0.2, max_tokens=2048)
    try:
        return parse_feedback(reply)
    except ValueError as exc:
        raise LLMError(f"Could not parse interview feedback: {exc}") from exc
