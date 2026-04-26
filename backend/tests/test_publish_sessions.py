import uuid

import pytest
from sqlalchemy import select

from app.models.errata_draft import (
    ErrataPackage,
    ErrataPackageStatus,
    PublishArtifact,
    PublishArtifactKind,
    PublishArtifactStatus,
    PublishDirectoryPreset,
    PublishDirectoryTargetArea,
    PublishSession,
    PublishSessionStatus,
)
from app.models.user import User, UserRole
from app.utils.security import hash_password


@pytest.mark.asyncio
async def test_publish_session_artifact_models_persist(db):
    suffix = uuid.uuid4().hex[:8]
    admin = User(username=f"publish-model-admin-{suffix}", password_hash=hash_password("pw"), role=UserRole.ADMIN)
    db.add(admin)
    await db.flush()
    package = ErrataPackage(package_no=f"ERRATA-PUBLISH-{suffix}", status=ErrataPackageStatus.WAITING_PUBLISH, created_by=admin.id)
    db.add(package)
    await db.flush()

    session = PublishSession(
        package_id=package.id,
        status=PublishSessionStatus.DRAFT,
        current_step="select_package",
        artifact_root=f"data/cache/publish/{package.package_no}/{suffix}",
        created_by=admin.id,
        updated_by=admin.id,
    )
    db.add(session)
    await db.flush()
    artifact = PublishArtifact(
        session_id=session.id,
        kind=PublishArtifactKind.MANIFEST,
        status=PublishArtifactStatus.ACTIVE,
        path=f"{session.artifact_root}/manifest.json",
        public_url="/static/cache/publish/test/manifest.json",
        checksum="abc123",
        artifact_metadata={"package_no": package.package_no},
    )
    db.add(artifact)
    await db.commit()

    saved_session = (await db.execute(select(PublishSession).where(PublishSession.id == session.id))).scalar_one()
    saved_artifact = (await db.execute(select(PublishArtifact).where(PublishArtifact.session_id == session.id))).scalar_one()
    assert saved_session.status == PublishSessionStatus.DRAFT
    assert saved_artifact.kind == PublishArtifactKind.MANIFEST
    assert saved_artifact.artifact_metadata["package_no"] == package.package_no


@pytest.mark.asyncio
async def test_publish_directory_preset_model_persists(db):
    preset = PublishDirectoryPreset(
        local_dir_prefix="剧本卡/01_基础游戏",
        target_area=PublishDirectoryTargetArea.CAMPAIGNS,
        target_bag_path="decomposed/language-pack/Simplified Chinese - Campaigns/SimplifiedChinese-Campaigns.SimplifiedChineseC/Core.8d1ac7.json",
        target_bag_guid="8d1ac7",
        target_object_dir="Core.8d1ac7",
        label="01_基础游戏 -> Core",
        is_active=True,
    )
    db.add(preset)
    await db.commit()

    saved = (await db.execute(select(PublishDirectoryPreset))).scalar_one()
    assert saved.target_area == PublishDirectoryTargetArea.CAMPAIGNS
    assert saved.local_dir_prefix == "剧本卡/01_基础游戏"
