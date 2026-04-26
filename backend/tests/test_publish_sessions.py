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

from httpx import AsyncClient


async def _admin_token(client: AsyncClient, db) -> tuple[str, User]:
    suffix = uuid.uuid4().hex[:8]
    admin = User(username=f"publish-session-admin-{suffix}", password_hash=hash_password("pw"), role=UserRole.ADMIN)
    db.add(admin)
    await db.commit()
    await db.refresh(admin)
    response = await client.post("/api/auth/login", json={"username": admin.username, "password": "pw"})
    assert response.status_code == 200
    return response.json()["token"], admin


@pytest.mark.asyncio
async def test_admin_can_create_publish_session(client: AsyncClient, db):
    token, admin = await _admin_token(client, db)
    package = ErrataPackage(package_no=f"ERRATA-SESSION-{uuid.uuid4().hex[:6]}", status=ErrataPackageStatus.WAITING_PUBLISH, created_by=admin.id)
    db.add(package)
    await db.commit()
    await db.refresh(package)

    response = await client.post(
        "/api/admin/publish/sessions",
        headers={"Authorization": f"Bearer {token}"},
        json={"package_id": package.id},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["package_id"] == package.id
    assert data["status"] == "草稿"
    assert data["artifact_root"].startswith(f"data/cache/publish/{package.package_no}/")


@pytest.mark.asyncio
async def test_cannot_create_second_active_session_for_same_package(client: AsyncClient, db):
    token, admin = await _admin_token(client, db)
    package = ErrataPackage(package_no=f"ERRATA-ONE-SESSION-{uuid.uuid4().hex[:6]}", status=ErrataPackageStatus.WAITING_PUBLISH, created_by=admin.id)
    db.add(package)
    await db.commit()
    await db.refresh(package)

    first = await client.post("/api/admin/publish/sessions", headers={"Authorization": f"Bearer {token}"}, json={"package_id": package.id})
    second = await client.post("/api/admin/publish/sessions", headers={"Authorization": f"Bearer {token}"}, json={"package_id": package.id})

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["detail"] == "当前勘误包已有未完成发布会话"

from app.models.errata_draft import ErrataDraft, ErrataDraftStatus


@pytest.mark.asyncio
async def test_generate_sheets_creates_session_artifacts(client: AsyncClient, db, monkeypatch, tmp_path):
    token, admin = await _admin_token(client, db)
    package = ErrataPackage(package_no=f"ERRATA-SHEETS-{uuid.uuid4().hex[:6]}", status=ErrataPackageStatus.WAITING_PUBLISH, created_by=admin.id)
    db.add(package)
    await db.flush()
    draft = ErrataDraft(
        arkhamdb_id="01104",
        status=ErrataDraftStatus.WAITING_PUBLISH,
        original_faces={},
        modified_faces={"a": {"name": "测试正面"}, "b": {"name": "测试背面"}},
        changed_faces=["a", "b"],
        package_id=package.id,
        created_by=admin.id,
        updated_by=admin.id,
    )
    db.add(draft)
    await db.commit()
    await db.refresh(package)

    def fake_render(content, output_dir, filename):
        from PIL import Image
        path = output_dir / f"{filename}.jpg"
        Image.new("RGB", (750, 1050), (255, 255, 255)).save(path)
        return str(path)

    monkeypatch.setattr("app.api.publish.render_card_preview", fake_render)
    session_response = await client.post("/api/admin/publish/sessions", headers={"Authorization": f"Bearer {token}"}, json={"package_id": package.id})
    session_id = session_response.json()["id"]

    response = await client.post(f"/api/admin/publish/sessions/{session_id}/generate-sheets", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "待确认精灵图"
    kinds = {artifact["kind"] for artifact in data["artifacts"]}
    assert "sheet_front" in kinds
    assert "sheet_back" in kinds

@pytest.mark.asyncio
async def test_import_manual_urls_creates_url_mapping_artifact(client: AsyncClient, db):
    token, admin = await _admin_token(client, db)
    package = ErrataPackage(package_no=f"ERRATA-URLS-{uuid.uuid4().hex[:6]}", status=ErrataPackageStatus.WAITING_PUBLISH, created_by=admin.id)
    db.add(package)
    await db.commit()
    await db.refresh(package)
    session_response = await client.post("/api/admin/publish/sessions", headers={"Authorization": f"Bearer {token}"}, json={"package_id": package.id})
    session_id = session_response.json()["id"]

    response = await client.post(
        f"/api/admin/publish/sessions/{session_id}/import-urls",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "source": "manual",
            "url_mapping": {
                "01104": {"face_url": "https://example.com/sheet.jpg", "back_url": "https://example.com/sheet-back.jpg", "deck_key": "1104", "card_id": 110400, "grid_w": 10, "grid_h": 1, "unique_back": False}
            },
        },
    )

    assert response.status_code == 200
    artifacts = response.json()["artifacts"]
    url_artifacts = [artifact for artifact in artifacts if artifact["kind"] == "url_mapping"]
    assert url_artifacts
    assert url_artifacts[-1]["metadata"]["url_mapping"]["01104"]["face_url"] == "https://example.com/sheet.jpg"


@pytest.mark.asyncio
async def test_rollback_to_confirm_sheets_supersedes_url_artifacts(client: AsyncClient, db):
    token, admin = await _admin_token(client, db)
    package = ErrataPackage(package_no=f"ERRATA-ROLLBACK-{uuid.uuid4().hex[:6]}", status=ErrataPackageStatus.WAITING_PUBLISH, created_by=admin.id)
    db.add(package)
    await db.commit()
    await db.refresh(package)
    session_response = await client.post("/api/admin/publish/sessions", headers={"Authorization": f"Bearer {token}"}, json={"package_id": package.id})
    session_id = session_response.json()["id"]
    await client.post(
        f"/api/admin/publish/sessions/{session_id}/import-urls",
        headers={"Authorization": f"Bearer {token}"},
        json={"source": "manual", "url_mapping": {"01104": {"face_url": "new-face"}}},
    )

    response = await client.post(
        f"/api/admin/publish/sessions/{session_id}/rollback-step",
        headers={"Authorization": f"Bearer {token}"},
        json={"target_step": "confirm_sheets"},
    )

    assert response.status_code == 200
    assert response.json()["current_step"] == "confirm_sheets"
    url_artifacts = [artifact for artifact in response.json()["artifacts"] if artifact["kind"] == "url_mapping"]
    assert all(artifact["status"] == "superseded" for artifact in url_artifacts)
