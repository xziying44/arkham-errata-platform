from datetime import datetime
from pydantic import BaseModel, ConfigDict


class PublishSessionCreateRequest(BaseModel):
    package_id: int


class PublishArtifactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: int
    kind: str
    status: str
    path: str
    public_url: str | None
    checksum: str | None
    metadata: dict
    created_at: datetime
    updated_at: datetime


class PublishSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    package_id: int
    status: str
    current_step: str
    artifact_root: str
    error_message: str | None
    cleanup_at: datetime | None
    created_at: datetime
    updated_at: datetime
    artifacts: list[PublishArtifactResponse] = []


class PublishDirectoryPresetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    local_dir_prefix: str
    target_area: str
    target_bag_path: str
    target_bag_guid: str
    target_object_dir: str
    label: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class PublishDirectoryPresetUpdateRequest(BaseModel):
    target_bag_path: str | None = None
    target_bag_guid: str | None = None
    target_object_dir: str | None = None
    label: str | None = None
    is_active: bool | None = None
