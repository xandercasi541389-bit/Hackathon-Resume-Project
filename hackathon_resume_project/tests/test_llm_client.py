"""LLM client tests with a mocked SDK; no network."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx2
import openai
import pytest

from ai import ConfigError, LLMClient, LLMConfig, LLMError, load_config

CONFIG = LLMConfig(api_key="test-key", model="gpt-oss")


@pytest.fixture
def clean_env(monkeypatch):
    for var in ("NRP_API_KEY", "NRP_BASE_URL", "NRP_MODEL", "NRP_TIMEOUT", "NRP_MAX_RETRIES"):
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


def completion(content, finish_reason="stop"):
    message = SimpleNamespace(content=content)
    return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason=finish_reason)])


def api_error(cls, status):
    request = httpx2.Request("POST", "https://example.test/v1/chat/completions")
    response = httpx2.Response(status, request=request)
    return cls("boom", response=response, body=None)


def test_load_config_from_env(clean_env):
    clean_env.setenv("NRP_API_KEY", "abc")
    clean_env.setenv("NRP_MODEL", "some-model")
    clean_env.setenv("NRP_TIMEOUT", "5")
    config = load_config(env_file=None)
    assert config.api_key == "abc"
    assert config.model == "some-model"
    assert config.timeout == 5.0
    assert config.base_url == "https://ellm.nrp-nautilus.io/v1"


def test_load_config_from_env_file(clean_env, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("NRP_API_KEY=from-file\nNRP_MODEL=file-model\n")
    config = load_config(env_file=env_file)
    assert (config.api_key, config.model) == ("from-file", "file-model")


@pytest.mark.parametrize("value", [None, "", "your_api_key_here"])
def test_missing_api_key_raises(clean_env, value):
    if value is not None:
        clean_env.setenv("NRP_API_KEY", value)
    with pytest.raises(ConfigError, match="NRP_API_KEY"):
        load_config(env_file=None)


def test_config_repr_hides_key():
    assert "test-key" not in repr(CONFIG)


def test_client_init_uses_config():
    client = LLMClient(CONFIG)
    assert client.model == "gpt-oss"
    assert str(client._client.base_url).startswith("https://ellm.nrp-nautilus.io/v1")
    assert client._client.max_retries == 2


def test_chat_returns_content_and_passes_params():
    sdk = MagicMock()
    sdk.chat.completions.create.return_value = completion("  Hello!  ")
    client = LLMClient(CONFIG, sdk_client=sdk)
    messages = [{"role": "user", "content": "hi"}]
    assert client.chat(messages, temperature=0.2, max_tokens=50) == "Hello!"
    sdk.chat.completions.create.assert_called_once_with(
        model="gpt-oss", messages=messages, temperature=0.2, max_tokens=50)


def test_chat_empty_content_raises():
    sdk = MagicMock()
    sdk.chat.completions.create.return_value = completion(None, finish_reason="length")
    with pytest.raises(LLMError, match="max_tokens"):
        LLMClient(CONFIG, sdk_client=sdk).chat([{"role": "user", "content": "hi"}])


@pytest.mark.parametrize("error, expected", [
    (api_error(openai.AuthenticationError, 401), "API key"),
    (api_error(openai.RateLimitError, 429), "rate limit"),
    (api_error(openai.InternalServerError, 500), "500"),
    (openai.APIConnectionError(request=httpx2.Request("POST", "https://x")), "connect"),
])
def test_chat_api_failures_raise_llm_error(error, expected):
    sdk = MagicMock()
    sdk.chat.completions.create.side_effect = error
    with pytest.raises(LLMError, match=expected):
        LLMClient(CONFIG, sdk_client=sdk).chat([{"role": "user", "content": "hi"}])


def test_list_models_and_check_model():
    sdk = MagicMock()
    sdk.models.list.return_value = [SimpleNamespace(id="b-model"), SimpleNamespace(id="gpt-oss")]
    client = LLMClient(CONFIG, sdk_client=sdk)
    assert client.list_models() == ["b-model", "gpt-oss"]
    client.check_model()  # no error


def test_check_model_does_not_fall_back():
    sdk = MagicMock()
    sdk.models.list.return_value = [SimpleNamespace(id="other-model")]
    client = LLMClient(CONFIG, sdk_client=sdk)
    with pytest.raises(LLMError, match="other-model"):
        client.check_model()
    assert client.model == "gpt-oss"


def test_chat_rejects_model_override():
    sdk = MagicMock()
    with pytest.raises(TypeError, match="NRP_MODEL"):
        LLMClient(CONFIG, sdk_client=sdk).chat([{"role": "user", "content": "hi"}], model="other")
    sdk.chat.completions.create.assert_not_called()


@pytest.mark.parametrize("var, value", [
    ("NRP_TIMEOUT", "0"), ("NRP_TIMEOUT", "nan"), ("NRP_TIMEOUT", "abc"), ("NRP_MAX_RETRIES", "-1"),
])
def test_invalid_numeric_config_raises(clean_env, var, value):
    clean_env.setenv("NRP_API_KEY", "abc")
    clean_env.setenv(var, value)
    with pytest.raises(ConfigError):
        load_config(env_file=None)
