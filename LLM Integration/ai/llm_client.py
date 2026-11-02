"""Reusable client for the NRP OpenAI-compatible LLM API.

One LLMClient wraps one OpenAI SDK connection; share it across features instead
of creating a new connection per request. Configuration comes from environment
variables (loaded from hackathon_resume_project/.env via python-dotenv).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import openai
from dotenv import load_dotenv

DEFAULT_BASE_URL = "https://ellm.nrp-nautilus.io/v1"
DEFAULT_MODEL = "gpt-oss"
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class ConfigError(RuntimeError):
    """Missing or invalid configuration (e.g. no API key)."""


class LLMError(RuntimeError):
    """The LLM API call failed or returned an unusable response."""


@dataclass(frozen=True)
class LLMConfig:
    api_key: str
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    timeout: float = 120.0
    max_retries: int = 2

    def __repr__(self) -> str:  # never leak the key in logs/tracebacks
        return (f"LLMConfig(base_url={self.base_url!r}, model={self.model!r}, "
                f"timeout={self.timeout}, max_retries={self.max_retries})")


def load_config(env_file: str | os.PathLike | None = ENV_FILE) -> LLMConfig:
    """Build an LLMConfig from NRP_* environment variables.

    Values already set in the process environment win over the .env file.
    """
    if env_file is not None:
        load_dotenv(env_file, override=False)
    api_key = os.getenv("NRP_API_KEY", "").strip()
    if not api_key or api_key == "your_api_key_here":
        raise ConfigError(
            "NRP_API_KEY is not set. Copy .env.example to .env and add your key.")
    try:
        timeout = float(os.getenv("NRP_TIMEOUT", "120"))
        max_retries = int(os.getenv("NRP_MAX_RETRIES", "2"))
    except ValueError as exc:
        raise ConfigError(f"NRP_TIMEOUT / NRP_MAX_RETRIES must be numbers: {exc}") from exc
    if not timeout > 0 or max_retries < 0:  # `not >` also rejects NaN
        raise ConfigError("NRP_TIMEOUT must be > 0 and NRP_MAX_RETRIES must be >= 0.")
    return LLMConfig(
        api_key=api_key,
        base_url=os.getenv("NRP_BASE_URL", "").strip() or DEFAULT_BASE_URL,
        model=os.getenv("NRP_MODEL", "").strip() or DEFAULT_MODEL,
        timeout=timeout,
        max_retries=max_retries,
    )


class LLMClient:
    def __init__(self, config: LLMConfig | None = None, *, sdk_client=None):
        self.config = config or load_config()
        # The SDK handles timeouts and retries (with backoff) on connection
        # errors, 408/409/429 and 5xx responses.
        self._client = sdk_client or openai.OpenAI(
            api_key=self.config.api_key,
            base_url=self.config.base_url,
            timeout=self.config.timeout,
            max_retries=self.config.max_retries,
        )

    @property
    def model(self) -> str:
        return self.config.model

    def list_models(self) -> list[str]:
        try:
            return sorted(m.id for m in self._client.models.list())
        except openai.OpenAIError as exc:
            raise LLMError(_describe(exc, "listing models")) from exc

    def check_model(self) -> None:
        """Raise LLMError if the configured model is not offered by the API.

        We never switch to another model silently; the caller decides.
        """
        available = self.list_models()
        if self.model not in available:
            raise LLMError(
                f"Model {self.model!r} is not available. Set NRP_MODEL to one of: "
                + ", ".join(available))

    def chat(self, messages: list[dict], *, temperature: float | None = None,
             max_tokens: int | None = None, **extra) -> str:
        """Send a chat completion and return the assistant's text content."""
        if "model" in extra:
            raise TypeError("chat() always uses the configured model; set NRP_MODEL to change it.")
        params = {**extra, "model": self.model, "messages": messages}
        if temperature is not None:
            params["temperature"] = temperature
        if max_tokens is not None:
            params["max_tokens"] = max_tokens
        try:
            response = self._client.chat.completions.create(**params)
        except openai.OpenAIError as exc:
            raise LLMError(_describe(exc, "chat completion")) from exc
        if not response.choices:
            raise LLMError("The model returned no choices.")
        choice = response.choices[0]
        content = (choice.message.content or "").strip()
        if not content:
            # Reasoning models can spend the whole token budget "thinking".
            hint = " (hit max_tokens; raise it)" if choice.finish_reason == "length" else ""
            raise LLMError(f"The model returned an empty response{hint}.")
        return content


def _describe(exc: openai.OpenAIError, action: str) -> str:
    if isinstance(exc, openai.AuthenticationError):
        return f"NRP API rejected the API key while {action}. Check NRP_API_KEY."
    if isinstance(exc, openai.NotFoundError):
        return f"NRP API returned 404 while {action}. Check NRP_BASE_URL and NRP_MODEL."
    if isinstance(exc, openai.RateLimitError):
        return f"NRP API rate limit hit while {action}; retries exhausted."
    if isinstance(exc, openai.APITimeoutError):
        return f"NRP API timed out while {action}."
    if isinstance(exc, openai.APIConnectionError):
        return f"Could not connect to the NRP API while {action}."
    if isinstance(exc, openai.APIStatusError):
        return f"NRP API error {exc.status_code} while {action}: {exc.message}"
    return f"NRP API error while {action}: {exc}"
