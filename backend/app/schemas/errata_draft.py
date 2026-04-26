from datetime import datetime
from pydantic import BaseModel


class SaveErrataDraftRequest(BaseModel):
    modified_faces: dict[str, dict]
    changed_faces: list[str]
    diff_summary: str | None = None


class ErrataDraftResponse(BaseModel):
    id: int
    arkhamdb_id: str
    status: str
    original_faces: dict[str, dict]
    modified_faces: dict[str, dict]
    changed_faces: list[str]
    rendered_previews: dict[str, str | None]
    package_id: int | None
    participant_usernames: list[str]
    created_at: datetime
    updated_at: datetime


class ErrataAuditLogResponse(BaseModel):
    id: int
    arkhamdb_id: str
    username: str
    action: str
    from_status: str | None
    to_status: str | None
    changed_faces: list[str]
    diff_summary: str | None
    created_at: datetime
