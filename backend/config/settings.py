import os
import pathlib

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load backend/.env into os.environ so provider SDKs (Mistral, Anthropic, Tavily) that
# read os.environ directly pick up the keys. `langgraph dev` does this via langgraph.json's
# "env" field; other entrypoints (uvicorn API gateway, run_evals, CLI) need it done here.
# override=True so .env is authoritative over any stale shell/conda env var of the same name.
try:
    from dotenv import load_dotenv

    load_dotenv(pathlib.Path(__file__).resolve().parents[1] / ".env", override=True)
except ImportError:
    pass


def _load_env_yaml() -> dict:
    """Load the environment-specific yaml config as field defaults.

    Priority for BACKEND_ENV: OS environment variable > .env file > "dev"
    The yaml values become the lowest-priority defaults — .env and env vars override them.
    """
    try:
        from dotenv import dotenv_values
        env_name = os.getenv("BACKEND_ENV") or dotenv_values(".env").get("BACKEND_ENV", "dev")
    except ImportError:
        env_name = os.getenv("BACKEND_ENV", "dev")

    yaml_path = pathlib.Path(__file__).parent / "environments" / f"{env_name}.yaml"
    if not yaml_path.exists():
        return {}

    try:
        import yaml
        with open(yaml_path) as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        return {}


_env = _load_env_yaml()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Core — read from environment yaml first, then overridden by .env / env vars
    backend_model: str = _env.get("backend_model", "anthropic:claude-opus-4-8")
    backend_env: str = _env.get("backend_env", "dev")
    summarization_model: str = _env.get("summarization_model", "")
    hitl_channel: str = _env.get("hitl_channel", "cli")

    @model_validator(mode="after")
    def _default_summarization_model(self) -> "Settings":
        if not self.summarization_model:
            self.summarization_model = self.backend_model
        return self

    # Provider keys — set whichever matches BACKEND_MODEL; others can be empty.
    # init_chat_model() picks up the right key automatically from the environment.
    anthropic_api_key: str = ""
    groq_api_key: str = ""
    mistral_api_key: str = ""

    langsmith_api_key: str = ""
    langsmith_tracing: bool = False

    tavily_api_key: str = ""
    # Canonical operational DB built by src/data_pipeline/build_gold_layer.py at repo root.
    # settings.py = backend/config/settings.py → parents[2] = repo root.
    duckdb_path: str = str(
        pathlib.Path(__file__).resolve().parents[2] / "data" / "database" / "operational_twin.db"
    )

    hitl_enabled: bool = True
    eval_budget_usd: float = 5.0


settings = Settings()
