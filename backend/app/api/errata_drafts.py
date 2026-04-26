from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import require_user
from app.database import get_db
from app.models.errata_draft import ErrataAuditAction
from app.models.user import User, UserRole
from app.schemas.errata_draft import ErrataAuditLogResponse, ErrataDraftResponse, SaveErrataDraftRequest
from app.services.errata_drafts import get_active_draft, get_logs, get_participant_usernames, save_draft

router = APIRouter(prefix="/api/errata-drafts", tags=["勘误副本"])


def can_save(user: User) -> bool:
    return user.role in {UserRole.ERRATA, UserRole.REVIEWER, UserRole.ADMIN}


def serialize_draft(draft, participant_usernames: list[str]) -> ErrataDraftResponse:
    return ErrataDraftResponse(
        id=draft.id,
        arkhamdb_id=draft.arkhamdb_id,
        status=draft.status.value,
        original_faces=draft.original_faces,
        modified_faces=draft.modified_faces,
        changed_faces=draft.changed_faces,
        rendered_previews=draft.rendered_previews,
        package_id=draft.package_id,
        participant_usernames=participant_usernames,
        created_at=draft.created_at,
        updated_at=draft.updated_at,
    )


@router.get("/{arkhamdb_id}", response_model=ErrataDraftResponse)
async def get_draft(
    arkhamdb_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    draft = await get_active_draft(db, arkhamdb_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="该卡牌还没有勘误副本")
    participants = await get_participant_usernames(db, arkhamdb_id)
    return serialize_draft(draft, participants)


@router.put("/{arkhamdb_id}", response_model=ErrataDraftResponse)
async def put_draft(
    arkhamdb_id: str,
    body: SaveErrataDraftRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    if not can_save(current_user):
        raise HTTPException(status_code=403, detail="需要勘误或审核权限")
    action = ErrataAuditAction.REVIEW_SAVE if current_user.role == UserRole.REVIEWER else ErrataAuditAction.SAVE
    draft = await save_draft(db, arkhamdb_id, body, current_user, action)
    participants = await get_participant_usernames(db, arkhamdb_id)
    return serialize_draft(draft, participants)


@router.get("/{arkhamdb_id}/logs", response_model=list[ErrataAuditLogResponse])
async def list_draft_logs(
    arkhamdb_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    rows = await get_logs(db, arkhamdb_id)
    return [
        ErrataAuditLogResponse(
            id=log.id,
            arkhamdb_id=log.arkhamdb_id,
            username=username,
            action=log.action.value,
            from_status=log.from_status,
            to_status=log.to_status,
            changed_faces=log.changed_faces,
            diff_summary=log.diff_summary,
            created_at=log.created_at,
        )
        for log, username in rows
    ]
