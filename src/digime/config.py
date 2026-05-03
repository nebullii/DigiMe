from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    env: str = "development"
    draft_only: bool = True
    llm_provider: str = "ollama"
    llm_model: str = "qwen2.5:7b-instruct"
    llm_base_url: str = "http://127.0.0.1:11434"
    database_url: str = "sqlite:///./digime.sqlite3"
    vector_dir: str = "./data/processed/vector"

    model_config = SettingsConfigDict(env_prefix="DIGIME_", env_file=".env", extra="ignore")


settings = Settings()

