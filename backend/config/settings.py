from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    backend_model: str = "anthropic:claude-opus-4-8"
    backend_env: str = "dev"

    # Provider keys — set whichever matches BACKEND_MODEL; others can be empty.
    # init_chat_model() picks up the right key automatically from the environment.
    anthropic_api_key: str = ""
    groq_api_key: str = ""
    mistral_api_key: str = ""

    langsmith_api_key: str = ""
    langsmith_tracing: bool = False
    hitl_enabled: bool = True
    eval_budget_usd: float = 5.0


settings = Settings()
