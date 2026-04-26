import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.api import auth, cards, errata, review, publish, mapping
from app.services.data_repo_sync import periodic_data_repo_sync

@asynccontextmanager
async def lifespan(app: FastAPI):
    stop_event = asyncio.Event()
    sync_task: asyncio.Task | None = None
    if settings.data_repo_sync_enabled:
        sync_task = asyncio.create_task(periodic_data_repo_sync(stop_event))
    try:
        yield
    finally:
        stop_event.set()
        if sync_task:
            await sync_task


app = FastAPI(title="卡牌勘误平台", version="0.1.0", lifespan=lifespan)
app.include_router(auth.router)
app.include_router(cards.router)
app.include_router(errata.router)
app.include_router(review.router)
app.include_router(publish.router)
app.include_router(mapping.router)

# 挂载缓存静态文件目录
cache_dir = settings.project_root / settings.cache_dir
cache_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static/cache", StaticFiles(directory=str(cache_dir)), name="cache")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.cors_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health():
    return {"status": "ok"}
