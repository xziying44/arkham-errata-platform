from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/arkham_errata"
    secret_key: str = "change-me-in-production"
    access_token_expire_minutes: int = 480
    project_root: Path = Path(__file__).parent.parent.parent
    local_card_db: Path = Path("卡牌数据库")
    sced_downloads: Path = Path("SCED-downloads/decomposed")
    cache_dir: Path = Path("data/cache")
    arkham_card_maker_home: str = ""

    class Config:
        env_file = ".env"

settings = Settings()
