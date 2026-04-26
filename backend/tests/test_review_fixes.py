import json
from pathlib import Path

import pytest
from sqlalchemy import select
from PIL import Image

from app.config import settings
from app.models.card import CardIndex, TTSCardImage
from app.models.card import LocalCardFile
from app.models.errata import Errata, ErrataStatus
from app.models.errata_draft import (
    ErrataAuditAction,
    ErrataAuditLog,
    ErrataDraft,
    ErrataDraftStatus,
    ErrataPackage,
    ErrataPackageStatus,
)
from app.models.user import User, UserRole
from app.utils.security import hash_password


async def _login(client, username: str, password: str = "123456") -> str:
    resp = await client.post("/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200
    return resp.json()["token"]


@pytest.mark.asyncio
async def test_errata_preview_requires_owner_or_admin(client, db):
    card = CardIndex(arkhamdb_id="90001", name_zh="测试卡", category="玩家卡")
    owner = User(username="owner", password_hash=hash_password("123456"), role=UserRole.ERRATA)
    other = User(username="other", password_hash=hash_password("123456"), role=UserRole.ERRATA)
    db.add_all([card, owner, other])
    await db.flush()
    errata = Errata(
        arkhamdb_id="90001",
        user_id=owner.id,
        original_content=json.dumps({"name": "原始"}, ensure_ascii=False),
        modified_content=json.dumps({"name": "修改"}, ensure_ascii=False),
        status=ErrataStatus.PENDING,
    )
    db.add(errata)
    await db.commit()

    other_token = await _login(client, "other")
    resp = await client.post(
        f"/api/errata/{errata.id}/preview",
        headers={"Authorization": f"Bearer {other_token}"},
    )

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_publish_export_requires_admin(client):
    resp = await client.post(
        "/api/admin/publish/step3-export-tts",
        json={"approved_cards": [], "sheet_urls": {}, "sheet_grids": {}},
    )
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_card_detail_returns_all_tts_instances(client, db):
    card = CardIndex(arkhamdb_id="90002", name_zh="多实例卡", category="剧本卡")
    db.add(card)
    await db.flush()
    db.add_all([
        TTSCardImage(
            arkhamdb_id="90002",
            source="英文",
            relative_json_path="a/Card.aaa.json",
            card_id=10000,
            deck_key="100",
            face_url="https://example.com/a.jpg",
        ),
        TTSCardImage(
            arkhamdb_id="90002",
            source="英文",
            relative_json_path="b/Card.bbb.json",
            card_id=10100,
            deck_key="101",
            face_url="https://example.com/b.jpg",
        ),
    ])
    await db.commit()

    resp = await client.get("/api/cards/90002")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["tts_en"]) == 2
    assert {item["relative_json_path"] for item in data["tts_en"]} == {
        "a/Card.aaa.json",
        "b/Card.bbb.json",
    }


@pytest.mark.asyncio
async def test_tts_image_endpoint_generates_cache(client, db, monkeypatch, tmp_path):
    card = CardIndex(arkhamdb_id="90003", name_zh="图片卡", category="剧本卡")
    db.add(card)
    await db.flush()
    tts = TTSCardImage(
        arkhamdb_id="90003",
        source="中文",
        relative_json_path="Card.ccc.json",
        card_id=10000,
        deck_key="100",
        face_url="https://example.com/sheet.jpg",
        grid_width=10,
        grid_height=1,
        grid_position=0,
        unique_back=True,
    )
    db.add(tts)
    await db.commit()
    await db.refresh(tts)

    def fake_download(*args, **kwargs):
        generated = Path(kwargs["cache_dir"]) / "generated.jpg"
        generated.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (10, 10), "white").save(generated, "JPEG")
        return str(generated)

    monkeypatch.setattr("app.api.cards.download_and_cut_sheet", fake_download)

    resp = await client.get(f"/api/cards/tts-images/{tts.id}/front")

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/jpeg"


@pytest.mark.asyncio
async def test_preview_returns_browser_accessible_url(client, monkeypatch, tmp_path):
    preview_file = settings.project_root / settings.cache_dir / "previews" / "01111.jpg"
    preview_file.parent.mkdir(parents=True, exist_ok=True)
    preview_file.write_bytes(b"fake image")

    def fake_render(*args, **kwargs):
        return str(preview_file)

    monkeypatch.setattr("app.services.renderer.render_card_preview", fake_render)

    resp = await client.post(
        "/api/cards/preview",
        json={"arkhamdb_id": "01111", "content": {"name": "测试"}},
    )

    assert resp.status_code == 200
    assert resp.json()["preview_url"].startswith("/static/cache/")


@pytest.mark.asyncio
async def test_local_card_tree_only_includes_cards_with_local_files(client, db):
    with_file = CardIndex(arkhamdb_id="91001", name_zh="有文件", category="玩家卡", cycle="01_基础游戏")
    without_file = CardIndex(arkhamdb_id="91002", name_zh="无文件", category="玩家卡", cycle="01_基础游戏")
    db.add_all([with_file, without_file])
    await db.flush()
    db.add(LocalCardFile(
        arkhamdb_id="91001",
        face="a",
        relative_path="玩家卡/01_基础游戏/91001_a.card",
        content_hash="hash",
        last_modified="0",
    ))
    await db.commit()

    resp = await client.get("/api/cards/tree")

    assert resp.status_code == 200
    text = json.dumps(resp.json(), ensure_ascii=False)
    assert "91001" in text
    assert "有文件" in text
    assert "91002" not in text


@pytest.mark.asyncio
async def test_local_card_tree_filters_by_filename(client, db):
    card = CardIndex(arkhamdb_id="91003", name_zh="文件搜索", category="剧本卡", cycle="02_敦威治")
    db.add(card)
    await db.flush()
    db.add(LocalCardFile(
        arkhamdb_id="91003",
        face="a",
        relative_path="剧本卡/02_敦威治/91003_a.card",
        content_hash="hash",
        last_modified="0",
    ))
    await db.commit()

    resp = await client.get("/api/cards/tree", params={"keyword": "91003_a"})

    assert resp.status_code == 200
    text = json.dumps(resp.json(), ensure_ascii=False)
    assert "91003" in text


@pytest.mark.asyncio
async def test_preview_all_renders_each_local_face(client, db, monkeypatch):
    card = CardIndex(arkhamdb_id="91004", name_zh="批量预览", category="剧本卡", cycle="01_基础游戏")
    db.add(card)
    await db.flush()
    db.add_all([
        LocalCardFile(arkhamdb_id="91004", face="a", relative_path="剧本卡/01_基础游戏/91004_a.card", content_hash="hash-a", last_modified="0"),
        LocalCardFile(arkhamdb_id="91004", face="b", relative_path="剧本卡/01_基础游戏/91004_b.card", content_hash="hash-b", last_modified="0"),
    ])
    await db.commit()

    def fake_load_card_content(root, relative_path, include_picture=False):
        content = {"name": relative_path, "type": "地点卡"}
        if include_picture:
            content["picture_base64"] = "data:image/png;base64,AAAA"
        return content

    def fake_render(card_content, output_dir, filename):
        path = settings.project_root / settings.cache_dir / "previews" / f"{filename}.jpg"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fake image")
        return str(path)

    monkeypatch.setattr("app.api.cards.load_card_content", fake_load_card_content)
    monkeypatch.setattr("app.services.renderer.render_card_preview", fake_render)

    resp = await client.post("/api/cards/91004/preview-all")

    assert resp.status_code == 200
    assert {item["face"] for item in resp.json()["items"]} == {"a", "b"}
    assert all(item["preview_url"].startswith("/static/cache/") for item in resp.json()["items"])


@pytest.mark.asyncio
async def test_preview_all_uses_picture_base64_for_rendering(client, db, monkeypatch):
    card = CardIndex(arkhamdb_id="91005", name_zh="背景预览", category="剧本卡", cycle="01_基础游戏")
    db.add(card)
    await db.flush()
    db.add(LocalCardFile(arkhamdb_id="91005", face="a", relative_path="剧本卡/01_基础游戏/91005_a.card", content_hash="hash", last_modified="0"))
    await db.commit()

    def fake_load_card_content(root, relative_path, include_picture=False):
        return {"name": "背景预览", "type": "地点卡", **({"picture_base64": "data:image/png;base64,AAAA"} if include_picture else {})}

    def fake_render(card_content, output_dir, filename):
        assert card_content["picture_base64"] == "data:image/png;base64,AAAA"
        path = settings.project_root / settings.cache_dir / "previews" / f"{filename}.jpg"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fake image")
        return str(path)

    monkeypatch.setattr("app.api.cards.load_card_content", fake_load_card_content)
    monkeypatch.setattr("app.services.renderer.render_card_preview", fake_render)

    resp = await client.post("/api/cards/91005/preview-all")

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_chinese_side_follows_english_alignment(db, monkeypatch):
    """本地面与英文面确认后，中文预览必须使用同一个 TTS 面。"""
    card = CardIndex(arkhamdb_id="92001", name_zh="正反测试", category="剧本卡")
    db.add(card)
    await db.flush()
    db.add_all([
        LocalCardFile(arkhamdb_id="92001", face="a", relative_path="92001_a.card", content_hash="a", last_modified="0"),
        LocalCardFile(arkhamdb_id="92001", face="b", relative_path="92001_b.card", content_hash="b", last_modified="0"),
        TTSCardImage(arkhamdb_id="92001", source="英文", relative_json_path="en.json", card_id=10000, deck_key="100", face_url="en-front", back_url="en-back", unique_back=True),
        TTSCardImage(arkhamdb_id="92001", source="中文", relative_json_path="zh.json", card_id=20000, deck_key="200", face_url="zh-front", back_url="zh-back", unique_back=True),
    ])
    await db.commit()
    en_tts = (await db.execute(select(TTSCardImage).where(TTSCardImage.source == "英文", TTSCardImage.arkhamdb_id == "92001"))).scalars().first()

    monkeypatch.setattr("app.services.mapping_index.load_mapping_index", lambda: {
        "version": 1,
        "cards": {
            "92001": {
                "faces": {
                    "a": {"英文": {"tts_id": en_tts.id, "tts_side": "back"}},
                    "b": {"英文": {"tts_id": en_tts.id, "tts_side": "front"}},
                }
            }
        },
    })

    from app.services.mapping_index import resolve_card_image_mappings
    items = await resolve_card_image_mappings(db, "92001")
    by_key = {(item["local_face"], item["source"]): item for item in items}

    assert by_key[("a", "英文")]["tts_side"] == "back"
    assert by_key[("a", "中文")]["tts_side"] == "back"
    assert by_key[("b", "英文")]["tts_side"] == "front"
    assert by_key[("b", "中文")]["tts_side"] == "front"


@pytest.mark.asyncio
async def test_lookup_id_from_import_guides_chinese_candidate(db, monkeypatch):
    """注意.txt 导入的 tts_lookup_id 应同时驱动英文对齐和中文目标查找。"""
    card = CardIndex(arkhamdb_id="93001", name_zh="ID替换测试", category="剧本卡")
    lookup_card = CardIndex(arkhamdb_id="93001b", name_zh="ID替换目标", category="剧本卡")
    db.add_all([card, lookup_card])
    await db.flush()
    db.add(LocalCardFile(arkhamdb_id="93001", face="a", relative_path="93001_a.card", content_hash="a", last_modified="0"))
    db.add_all([
        TTSCardImage(arkhamdb_id="93001b", source="英文", relative_json_path="en-b.json", card_id=30000, deck_key="300", face_url="en-front", back_url="en-back", unique_back=True),
        TTSCardImage(arkhamdb_id="93001b", source="中文", relative_json_path="zh-b.json", card_id=40000, deck_key="400", face_url="zh-front", back_url="zh-back", unique_back=True),
    ])
    await db.commit()
    en_tts = (await db.execute(select(TTSCardImage).where(TTSCardImage.source == "英文", TTSCardImage.arkhamdb_id == "93001b"))).scalars().first()

    monkeypatch.setattr("app.services.mapping_index.load_mapping_index", lambda: {
        "version": 1,
        "cards": {
            "93001": {
                "faces": {
                    "a": {"英文": {"tts_id": en_tts.id, "tts_side": "front", "tts_lookup_id": "93001b"}},
                }
            }
        },
    })

    from app.services.mapping_index import resolve_card_image_mappings
    items = await resolve_card_image_mappings(db, "93001")
    by_key = {(item["local_face"], item["source"]): item for item in items}

    assert by_key[("a", "英文")]["relative_json_path"] == "en-b.json"
    assert by_key[("a", "中文")]["relative_json_path"] == "zh-b.json"


def test_mapping_side_prefers_notes_for_single_location_card():
    from scripts.import_mapping_index import side_from_card_content

    side, reason = side_from_card_content({"type": "地点卡", "location_type": "已揭示", "Notes": "front"}, "a")

    assert side == "front"
    assert reason == "card_notes"


def test_mapping_side_uses_location_type_for_ambiguous_location_pair():
    from types import SimpleNamespace

    from scripts.import_mapping_index import resolve_location_pair_overrides

    front_file = SimpleNamespace(id=1)
    back_file = SimpleNamespace(id=2)
    overrides = resolve_location_pair_overrides([
        (front_file, {"type": "地点卡", "location_type": "未揭示", "Notes": "back"}),
        (back_file, {"type": "地点卡", "location_type": "已揭示", "Notes": "back"}),
    ])

    assert overrides == {
        1: ("front", "location_type_unrevealed"),
        2: ("back", "location_type_revealed"),
    }


def test_tts_candidate_priority_prefers_parent_card_object():
    from types import SimpleNamespace

    from scripts.import_mapping_index import tts_candidate_priority

    parent = SimpleNamespace(relative_json_path="RolandBanks.9e9e98.json", id=15405)
    state = SimpleNamespace(relative_json_path="RolandBanks.9e9e98/RolandBanks.a684e0.json", id=15403)
    promo = SimpleNamespace(relative_json_path="RolandBanks.9e9e98/RolandBankspromoversion.e46857.json", id=15404)

    assert sorted([state, promo, parent], key=tts_candidate_priority) == [parent, state, promo]


def test_single_sided_back_override_updates_tts_bag(monkeypatch):
    """单面卡发布包应使用映射索引中的本地预发布卡背。"""
    from app.services import url_replacer

    monkeypatch.setattr(url_replacer, "load_mapping_index", lambda: {
        "version": 1,
        "cards": {
            "99001": {
                "faces": {
                    "a": {
                        "back_override": {
                            "preset_key": "player_card_back",
                            "back_url": "player-back-url",
                        }
                    }
                }
            }
        },
    })

    bag = url_replacer.generate_tts_bag_json(
        [{"arkhamdb_id": "99001", "name_zh": "测试卡", "sheet_name": "sheet-a", "unique_back": True}],
        {"sheet-a": "face-url", "sheet-a-back": "wrong-back-url"},
        {"sheet-a": {"deck_key": "123", "width": 10, "height": 7}},
    )
    card = bag["测试卡.000000"]
    sheet = card["CustomDeck"]["123"]

    assert sheet["BackURL"] == "player-back-url"
    assert sheet["UniqueBack"] is False
    assert sheet["BackIsHidden"] is True


def test_double_sided_card_rejects_back_override(monkeypatch):
    """双面卡不允许写入卡背预设，避免覆盖真实背面渲染。"""
    from app.services.mapping_index import set_back_override

    with pytest.raises(ValueError, match="只有单面卡需要设置卡背预设"):
        set_back_override("99002", "a", "player_card_back", "admin", is_single_sided=False)


@pytest.mark.asyncio
async def test_local_card_tree_includes_errata_review_state(client, db):
    pending_card = CardIndex(arkhamdb_id="94001", name_zh="待审核卡", category="玩家卡", cycle="01_基础游戏")
    approved_card = CardIndex(arkhamdb_id="94002", name_zh="待发布卡", category="玩家卡", cycle="01_基础游戏")
    normal_card = CardIndex(arkhamdb_id="94003", name_zh="普通卡", category="玩家卡", cycle="01_基础游戏")
    user_a = User(username="tree_user_a", password_hash="hash", role=UserRole.ERRATA)
    user_b = User(username="tree_user_b", password_hash="hash", role=UserRole.ERRATA)
    db.add_all([pending_card, approved_card, normal_card, user_a, user_b])
    await db.flush()
    package = ErrataPackage(package_no="ERRATA-TREE", status=ErrataPackageStatus.WAITING_PUBLISH, created_by=user_a.id)
    db.add(package)
    await db.flush()
    draft_a = ErrataDraft(
        arkhamdb_id="94001",
        status=ErrataDraftStatus.ERRATA,
        original_faces={},
        modified_faces={"a": {}},
        changed_faces=["a"],
        created_by=user_a.id,
        updated_by=user_b.id,
    )
    draft_b = ErrataDraft(
        arkhamdb_id="94002",
        status=ErrataDraftStatus.WAITING_PUBLISH,
        original_faces={},
        modified_faces={"a": {}},
        changed_faces=["a"],
        package_id=package.id,
        created_by=user_a.id,
        updated_by=user_a.id,
    )
    db.add_all([
        LocalCardFile(arkhamdb_id="94001", face="a", relative_path="玩家卡/01_基础游戏/94001_a.card", content_hash="hash-a", last_modified="0"),
        LocalCardFile(arkhamdb_id="94002", face="a", relative_path="玩家卡/01_基础游戏/94002_a.card", content_hash="hash-b", last_modified="0"),
        LocalCardFile(arkhamdb_id="94003", face="a", relative_path="玩家卡/01_基础游戏/94003_a.card", content_hash="hash-c", last_modified="0"),
        draft_a,
        draft_b,
    ])
    await db.flush()
    db.add_all([
        ErrataAuditLog(draft_id=draft_a.id, arkhamdb_id="94001", user_id=user_a.id, action=ErrataAuditAction.SAVE, changed_faces=["a"]),
        ErrataAuditLog(draft_id=draft_a.id, arkhamdb_id="94001", user_id=user_b.id, action=ErrataAuditAction.SAVE, changed_faces=["a"]),
        ErrataAuditLog(draft_id=draft_b.id, arkhamdb_id="94002", user_id=user_a.id, action=ErrataAuditAction.PACKAGE, changed_faces=["a"]),
    ])
    await db.commit()

    resp = await client.get("/api/cards/tree")

    assert resp.status_code == 200
    cards = {}
    for category in resp.json()["tree"]:
        for cycle in category["children"]:
            for node in cycle["children"]:
                cards[node["key"]] = node["card"]

    assert cards["94001"]["errata_state"] == "勘误"
    assert cards["94001"]["pending_errata_count"] == 1
    assert cards["94001"]["participant_usernames"] == ["tree_user_a", "tree_user_b"]
    assert cards["94002"]["errata_state"] == "待发布"
    assert cards["94002"]["approved_errata_count"] == 1
    assert cards["94002"]["latest_batch_id"] == str(package.id)
    assert cards["94003"]["errata_state"] == "正常"
