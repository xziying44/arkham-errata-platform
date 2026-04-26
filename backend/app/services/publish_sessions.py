"""发布会话服务：管理发布尝试和产物索引。"""

import hashlib
import json
import uuid
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.errata_draft import (
    ErrataPackage,
    ErrataPackageStatus,
    PublishArtifact,
    PublishArtifactKind,
    PublishArtifactStatus,
    PublishSession,
    PublishSessionStatus,
)
from app.models.user import User

ACTIVE_SESSION_STATUSES = {
    PublishSessionStatus.DRAFT,
    PublishSessionStatus.GENERATING,
    PublishSessionStatus.SHEETS_READY,
    PublishSessionStatus.URLS_READY,
    PublishSessionStatus.PATCH_READY,
    PublishSessionStatus.FAILED,
}


def artifact_public_url(path: str) -> str | None:
    cache_root = settings.project_root / settings.cache_dir
    absolute = settings.project_root / path
    try:
        relative = absolute.relative_to(cache_root)
    except ValueError:
        return None
    return f"/static/cache/{relative.as_posix()}"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


async def create_publish_session(db: AsyncSession, package_id: int, admin: User) -> PublishSession:
    package = await db.get(ErrataPackage, package_id)
    if package is None:
        raise HTTPException(status_code=404, detail="勘误包不存在")
    if package.status != ErrataPackageStatus.WAITING_PUBLISH:
        raise HTTPException(status_code=409, detail="只有待发布勘误包可以创建发布会话")

    existing = await db.execute(
        select(PublishSession)
        .where(PublishSession.package_id == package_id)
        .where(PublishSession.status.in_(ACTIVE_SESSION_STATUSES))
    )
    if existing.scalars().first() is not None:
        raise HTTPException(status_code=409, detail="当前勘误包已有未完成发布会话")

    session_key = uuid.uuid4().hex[:12]
    artifact_root = settings.cache_dir / "publish" / package.package_no / session_key
    absolute_root = settings.project_root / artifact_root
    absolute_root.mkdir(parents=True, exist_ok=True)

    session = PublishSession(
        package_id=package.id,
        status=PublishSessionStatus.DRAFT,
        current_step="select_package",
        artifact_root=artifact_root.as_posix(),
        created_by=admin.id,
        updated_by=admin.id,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


async def load_publish_session(db: AsyncSession, session_id: int) -> PublishSession:
    session = await db.get(PublishSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="发布会话不存在")
    return session


async def list_session_artifacts(db: AsyncSession, session_id: int) -> list[PublishArtifact]:
    result = await db.execute(select(PublishArtifact).where(PublishArtifact.session_id == session_id).order_by(PublishArtifact.id))
    return list(result.scalars().all())


async def add_artifact(
    db: AsyncSession,
    session: PublishSession,
    kind: PublishArtifactKind,
    path: Path,
    metadata: dict,
    status: PublishArtifactStatus = PublishArtifactStatus.ACTIVE,
) -> PublishArtifact:
    relative_path = path.relative_to(settings.project_root).as_posix()
    artifact = PublishArtifact(
        session_id=session.id,
        kind=kind,
        status=status,
        path=relative_path,
        public_url=artifact_public_url(relative_path),
        checksum=file_sha256(path) if path.exists() and path.is_file() else None,
        artifact_metadata=metadata,
    )
    db.add(artifact)
    await db.flush()
    return artifact


async def supersede_artifacts_after_step(db: AsyncSession, session_id: int, kinds: set[PublishArtifactKind]) -> None:
    result = await db.execute(
        select(PublishArtifact)
        .where(PublishArtifact.session_id == session_id)
        .where(PublishArtifact.kind.in_(kinds))
        .where(PublishArtifact.status.in_({PublishArtifactStatus.ACTIVE, PublishArtifactStatus.CONFIRMED}))
    )
    for artifact in result.scalars().all():
        artifact.status = PublishArtifactStatus.SUPERSEDED


STEP_ARTIFACTS: dict[str, set[PublishArtifactKind]] = {
    "confirm_sheets": {PublishArtifactKind.URL_MAPPING, PublishArtifactKind.TTS_BAG, PublishArtifactKind.PATCH_ZIP, PublishArtifactKind.MANIFEST, PublishArtifactKind.REPORT},
    "prepare_urls": {PublishArtifactKind.PATCH_ZIP, PublishArtifactKind.MANIFEST, PublishArtifactKind.REPORT},
}


async def import_url_mapping(
    db: AsyncSession,
    session: PublishSession,
    source: str,
    url_mapping: dict[str, dict],
) -> PublishArtifact:
    mapping_dir = settings.project_root / session.artifact_root / "mappings"
    mapping_dir.mkdir(parents=True, exist_ok=True)
    mapping_path = mapping_dir / "url_mapping.json"
    mapping_path.write_text(json.dumps({"source": source, "url_mapping": url_mapping}, ensure_ascii=False, indent=2), encoding="utf-8")
    artifact = await add_artifact(
        db,
        session,
        PublishArtifactKind.URL_MAPPING,
        mapping_path,
        {"source": source, "url_mapping": url_mapping},
        PublishArtifactStatus.CONFIRMED,
    )
    session.status = PublishSessionStatus.URLS_READY
    session.current_step = "export_patch"
    return artifact


async def rollback_session_to_step(db: AsyncSession, session: PublishSession, target_step: str) -> None:
    kinds = STEP_ARTIFACTS.get(target_step)
    if kinds is None:
        raise HTTPException(status_code=400, detail="不支持的回退步骤")
    await supersede_artifacts_after_step(db, session.id, kinds)
    session.current_step = target_step
    if target_step == "confirm_sheets":
        session.status = PublishSessionStatus.SHEETS_READY
    elif target_step == "prepare_urls":
        session.status = PublishSessionStatus.URLS_READY
