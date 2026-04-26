from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/arkham_errata"
    cors_origin: str = "http://localhost:5173"
    project_root: Path = Path(__file__).parent.parent.parent
    secret_key: str = "change-me-in-production"
    access_token_expire_minutes: int = 480
    local_card_db: Path = Path("../卡牌数据库")
    sced_downloads: Path = Path("../SCED-downloads")
    sced_repo: Path = Path("../SCED")
    cache_dir: Path = Path("data/cache")
    data_repo_sync_enabled: bool = False
    data_repo_sync_interval_minutes: int = 60
    git_executable: str = "git"


settings = Settings()
