from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Database
    db_host: str = "localhost"
    db_port: int = 5432
    db_user: str = "civ_user"
    db_password: str = "civ_pass"
    db_name: str = "civ_db"

    # Azure OpenAI
    azure_openai_key: str = ""
    azure_openai_endpoint: str = ""
    azure_openai_deployment_name: str = "gpt-4o"
    azure_openai_api_version: str = "2024-02-01"

    # AI feature flags
    # Set ai_enabled=true in .env to activate LLM features.
    # All AI features degrade gracefully when disabled.
    ai_enabled: bool = False
    ai_max_calls_per_run: int = 3       # cap on decision-support calls per turn
    ai_summary_enabled: bool = True     # narrative summaries for multi-turn runs
    ai_ask_agent_enabled: bool = True   # in-character agent answers

    # App
    app_env: str = "development"
    log_level: str = "INFO"
    allowed_origins: str = (
        "http://localhost:3000,"
        "http://127.0.0.1:3000,"
        "http://localhost:5173,"
        "http://127.0.0.1:5173"
    )

    # Simulation
    autoplay_max_turns: int = 20

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def database_url_sync(self) -> str:
        """Sync URL for Alembic migrations."""
        return (
            f"postgresql+psycopg2://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"


settings = Settings()