from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    env: str = Field("development", validation_alias=AliasChoices("DIGIME_ENV", "ENV"))
    draft_only: bool = Field(True, validation_alias=AliasChoices("DIGIME_DRAFT_ONLY", "DRAFT_ONLY"))
    llm_provider: str = Field("ollama", validation_alias="DIGIME_LLM_PROVIDER")
    llm_model: str = Field("qwen3:latest", validation_alias="DIGIME_LLM_MODEL")
    llm_base_url: str = Field("http://127.0.0.1:11434", validation_alias="DIGIME_LLM_BASE_URL")
    database_url: str = Field("sqlite:///./digime.sqlite3", validation_alias="DIGIME_DATABASE_URL")
    vector_dir: str = Field("./data/processed/vector", validation_alias="DIGIME_VECTOR_DIR")
    slack_bot_token: str | None = Field(None, validation_alias="SLACK_BOT_TOKEN")
    slack_user_token: str | None = Field(None, validation_alias="SLACK_USER_TOKEN")
    slack_your_user_id: str | None = Field(None, validation_alias="SLACK_YOUR_USER_ID")
    discord_bot_token: str | None = Field(None, validation_alias="DISCORD_BOT_TOKEN")
    discord_default_channel_id: str | None = Field(
        None,
        validation_alias="DISCORD_DEFAULT_CHANNEL_ID",
    )

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def slack_token(self) -> str | None:
        return self.slack_user_token or self.slack_bot_token


settings = Settings()
