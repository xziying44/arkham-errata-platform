from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/arkham_errata"
    cors_origin: str = "http://localhost:5173"
    project_root: Path = Path(__file__).parent.parent.parent


settings = Settings()
