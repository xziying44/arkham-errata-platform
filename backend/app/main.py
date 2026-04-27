import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.api import auth, cards, errata, review, publish, mapping, errata_drafts, packages
from app.services.data_repo_sync import periodic_data_repo_sync
from app.services.local_card_index import build_local_card_index
from app.services.tts_cache_warmer import start_tts_cache_warmer, stop_tts_cache_warmer

@asynccontextmanager
async def lifespan(app: FastAPI):
    stop_event = asyncio.Event()
    sync_task: asyncio.Task | None = None
    try:
        await asyncio.to_thread(build_local_card_index, settings.project_root / settings.local_card_db)
    except Exception as exc:
        print(f"本地卡牌内容索引构建失败，将在首次请求时重试：{exc}")
    if settings.data_repo_sync_enabled:
        sync_task = asyncio.create_task(periodic_data_repo_sync(stop_event))
    if settings.tts_cache_warm_enabled:
        start_tts_cache_warmer()
    try:
        yield
    finally:
        stop_event.set()
        await stop_tts_cache_warmer()
        if sync_task:
            await sync_task


app = FastAPI(title="卡牌勘误平台", version="0.1.0", lifespan=lifespan)
app.include_router(auth.router)
app.include_router(cards.router)
app.include_router(errata.router)
app.include_router(review.router)
app.include_router(publish.router)
app.include_router(mapping.router)
app.include_router(errata_drafts.router)
app.include_router(packages.router)

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
