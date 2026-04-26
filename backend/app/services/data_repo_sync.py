"""数据源 Git 仓库同步服务。"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DataRepo:
    name: str
    path: Path


def configured_data_repos() -> list[DataRepo]:
    """返回需要跟随远程强制同步的数据源仓库。"""
    return [
        DataRepo("卡牌数据库", settings.project_root / settings.local_card_db),
        DataRepo("SCED-downloads", settings.project_root / settings.sced_downloads),
        DataRepo("SCED", settings.project_root / settings.sced_repo),
    ]


async def _run_git(repo: DataRepo, *args: str) -> str:
    process = await asyncio.create_subprocess_exec(
        settings.git_executable,
        *args,
        cwd=repo.path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    output = (stdout + stderr).decode("utf-8", errors="replace")
    if process.returncode != 0:
        raise RuntimeError(f"{repo.name} 执行 git {' '.join(args)} 失败：{output.strip()}")
    return output.strip()


async def sync_data_repo(repo: DataRepo) -> dict[str, str]:
    """将单个数据源仓库强制重置到当前分支的远程跟踪分支。"""
    if not repo.path.exists():
        return {"name": repo.name, "path": str(repo.path), "status": "missing"}
    git_dir = repo.path / ".git"
    if not git_dir.exists():
        return {"name": repo.name, "path": str(repo.path), "status": "not_git_repo"}

    await _run_git(repo, "fetch", "--prune")
    upstream = await _run_git(repo, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    before = await _run_git(repo, "rev-parse", "HEAD")
    await _run_git(repo, "reset", "--hard", upstream)
    after = await _run_git(repo, "rev-parse", "HEAD")
    return {
        "name": repo.name,
        "path": str(repo.path),
        "status": "synced",
        "upstream": upstream,
        "before": before,
        "after": after,
    }


async def sync_all_data_repos() -> list[dict[str, str]]:
    """同步全部配置的数据源仓库。"""
    results: list[dict[str, str]] = []
    for repo in configured_data_repos():
        try:
            results.append(await sync_data_repo(repo))
        except Exception as exc:
            logger.exception("同步数据仓库失败：%s", repo.name)
            results.append({"name": repo.name, "path": str(repo.path), "status": "error", "error": str(exc)})
    return results


async def periodic_data_repo_sync(stop_event: asyncio.Event) -> None:
    """按固定间隔同步数据源仓库，默认由配置关闭。"""
    while not stop_event.is_set():
        await sync_all_data_repos()
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=settings.data_repo_sync_interval_minutes * 60)
        except asyncio.TimeoutError:
            continue
