"""LLM-driven mock interview session.

Mirrors the team's C++ InterviewSession (InterviewSession.h on main):
  getCurrentQuestion / submitAnswer / hasMoreQuestions / getQuestionCount / evaluateInterview
and returns its InterviewResult fields (totalScore, overallFeedback, weakAreas) plus
richer, LLM-written feedback. `kind` plays the role of the C++ targetRole switch.

With no client, or when the LLM fails, the session continues with the C++ question
bank and scoring (ai.question_bank), and says so via `offline` / `llm_error`.
The resume reaches the LLM only through ResumeAnalysis.to_prompt_text(), so the
student's name, email, phone and location are never sent.
"""

from __future__ import annotations

import re

from . import prompts, question_bank
from .feedback import FEEDBACK_KEYS, generate_feedback
from .llm_client import LLMError

KINDS = ("technical", "hr")


def content_to_text(content: dict | None, kind: str) -> str:
    """Research notes for the prompt; only the parts relevant to this interview type."""
    if not content:
        return "(none)"
    keys = ["company_facts", "mission_and_values"]
    keys += ["technical_topics", "technical_questions"] if kind == "technical" else ["hr_topics", "hr_questions"]
    lines = []
    for key in keys:
        # Source URLs stay in the fixture for traceability but aren't useful to the model.
        items = [re.sub(r"\s*\(https?://[^)]*\)", "", str(i)).strip() for i in content.get(key) or []]
        items = [i for i in items if i]
        if items:
            lines.append(key.replace("_", " ").capitalize() + ":")
            lines.extend(f"- {i}" for i in items)
    return "\n".join(lines) or "(none)"


def _clean_question(text: str) -> str:
    text = re.sub(r"^\s*(?:\*\*)?recruiter(?:\*\*)?\s*:\s*", "", text.strip(), flags=re.IGNORECASE)
    return text.strip().strip('"').strip()


class InterviewSession:
    def __init__(self, company, resume, job, content: dict | None = None, client=None,
                 kind: str = "technical", max_questions: int = 5):
        if kind not in KINDS:
            raise ValueError(f"kind must be one of {KINDS}, not {kind!r}")
        if not 1 <= max_questions <= 10:
            raise ValueError("max_questions must be between 1 and 10")
        self.company, self.resume, self.job = company, resume, job
        self.kind, self.max_questions = kind, max_questions
        self.client = client
        self.offline = client is None
        self.llm_error = ""
        self.history: list[tuple[str, str]] = []
        self._bank = question_bank.questions_for(kind)
        self._messages = [
            {"role": "system", "content": prompts.recruiter_system_prompt(kind, company.company_name, job.title)},
            {"role": "user", "content": prompts.context_message(
                company.to_prompt_text(), job.to_prompt_text(), resume.to_prompt_text(),
                content_to_text(content, kind), self._bank[0], max_questions)},
        ]
        self._current = self._next_question()

    # -- C++-style interface ------------------------------------------------------------

    def get_current_question(self) -> str:
        return self._current if self.has_more_questions() else ""

    def submit_answer(self, answer: str) -> None:
        if not self.has_more_questions():
            raise RuntimeError("The interview is already finished.")
        answer = (answer or "").strip()
        self.history.append((self._current, answer))
        if not self.has_more_questions():
            self._current = ""
            return
        self._messages.append({"role": "user", "content": prompts.answer_message(
            answer, len(self.history), self.max_questions)})
        self._current = self._next_question()

    def has_more_questions(self) -> bool:
        return len(self.history) < self.max_questions

    def get_question_count(self) -> int:
        return self.max_questions

    def evaluate_interview(self) -> dict:
        if not self.offline:
            try:
                return generate_feedback(self.client, self.history, self.kind, self.company.company_name,
                                         self.job.title, self.job.to_prompt_text())
            except LLMError as exc:
                self.llm_error = str(exc)
        return self._offline_result()

    # -- internals ----------------------------------------------------------------------

    def _next_question(self) -> str:
        if not self.offline:
            try:
                question = _clean_question(self.client.chat(self._messages, temperature=0.6, max_tokens=1024))
                if question:
                    self._messages.append({"role": "assistant", "content": question})
                    return question
                raise LLMError("The model returned an empty question.")
            except LLMError as exc:
                self.offline, self.llm_error = True, str(exc)
        question = self._bank[len(self.history) % len(self._bank)]
        self._messages.append({"role": "assistant", "content": question})
        return question

    def _offline_result(self) -> dict:
        result = {key: [] for key in FEEDBACK_KEYS}
        result.update({"communication": "", "relevance": "", "examples": ""})
        result.update(question_bank.offline_evaluation([a for _, a in self.history]))
        return result
