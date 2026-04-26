import hashlib
import json
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.card import LocalCardFile
from app.models.errata_draft import ErrataAuditAction, ErrataAuditLog, ErrataDraft, ErrataDraftStatus
from app.models.user import User
from app.schemas.errata_draft import SaveErrataDraftRequest


def _content_hash(content: dict) -> str:
    payload = json.dumps(content, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _local_card_root() -> Path:
    return (settings.project_root / settings.local_card_db).resolve()


def _read_local_card_content(relative_path: str) -> dict:
    path = _local_card_root() / relative_path
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail=f"本地卡牌文件 JSON 无法解析：{relative_path}") from exc


async def get_active_draft(db: AsyncSession, arkhamdb_id: str) -> ErrataDraft | None:
    result = await db.execute(
        select(ErrataDraft)
        .where(ErrataDraft.arkhamdb_id == arkhamdb_id)
        .where(ErrataDraft.archived_at.is_(None))
        .order_by(ErrataDraft.updated_at.desc(), ErrataDraft.id.desc())
    )
    return result.scalars().first()


async def load_original_faces(db: AsyncSession, arkhamdb_id: str) -> dict[str, dict]:
    result = await db.execute(
        select(LocalCardFile)
        .where(LocalCardFile.arkhamdb_id == arkhamdb_id)
        .order_by(LocalCardFile.face)
    )
    files = result.scalars().all()
    if not files:
        raise HTTPException(status_code=404, detail="本地卡牌文件不存在")
    return {card_file.face: _read_local_card_content(card_file.relative_path) for card_file in files}


def ensure_draft_editable(draft: ErrataDraft) -> None:
    if draft.status == ErrataDraftStatus.WAITING_PUBLISH:
        raise HTTPException(status_code=409, detail="该卡牌已进入待发布包，请管理员解锁后再修改")


async def append_audit_log(
    db: AsyncSession,
    draft: ErrataDraft,
    user: User,
    action: ErrataAuditAction,
    from_status: str | None,
    to_status: str | None,
    changed_faces: list[str],
    diff_summary: str | None = None,
) -> ErrataAuditLog:
    log = ErrataAuditLog(
        draft_id=draft.id,
        arkhamdb_id=draft.arkhamdb_id,
        user_id=user.id,
        action=action,
        from_status=from_status,
        to_status=to_status,
        changed_faces=changed_faces,
        content_hash=_content_hash(draft.modified_faces),
        diff_summary=diff_summary,
    )
    db.add(log)
    return log


async def save_draft(
    db: AsyncSession,
    arkhamdb_id: str,
    body: SaveErrataDraftRequest,
    user: User,
    action: ErrataAuditAction,
) -> ErrataDraft:
    draft = await get_active_draft(db, arkhamdb_id)
    created = False
    from_status: str | None = None

    if draft is None:
        original_faces = await load_original_faces(db, arkhamdb_id)
        draft = ErrataDraft(
            arkhamdb_id=arkhamdb_id,
            status=ErrataDraftStatus.ERRATA,
            original_faces=original_faces,
            modified_faces=body.modified_faces,
            changed_faces=body.changed_faces,
            rendered_previews={},
            created_by=user.id,
            updated_by=user.id,
        )
        db.add(draft)
        await db.flush()
        created = True
        await append_audit_log(
            db,
            draft,
            user,
            ErrataAuditAction.CREATE,
            None,
            draft.status.value,
            body.changed_faces,
            "创建勘误副本",
        )
    else:
        ensure_draft_editable(draft)
        from_status = draft.status.value
        draft.modified_faces = body.modified_faces
        draft.changed_faces = body.changed_faces
        draft.updated_by = user.id

    await append_audit_log(
        db,
        draft,
        user,
        action if not created else ErrataAuditAction.SAVE,
        from_status or draft.status.value,
        draft.status.value,
        body.changed_faces,
        body.diff_summary,
    )
    await db.commit()
    await db.refresh(draft)
    return draft


async def cancel_draft(db: AsyncSession, arkhamdb_id: str, user: User, note: str | None = None) -> ErrataDraft:
    draft = await get_active_draft(db, arkhamdb_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="该卡牌还没有勘误副本")
    if draft.status != ErrataDraftStatus.ERRATA:
        raise HTTPException(status_code=409, detail="只有勘误状态的卡牌可以取消勘误")

    from_status = draft.status.value
    draft.status = ErrataDraftStatus.ARCHIVED
    draft.archived_at = datetime.now()
    draft.package_id = None
    draft.updated_by = user.id
    await append_audit_log(
        db,
        draft,
        user,
        ErrataAuditAction.CANCEL,
        from_status,
        "正常",
        draft.changed_faces,
        note or "审核员取消勘误状态",
    )
    await db.commit()
    await db.refresh(draft)
    return draft


async def get_participant_usernames(db: AsyncSession, arkhamdb_id: str) -> list[str]:
    from app.models.user import User

    result = await db.execute(
        select(User.username)
        .join(ErrataAuditLog, ErrataAuditLog.user_id == User.id)
        .where(ErrataAuditLog.arkhamdb_id == arkhamdb_id)
        .group_by(User.username)
        .order_by(User.username)
    )
    return list(result.scalars().all())


async def get_logs(db: AsyncSession, arkhamdb_id: str) -> list[tuple[ErrataAuditLog, str]]:
    from app.models.user import User

    result = await db.execute(
        select(ErrataAuditLog, User.username)
        .join(User, ErrataAuditLog.user_id == User.id)
        .where(ErrataAuditLog.arkhamdb_id == arkhamdb_id)
        .order_by(ErrataAuditLog.created_at.asc(), ErrataAuditLog.id.asc())
    )
    return list(result.all())
