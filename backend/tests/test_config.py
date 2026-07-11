"""Unit tests for config — no API calls."""
from pydantic_settings import SettingsConfigDict

from config.settings import Settings


class _TestSettings(Settings):
    """Settings subclass that never reads .env — for isolated unit tests."""
    model_config = SettingsConfigDict(env_file=None, extra="ignore")


def test_summarization_model_defaults_to_backend_model():
    s = _TestSettings(backend_model="anthropic:claude-opus-4-8", summarization_model="")
    assert s.summarization_model == "anthropic:claude-opus-4-8"


def test_summarization_model_explicit_override():
    s = _TestSettings(
        backend_model="anthropic:claude-opus-4-8",
        summarization_model="anthropic:claude-haiku-4-5",
    )
    assert s.summarization_model == "anthropic:claude-haiku-4-5"


def test_summarization_model_not_overridden_when_set():
    s = _TestSettings(
        backend_model="groq:llama-3.3-70b-versatile",
        summarization_model="groq:llama-3.1-8b-instant",
    )
    assert s.summarization_model == "groq:llama-3.1-8b-instant"


def test_eval_budget_default():
    s = _TestSettings()
    assert s.eval_budget_usd == 5.0


def test_hitl_enabled_default():
    s = _TestSettings()
    assert s.hitl_enabled is True


def test_duckdb_path_default():
    s = _TestSettings()
    # Default points at the built gold-layer DB (may be absolute or repo-relative).
    assert s.duckdb_path.replace("\\", "/").endswith("data/database/operational_twin.db")
