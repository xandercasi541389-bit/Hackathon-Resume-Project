"""Optional integration test against the real NRP API (uses quota).

Opt-in only: RUN_LIVE_TESTS=1 .venv/bin/python -m pytest tests/test_live_api.py -v
"""

import os

import pytest

from ai import ConfigError, LLMClient, load_config

CONFIG = None
if os.getenv("RUN_LIVE_TESTS") == "1":
    try:
        CONFIG = load_config()
    except ConfigError:
        pass

pytestmark = pytest.mark.skipif(
    CONFIG is None, reason="set RUN_LIVE_TESTS=1 and NRP_API_KEY to run live API tests")


def test_live_model_is_available():
    LLMClient(CONFIG).check_model()


def test_live_basic_completion():
    reply = LLMClient(CONFIG).chat(
        [{"role": "user", "content": "Reply with the single word: ready"}], max_tokens=2048)
    assert "ready" in reply.lower()
