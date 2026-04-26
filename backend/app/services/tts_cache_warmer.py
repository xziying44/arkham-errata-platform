"""TTS 卡图后台缓存预热服务。"""

import asyncio
from dataclasses import dataclass, asdict
from pathlib import Path
from time import monotonic

from sqlalchemy import select

from app.config import settings
from app.database import async_session
from app.models.card import LocalCardFile, TTSCardImage
from app.services.image_cache import download_and_cut_sheet


@dataclass
class CacheWarmStatus:
    """后台缓存预热运行状态。"""

    running: bool = False
    total: int = 0
    done: int = 0
    failed: int = 0
    skipped: int = 0
    current: str | None = None
    started_at: float | None = None
    finished_at: float | None = None
    last_error: str | None = None


_status = CacheWarmStatus()
_task: asyncio.Task | None = None
_stop_event: asyncio.Event | None = None


def get_cache_warm_status() -> dict:
    """返回当前缓存预热状态，供接口展示。"""
    return asdict(_status)


def _cache_path_exists(relative_path: str | None) -> bool:
    if not relative_path:
        return False
    return (settings.project_root / relative_path).exists()


def _side_cache_target(tts: TTSCardImage, side: str) -> tuple[str, str] | None:
    sheet_url = tts.face_url if side == "front" else tts.back_url
    cached_path = tts.cached_front_path if side == "front" else tts.cached_back_path
    if not sheet_url or _cache_path_exists(cached_path):
        return None
    return side, sheet_url


async def _load_targets() -> list[tuple[int, str, str, int, int, int, str, str]]:
    """读取所有与本地 .card 相关且尚未缓存的 TTS 图片任务。"""
    async with async_session() as db:
        result = await db.execute(
            select(TTSCardImage)
            .join(LocalCardFile, LocalCardFile.arkhamdb_id == TTSCardImage.arkhamdb_id)
            .order_by(TTSCardImage.source, TTSCardImage.arkhamdb_id, TTSCardImage.id)
        )
        targets: list[tuple[int, str, str, int, int, int, str, str]] = []
        for tts in result.scalars().unique().all():
            for side in ("front", "back"):
                side_target = _side_cache_target(tts, side)
                if not side_target:
                    continue
                _, sheet_url = side_target
                targets.append((
                    tts.id,
                    side,
                    sheet_url,
                    tts.grid_position,
                    tts.grid_width,
                    tts.grid_height,
                    f"{tts.source}_{tts.id}_{side}",
                    f"{tts.source} {tts.arkhamdb_id} {side}",
                ))
        return targets


async def _save_cache_path(tts_id: int, side: str, generated_path: str) -> None:
    """把生成后的缓存路径写回数据库。"""
    relative_path = str(Path(generated_path).relative_to(settings.project_root))
    async with async_session() as db:
        tts = await db.get(TTSCardImage, tts_id)
        if not tts:
            return
        if side == "front":
            tts.cached_front_path = relative_path
        else:
            tts.cached_back_path = relative_path
        await db.commit()


async def warm_tts_cache(stop_event: asyncio.Event) -> None:
    """后台预热 TTS 图片缓存。"""
    global _status
    if _status.running:
        return

    _status = CacheWarmStatus(running=True, started_at=monotonic())
    cache_dir = settings.project_root / settings.cache_dir / "tts"
    try:
        try:
            targets = await _load_targets()
        except Exception as exc:  # noqa: BLE001 - 启动阶段也要把错误暴露到状态接口
            _status.failed += 1
            _status.last_error = f"加载缓存任务失败：{exc}"
            return
        _status.total = len(targets)
        if not targets:
            return

        semaphore = asyncio.Semaphore(settings.tts_cache_warm_workers)

        async def run_target(target: tuple[int, str, str, int, int, int, str, str]) -> None:
            tts_id, side, sheet_url, grid_position, grid_width, grid_height, cache_key, label = target
            if stop_event.is_set():
                _status.skipped += 1
                return
            async with semaphore:
                _status.current = label
                try:
                    generated_path = await asyncio.to_thread(
                        download_and_cut_sheet,
                        sheet_url=sheet_url,
                        grid_position=grid_position,
                        grid_width=grid_width,
                        grid_height=grid_height,
                        cache_dir=cache_dir,
                        cache_key=cache_key,
                    )
                    if generated_path:
                        await _save_cache_path(tts_id, side, generated_path)
                        _status.done += 1
                    else:
                        _status.failed += 1
                        _status.last_error = f"缓存失败：{label}"
                except Exception as exc:  # noqa: BLE001 - 后台任务需要记录错误并继续
                    _status.failed += 1
                    _status.last_error = f"{label}: {exc}"

        await asyncio.gather(*(run_target(target) for target in targets))
    finally:
        _status.running = False
        _status.current = None
        _status.finished_at = monotonic()


def start_tts_cache_warmer() -> asyncio.Task | None:
    """启动后台缓存预热任务；已运行时直接返回现有任务。"""
    global _task, _stop_event
    if _task and not _task.done():
        return _task
    _stop_event = asyncio.Event()
    _task = asyncio.create_task(warm_tts_cache(_stop_event))
    return _task


async def stop_tts_cache_warmer() -> None:
    """请求后台缓存预热任务停止。"""
    if _stop_event:
        _stop_event.set()
    if _task:
        await asyncio.wait([_task], timeout=5)
