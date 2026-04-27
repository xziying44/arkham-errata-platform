"""将已发布勘误写回本地卡牌数据库。"""

import hashlib
import json
import os
import subprocess
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.card import LocalCardFile
from app.models.errata_draft import ErrataDraft, ErrataPackage


def _card_database_root() -> Path:
    return (settings.project_root / settings.local_card_db).resolve()


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail=f"卡牌数据库文件 JSON 无法解析：{path}") from exc


def _merge_preserving_picture(original: dict, modified: dict) -> dict:
    if not isinstance(modified, dict):
        return modified
    if modified.get("picture_base64"):
        return modified
    if isinstance(original, dict) and original.get("picture_base64"):
        return {**modified, "picture_base64": original["picture_base64"]}
    return modified


def _write_card_file(path: Path, content: dict) -> tuple[str, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(content, ensure_ascii=False, indent=2) + "\n"
    path.write_text(payload, encoding="utf-8")
    content_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    last_modified = str(os.path.getmtime(str(path)))
    return content_hash, last_modified


def _run_git(card_root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [settings.git_executable, "-C", str(card_root), *args],
        check=True,
        text=True,
        capture_output=True,
    )


def _commit_card_database(card_root: Path, relative_paths: list[str], package_no: str) -> str | None:
    try:
        _run_git(card_root, ["rev-parse", "--is-inside-work-tree"])
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise HTTPException(status_code=500, detail="卡牌数据库目录不是可提交的 git 仓库") from exc

    if not relative_paths:
        return None

    _run_git(card_root, ["add", *relative_paths])
    diff = _run_git(card_root, ["diff", "--cached", "--name-only"])
    if not diff.stdout.strip():
        return None

    message = f"发布勘误包 {package_no}"
    _run_git(
        card_root,
        [
            "-c",
            "user.name=xziying",
            "-c",
            "user.email=xziying@vip.qq.com",
            "commit",
            "-m",
            message,
        ],
    )
    head = _run_git(card_root, ["rev-parse", "--short", "HEAD"])
    return head.stdout.strip()


async def publish_package_to_card_database(db: AsyncSession, package: ErrataPackage, drafts: list[ErrataDraft]) -> dict:
    card_root = _card_database_root()
    written_paths: list[str] = []

    for draft in drafts:
        result = await db.execute(
            select(LocalCardFile)
            .where(LocalCardFile.arkhamdb_id == draft.arkhamdb_id)
            .order_by(LocalCardFile.face)
        )
        files_by_face = {record.face: record for record in result.scalars().all()}
        for face, modified in sorted((draft.modified_faces or {}).items()):
            file_record = files_by_face.get(face)
            if file_record is None:
                raise HTTPException(status_code=409, detail=f"{draft.arkhamdb_id} 缺少 {face} 面本地 .card 文件，不能写回卡牌数据库")
            target_path = card_root / file_record.relative_path
            if not target_path.exists():
                raise HTTPException(status_code=409, detail=f"本地卡牌文件不存在：{file_record.relative_path}")
            original = _read_json(target_path)
            next_content = _merge_preserving_picture(original, modified)
            content_hash, last_modified = _write_card_file(target_path, next_content)
            file_record.content_hash = content_hash
            file_record.last_modified = last_modified
            written_paths.append(file_record.relative_path)

    unique_paths = sorted(set(written_paths))
    commit = _commit_card_database(card_root, unique_paths, package.package_no)
    return {"written_files": unique_paths, "commit": commit}
