import json
import zipfile
import uuid
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.card import CardIndex, LocalCardFile
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

    saved = (await db.execute(select(PublishDirectoryPreset).where(PublishDirectoryPreset.local_dir_prefix == "剧本卡/01_基础游戏"))).scalar_one()
    assert saved.target_area == PublishDirectoryTargetArea.CAMPAIGNS
    assert saved.local_dir_prefix == "剧本卡/01_基础游戏"


@pytest.mark.asyncio
async def test_admin_can_create_directory_preset(client: AsyncClient, db):
    token, _admin = await _admin_token(client, db)

    response = await client.post(
        "/api/admin/publish/directory-presets",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "local_dir_prefix": "剧本卡/09_绯红密钥",
            "target_area": "campaigns",
            "target_bag_path": "decomposed/language-pack/Simplified Chinese - Campaigns/SimplifiedChinese-Campaigns.SimplifiedChineseC/TheScarletKeys.ab12cd.json",
            "target_bag_guid": "ab12cd",
            "target_object_dir": "TheScarletKeys.ab12cd",
            "label": "09_绯红密钥 -> TheScarletKeys",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["local_dir_prefix"] == "剧本卡/09_绯红密钥"
    assert data["target_area"] == "campaigns"
    assert data["is_active"] is True

    saved = (await db.execute(select(PublishDirectoryPreset).where(PublishDirectoryPreset.local_dir_prefix == "剧本卡/09_绯红密钥"))).scalar_one()
    assert saved.target_object_dir == "TheScarletKeys.ab12cd"



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

    def fake_render(content, output_dir, filename, dpi=150, quality=90):
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
async def test_confirm_sheets_moves_session_to_prepare_urls(client: AsyncClient, db, monkeypatch):
    token, admin = await _admin_token(client, db)
    package = ErrataPackage(package_no=f"ERRATA-CONFIRM-SHEETS-{uuid.uuid4().hex[:6]}", status=ErrataPackageStatus.WAITING_PUBLISH, created_by=admin.id)
    db.add(package)
    await db.flush()
    draft = ErrataDraft(
        arkhamdb_id="01104",
        status=ErrataDraftStatus.WAITING_PUBLISH,
        original_faces={},
        modified_faces={"a": {"name": "测试正面"}},
        changed_faces=["a"],
        package_id=package.id,
        created_by=admin.id,
        updated_by=admin.id,
    )
    db.add(draft)
    await db.commit()

    def fake_render(content, output_dir, filename, dpi=150, quality=90):
        from PIL import Image
        path = output_dir / f"{filename}.jpg"
        Image.new("RGB", (750, 1050), (255, 255, 255)).save(path)
        return str(path)

    monkeypatch.setattr("app.api.publish.render_card_preview", fake_render)
    session_response = await client.post("/api/admin/publish/sessions", headers={"Authorization": f"Bearer {token}"}, json={"package_id": package.id})
    session_id = session_response.json()["id"]
    await client.post(f"/api/admin/publish/sessions/{session_id}/generate-sheets", headers={"Authorization": f"Bearer {token}"})

    response = await client.post(f"/api/admin/publish/sessions/{session_id}/confirm-sheets", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    data = response.json()
    assert data["current_step"] == "prepare_urls"
    assert data["status"] == "待准备URL"
    sheet_artifacts = [artifact for artifact in data["artifacts"] if artifact["kind"] == "sheet_front"]
    assert sheet_artifacts[-1]["status"] == "confirmed"


@pytest.mark.asyncio
async def test_session_exports_tts_bag_after_confirming_sheets(client: AsyncClient, db, monkeypatch):
    token, admin = await _admin_token(client, db)
    package = ErrataPackage(package_no=f"ERRATA-TTS-BAG-{uuid.uuid4().hex[:6]}", status=ErrataPackageStatus.WAITING_PUBLISH, created_by=admin.id)
    db.add(package)
    await db.flush()
    draft = ErrataDraft(
        arkhamdb_id="01104",
        status=ErrataDraftStatus.WAITING_PUBLISH,
        original_faces={},
        modified_faces={"a": {"name": "测试正面"}},
        changed_faces=["a"],
        package_id=package.id,
        created_by=admin.id,
        updated_by=admin.id,
    )
    db.add(draft)
    await db.commit()

    def fake_render(content, output_dir, filename, dpi=150, quality=90):
        from PIL import Image
        path = output_dir / f"{filename}.jpg"
        Image.new("RGB", (750, 1050), (255, 255, 255)).save(path)
        return str(path)

    monkeypatch.setattr("app.api.publish.render_card_preview", fake_render)
    session_response = await client.post("/api/admin/publish/sessions", headers={"Authorization": f"Bearer {token}"}, json={"package_id": package.id})
    session_id = session_response.json()["id"]
    await client.post(f"/api/admin/publish/sessions/{session_id}/generate-sheets", headers={"Authorization": f"Bearer {token}"})
    await client.post(f"/api/admin/publish/sessions/{session_id}/confirm-sheets", headers={"Authorization": f"Bearer {token}"})

    urls_response = await client.get(f"/api/admin/publish/sessions/{session_id}/sheet-urls", headers={"Authorization": f"Bearer {token}"})
    export_response = await client.get(f"/api/admin/publish/sessions/{session_id}/tts-bag", headers={"Authorization": f"Bearer {token}"})

    assert urls_response.status_code == 200
    assert urls_response.json()["items"][0]["url"].startswith("http://test")
    assert export_response.status_code == 200
    data = export_response.json()
    assert data["Name"] == "Custom_Model_Bag"
    assert "01104" in export_response.text


@pytest.mark.asyncio
async def test_generate_sheets_separates_single_sided_cards_from_double_sided_back_sheet(client: AsyncClient, db, monkeypatch):
    token, admin = await _admin_token(client, db)
    package = ErrataPackage(package_no=f"ERRATA-MIXED-SHEETS-{uuid.uuid4().hex[:6]}", status=ErrataPackageStatus.WAITING_PUBLISH, created_by=admin.id)
    db.add(package)
    await db.flush()
    drafts = [
        ErrataDraft(
            arkhamdb_id="01001",
            status=ErrataDraftStatus.WAITING_PUBLISH,
            original_faces={},
            modified_faces={"a": {"name": "双面正面"}, "b": {"name": "双面背面"}},
            changed_faces=["a", "b"],
            package_id=package.id,
            created_by=admin.id,
            updated_by=admin.id,
        ),
        ErrataDraft(
            arkhamdb_id="01011",
            status=ErrataDraftStatus.WAITING_PUBLISH,
            original_faces={},
            modified_faces={"a": {"name": "单面玩家"}},
            changed_faces=["a"],
            package_id=package.id,
            created_by=admin.id,
            updated_by=admin.id,
        ),
        ErrataDraft(
            arkhamdb_id="01014",
            status=ErrataDraftStatus.WAITING_PUBLISH,
            original_faces={},
            modified_faces={"a": {"name": "单面遭遇"}},
            changed_faces=["a"],
            package_id=package.id,
            created_by=admin.id,
            updated_by=admin.id,
        ),
    ]
    db.add_all(drafts)
    await db.commit()

    def fake_render(content, output_dir, filename, dpi=150, quality=90):
        from PIL import Image
        path = output_dir / f"{filename}.jpg"
        Image.new("RGB", (750, 1050), (255, 255, 255)).save(path)
        return str(path)

    monkeypatch.setattr("app.api.publish.render_card_preview", fake_render)
    session_response = await client.post("/api/admin/publish/sessions", headers={"Authorization": f"Bearer {token}"}, json={"package_id": package.id})
    session_id = session_response.json()["id"]

    response = await client.post(f"/api/admin/publish/sessions/{session_id}/generate-sheets", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    artifacts = response.json()["artifacts"]
    active_front_sheets = [artifact for artifact in artifacts if artifact["kind"] == "sheet_front" and artifact["status"] == "active"]
    active_back_sheets = [artifact for artifact in artifacts if artifact["kind"] == "sheet_back" and artifact["status"] == "active"]
    assert len(active_front_sheets) == 2
    assert len(active_back_sheets) == 1
    assert active_back_sheets[0]["metadata"]["card_ids"] == ["01001"]
    assert {tuple(artifact["metadata"]["card_ids"]) for artifact in active_front_sheets} == {("01001",), ("01011", "01014")}


@pytest.mark.asyncio
async def test_two_card_session_exports_two_column_sheet_grid(client: AsyncClient, db, monkeypatch):
    token, admin = await _admin_token(client, db)
    package = ErrataPackage(package_no=f"ERRATA-TWO-CARDS-{uuid.uuid4().hex[:6]}", status=ErrataPackageStatus.WAITING_PUBLISH, created_by=admin.id)
    db.add(package)
    await db.flush()
    for card_id in ["01104", "01105"]:
        db.add(ErrataDraft(
            arkhamdb_id=card_id,
            status=ErrataDraftStatus.WAITING_PUBLISH,
            original_faces={},
            modified_faces={"a": {"name": f"测试{card_id}"}},
            changed_faces=["a"],
            package_id=package.id,
            created_by=admin.id,
            updated_by=admin.id,
        ))
    await db.commit()

    def fake_render(content, output_dir, filename, dpi=150, quality=90):
        from PIL import Image
        path = output_dir / f"{filename}.jpg"
        Image.new("RGB", (1500, 2100), (255, 255, 255)).save(path)
        return str(path)

    monkeypatch.setattr("app.api.publish.render_card_preview", fake_render)
    session_response = await client.post("/api/admin/publish/sessions", headers={"Authorization": f"Bearer {token}"}, json={"package_id": package.id})
    session_id = session_response.json()["id"]
    generate_response = await client.post(f"/api/admin/publish/sessions/{session_id}/generate-sheets", headers={"Authorization": f"Bearer {token}"})

    assert generate_response.status_code == 200
    front_sheet = next(artifact for artifact in generate_response.json()["artifacts"] if artifact["kind"] == "sheet_front")
    assert front_sheet["metadata"]["grid_width"] == 2
    assert front_sheet["metadata"]["grid_height"] == 1

    await client.post(f"/api/admin/publish/sessions/{session_id}/confirm-sheets", headers={"Authorization": f"Bearer {token}"})
    export_response = await client.get(f"/api/admin/publish/sessions/{session_id}/tts-bag", headers={"Authorization": f"Bearer {token}"})
    custom_decks = [value["CustomDeck"] for value in export_response.json().values() if isinstance(value, dict) and value.get("Name") == "Card"]
    first_sheet = next(iter(custom_decks[0].values()))
    assert first_sheet["NumWidth"] == 2
    assert first_sheet["NumHeight"] == 1


@pytest.mark.asyncio
async def test_export_session_patch_creates_downloadable_zip(client: AsyncClient, db):
    token, admin = await _admin_token(client, db)
    package = ErrataPackage(package_no=f"ERRATA-PATCH-ZIP-{uuid.uuid4().hex[:6]}", status=ErrataPackageStatus.WAITING_PUBLISH, created_by=admin.id)
    db.add(package)
    await db.flush()
    draft = ErrataDraft(
        arkhamdb_id="01104",
        status=ErrataDraftStatus.WAITING_PUBLISH,
        original_faces={},
        modified_faces={"a": {"name": "聚集于此"}},
        changed_faces=["a"],
        package_id=package.id,
        created_by=admin.id,
        updated_by=admin.id,
    )
    db.add(draft)
    await db.commit()
    session_response = await client.post("/api/admin/publish/sessions", headers={"Authorization": f"Bearer {token}"}, json={"package_id": package.id})
    session_id = session_response.json()["id"]
    await client.post(
        f"/api/admin/publish/sessions/{session_id}/import-urls",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "source": "manual",
            "url_mapping": {
                "01104": {"face_url": "https://example.com/front.jpg", "back_url": "https://example.com/back.jpg", "deck_key": "1104", "card_id": 110400, "grid_w": 1, "grid_h": 1, "unique_back": False}
            },
        },
    )

    response = await client.post(f"/api/admin/publish/sessions/{session_id}/export-patch", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    data = response.json()
    assert data["current_step"] == "complete"
    zip_artifact = next(artifact for artifact in data["artifacts"] if artifact["kind"] == "patch_zip" and artifact["status"] == "confirmed")
    zip_path = Path(__file__).resolve().parents[2] / zip_artifact["path"]
    assert zip_path.exists()
    with zipfile.ZipFile(zip_path) as archive:
        names = set(archive.namelist())
    assert "MANIFEST.json" in names
    assert "validation_report.json" in names
    assert any(name.endswith(".json") and name.startswith("decomposed/language-pack/") for name in names)


@pytest.mark.asyncio
async def test_export_session_patch_serializes_new_card_directory_preset(client: AsyncClient, db):
    token, admin = await _admin_token(client, db)
    card_id = f"99{uuid.uuid4().hex[:4]}"
    package = ErrataPackage(package_no=f"ERRATA-NEW-PATCH-{uuid.uuid4().hex[:6]}", status=ErrataPackageStatus.WAITING_PUBLISH, created_by=admin.id)
    db.add(package)
    db.add(CardIndex(arkhamdb_id=card_id, name_zh="新增场景", category="剧本卡", cycle="09_绯红密钥", expansion="09_绯红密钥"))
    await db.flush()
    local_prefix = f"剧本卡/测试新增/{card_id}"
    db.add(LocalCardFile(arkhamdb_id=card_id, face="a", relative_path=f"{local_prefix}/{card_id}_a.card", content_hash="hash", last_modified="now"))
    db.add(PublishDirectoryPreset(
        local_dir_prefix=local_prefix,
        target_area=PublishDirectoryTargetArea.CAMPAIGNS,
        target_bag_path=f"decomposed/language-pack/Simplified Chinese - Campaigns/SimplifiedChinese-Campaigns.SimplifiedChineseC/TestPack.{card_id}/TestPack.{card_id}.json",
        target_bag_guid=card_id,
        target_object_dir=f"TestPack.{card_id}",
        label="测试新增 -> TestPack",
        is_active=True,
    ))
    draft = ErrataDraft(
        arkhamdb_id=card_id,
        status=ErrataDraftStatus.WAITING_PUBLISH,
        original_faces={},
        modified_faces={"a": {"name": "新增场景"}},
        changed_faces=["a"],
        package_id=package.id,
        created_by=admin.id,
        updated_by=admin.id,
    )
    db.add(draft)
    await db.commit()
    session_response = await client.post("/api/admin/publish/sessions", headers={"Authorization": f"Bearer {token}"}, json={"package_id": package.id})
    session_id = session_response.json()["id"]
    await client.post(
        f"/api/admin/publish/sessions/{session_id}/import-urls",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "source": "manual",
            "url_mapping": {card_id: {"face_url": "https://example.com/new-front.jpg", "back_url": "", "deck_key": "9900", "card_id": 990000, "grid_w": 1, "grid_h": 1, "unique_back": False}},
        },
    )

    response = await client.post(f"/api/admin/publish/sessions/{session_id}/export-patch", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    zip_artifact = next(artifact for artifact in response.json()["artifacts"] if artifact["kind"] == "patch_zip" and artifact["status"] == "confirmed")
    zip_path = Path(__file__).resolve().parents[2] / zip_artifact["path"]
    with zipfile.ZipFile(zip_path) as archive:
        report = json.loads(archive.read("validation_report.json"))
        names = set(archive.namelist())
    assert report["items"][0]["action"] == "新增"
    assert any(name.endswith(".json") and f"TestPack.{card_id}/" in name for name in names)


@pytest.mark.asyncio
async def test_upload_session_tts_json_imports_url_mapping(client: AsyncClient, db):
    token, admin = await _admin_token(client, db)
    package = ErrataPackage(package_no=f"ERRATA-UPLOAD-TTS-{uuid.uuid4().hex[:6]}", status=ErrataPackageStatus.WAITING_PUBLISH, created_by=admin.id)
    db.add(package)
    await db.commit()
    session_response = await client.post("/api/admin/publish/sessions", headers={"Authorization": f"Bearer {token}"}, json={"package_id": package.id})
    session_id = session_response.json()["id"]
    payload = {
        "Name": "Custom_Model_Bag",
        "ContainedObjects_order": ["测试.abc123"],
        "测试.abc123": {
            "Name": "Card",
            "CardID": 123401,
            "GMNotes": '{"id":"01104"}',
            "CustomDeck": {"1234": {"FaceURL": "https://steam.example/front.jpg", "BackURL": "https://steam.example/back.jpg", "NumWidth": 10, "NumHeight": 1, "UniqueBack": True}},
        },
    }

    response = await client.post(
        f"/api/admin/publish/sessions/{session_id}/upload-tts-json",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("tts.json", json.dumps(payload).encode("utf-8"), "application/json")},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["current_step"] == "export_patch"
    url_artifacts = [artifact for artifact in data["artifacts"] if artifact["kind"] == "url_mapping"]
    assert url_artifacts[-1]["metadata"]["url_mapping"]["01104"]["face_url"] == "https://steam.example/front.jpg"


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


@pytest.mark.asyncio
async def test_generate_sheets_preserves_original_picture_base64(client: AsyncClient, db, monkeypatch):
    token, admin = await _admin_token(client, db)
    package = ErrataPackage(package_no=f"ERRATA-PICTURE-{uuid.uuid4().hex[:6]}", status=ErrataPackageStatus.WAITING_PUBLISH, created_by=admin.id)
    db.add(package)
    await db.flush()
    draft = ErrataDraft(
        arkhamdb_id="91006",
        status=ErrataDraftStatus.WAITING_PUBLISH,
        original_faces={"a": {"name": "原图", "picture_base64": "data:image/png;base64,AAAA"}},
        modified_faces={"a": {"name": "改文"}},
        changed_faces=["a"],
        package_id=package.id,
        created_by=admin.id,
        updated_by=admin.id,
    )
    db.add(draft)
    await db.commit()
    await db.refresh(package)

    def fake_render(content, output_dir, filename, dpi=150, quality=90):
        from PIL import Image
        assert content["picture_base64"] == "data:image/png;base64,AAAA"
        path = output_dir / f"{filename}.jpg"
        Image.new("RGB", (750, 1050), (255, 255, 255)).save(path)
        return str(path)

    monkeypatch.setattr("app.api.publish.render_card_preview", fake_render)
    session_response = await client.post("/api/admin/publish/sessions", headers={"Authorization": f"Bearer {token}"}, json={"package_id": package.id})
    session_id = session_response.json()["id"]

    response = await client.post(f"/api/admin/publish/sessions/{session_id}/generate-sheets", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
