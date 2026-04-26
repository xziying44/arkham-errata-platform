import json
import uuid
from pathlib import Path
from sqlalchemy import select

from app.services.url_replacer import export_chinese_card_url_replacements


def test_export_chinese_card_url_replacements_does_not_modify_source(tmp_path):
    source_root = tmp_path / "source"
    output_root = tmp_path / "output"
    card_path = source_root / "pack" / "TestCard.json"
    card_path.parent.mkdir(parents=True)
    original = {
        "Name": "Card",
        "CardID": 100,
        "GMNotes": json.dumps({"id": "01001"}),
        "CustomDeck": {
            "1": {
                "FaceURL": "old-face",
                "BackURL": "old-back",
                "NumWidth": 10,
                "NumHeight": 1,
                "UniqueBack": False,
            }
        },
    }
    card_path.write_text(json.dumps(original, ensure_ascii=False), encoding="utf-8")

    modified = export_chinese_card_url_replacements(
        source_root,
        output_root,
        {
            "01001": {
                "deck_key": "9999",
                "card_id": 999900,
                "face_url": "new-face",
                "back_url": "new-back",
                "grid_w": 5,
                "grid_h": 2,
                "unique_back": True,
            }
        },
    )

    assert modified == ["pack/TestCard.json"]
    assert json.loads(card_path.read_text(encoding="utf-8")) == original
    exported = json.loads((output_root / "pack" / "TestCard.json").read_text(encoding="utf-8"))
    assert exported["CardID"] == 999900
    assert exported["CustomDeck"]["9999"]["FaceURL"] == "new-face"

import pytest
from httpx import AsyncClient

from app.models.errata_draft import ErrataDraft, ErrataDraftStatus, ErrataPackage, ErrataPackageStatus
from app.models.user import User, UserRole
from app.utils.security import hash_password


async def _publish_admin_token(client: AsyncClient, db) -> str:
    username = f"publish-admin-{uuid.uuid4().hex[:8]}"
    admin = User(username=username, password_hash=hash_password("pw"), role=UserRole.ADMIN)
    db.add(admin)
    await db.commit()
    response = await client.post("/api/auth/login", json={"username": username, "password": "pw"})
    assert response.status_code == 200
    return response.json()["token"], username


@pytest.mark.asyncio
async def test_step1_requires_existing_package(client: AsyncClient, db):
    token, _ = await _publish_admin_token(client, db)
    response = await client.post(
        "/api/admin/publish/step1-generate-sheets",
        headers={"Authorization": f"Bearer {token}"},
        json={"package_id": 999999},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "勘误包不存在"


@pytest.mark.asyncio
async def test_step1_requires_waiting_publish_package(client: AsyncClient, db):
    token, username = await _publish_admin_token(client, db)
    admin = (await db.execute(select(User).where(User.username == username))).scalar_one()
    package = ErrataPackage(package_no="ERRATA-PUBLISHED", status=ErrataPackageStatus.PUBLISHED, created_by=admin.id)
    db.add(package)
    await db.commit()
    await db.refresh(package)

    response = await client.post(
        "/api/admin/publish/step1-generate-sheets",
        headers={"Authorization": f"Bearer {token}"},
        json={"package_id": package.id},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "只有待发布的勘误包可以进入发布流程"


@pytest.mark.asyncio
async def test_step3_uses_package_id_instead_of_approved_cards(client: AsyncClient, db):
    token, username = await _publish_admin_token(client, db)
    admin = (await db.execute(select(User).where(User.username == username))).scalar_one()
    package = ErrataPackage(package_no="ERRATA-EXPORT", status=ErrataPackageStatus.WAITING_PUBLISH, created_by=admin.id)
    db.add(package)
    await db.flush()
    draft = ErrataDraft(
        arkhamdb_id="01999",
        status=ErrataDraftStatus.WAITING_PUBLISH,
        original_faces={},
        modified_faces={"a": {"name": "后端包数据"}},
        changed_faces=["a"],
        package_id=package.id,
        created_by=admin.id,
        updated_by=admin.id,
    )
    db.add(draft)
    await db.commit()

    response = await client.post(
        "/api/admin/publish/step3-export-tts",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "package_id": package.id,
            "approved_cards": [{"arkhamdb_id": "00000", "name_zh": "前端伪造"}],
            "sheet_urls": {"SheetZH01999-01999": "https://example.com/sheet.jpg"},
            "sheet_grids": {"SheetZH01999-01999": {"deck_key": "10000", "width": 10, "height": 1}},
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    payload = json.loads(response.content)
    assert payload["Nickname"] == "勘误发布包"
    assert any(obj.get("GMNotes") == json.dumps({"id": "01999"}, ensure_ascii=False) for obj in payload.values() if isinstance(obj, dict))


def test_generated_tts_bag_can_be_uploaded_back_for_url_extraction():
    from app.services.url_replacer import generate_tts_bag_json, extract_steam_urls_from_json

    bag = generate_tts_bag_json(
        approved_cards=[{"arkhamdb_id": "01104", "name_zh": "测试卡", "sheet_name": "SheetZH01104-01104", "unique_back": False}],
        sheet_urls={"SheetZH01104-01104": "https://example.com/sheet.jpg"},
        sheet_grids={"SheetZH01104-01104": {"deck_key": "1104", "width": 10, "height": 1}},
    )

    mapping = extract_steam_urls_from_json(bag)
    assert set(mapping) == {"01104"}
    assert mapping["01104"]["face_url"] == "https://example.com/sheet.jpg"
