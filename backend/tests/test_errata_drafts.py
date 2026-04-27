import json

import pytest
from httpx import AsyncClient
from pathlib import Path
from sqlalchemy import select

from app.config import settings
from app.models.card import CardIndex, LocalCardFile
from app.models.errata_draft import ErrataAuditLog, ErrataDraft, ErrataDraftStatus
from app.models.user import User, UserRole
from app.services.local_card_index import build_local_card_index, search_local_card_index
from app.utils.security import hash_password


async def login_token(client: AsyncClient, username: str, password: str) -> str:
    response = await client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return response.json()["token"]


@pytest.mark.asyncio
async def test_multiple_users_update_one_active_draft(client: AsyncClient, db, monkeypatch, tmp_path):
    def fake_render(content, output_dir, filename, dpi=150, quality=90):
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / f"{filename}.jpg"
        path.write_text("ok", encoding="utf-8")
        return str(path)

    monkeypatch.setattr("app.services.errata_drafts.render_card_preview", fake_render)

    card = CardIndex(arkhamdb_id="01001", name_zh="罗兰·班克斯", category="玩家卡")
    file_a = LocalCardFile(arkhamdb_id="01001", face="a", relative_path="玩家卡/01001_a.card")
    file_b = LocalCardFile(arkhamdb_id="01001", face="b", relative_path="玩家卡/01001_b.card")
    alice = User(username="alice", password_hash=hash_password("pw"), role=UserRole.ERRATA)
    bob = User(username="bob", password_hash=hash_password("pw"), role=UserRole.ERRATA)
    db.add_all([card, file_a, file_b, alice, bob])
    await db.commit()

    alice_token = await login_token(client, "alice", "pw")
    bob_token = await login_token(client, "bob", "pw")

    first = await client.put(
        "/api/errata-drafts/01001",
        headers={"Authorization": f"Bearer {alice_token}"},
        json={
            "modified_faces": {"a": {"name": "罗兰·班克斯", "body": "第一次修改"}, "b": {"name": "背面"}},
            "changed_faces": ["a"],
            "diff_summary": "alice 修改正面",
        },
    )
    assert first.status_code == 200

    second = await client.put(
        "/api/errata-drafts/01001",
        headers={"Authorization": f"Bearer {bob_token}"},
        json={
            "modified_faces": {"a": {"name": "罗兰·班克斯", "body": "第二次修改"}, "b": {"name": "背面"}},
            "changed_faces": ["a"],
            "diff_summary": "bob 修改正面",
        },
    )
    assert second.status_code == 200
    assert second.json()["participant_usernames"] == ["alice", "bob"]
    assert second.json()["modified_faces"]["a"]["body"] == "第二次修改"
    assert second.json()["rendered_previews"]["a"].startswith("/static/cache/previews/errata_01001_a")

    drafts = (await db.execute(select(ErrataDraft).where(ErrataDraft.arkhamdb_id == "01001"))).scalars().all()
    assert len(drafts) == 1

    logs = (await db.execute(select(ErrataAuditLog).where(ErrataAuditLog.arkhamdb_id == "01001"))).scalars().all()
    assert len(logs) == 3


@pytest.mark.asyncio
async def test_waiting_publish_draft_is_locked(client: AsyncClient, db, monkeypatch, tmp_path):
    def fake_render(content, output_dir, filename, dpi=150, quality=90):
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / f"{filename}.jpg"
        path.write_text("ok", encoding="utf-8")
        return str(path)

    monkeypatch.setattr("app.services.errata_drafts.render_card_preview", fake_render)

    card = CardIndex(arkhamdb_id="01002", name_zh="黛西·沃克", category="玩家卡")
    file_a = LocalCardFile(arkhamdb_id="01002", face="a", relative_path="玩家卡/01002_a.card")
    user = User(username="locked-user", password_hash=hash_password("pw"), role=UserRole.ERRATA)
    db.add_all([card, file_a, user])
    await db.commit()

    token = await login_token(client, "locked-user", "pw")
    created = await client.put(
        "/api/errata-drafts/01002",
        headers={"Authorization": f"Bearer {token}"},
        json={"modified_faces": {"a": {"name": "黛西"}}, "changed_faces": ["a"]},
    )
    assert created.status_code == 200

    draft = (await db.execute(select(ErrataDraft).where(ErrataDraft.arkhamdb_id == "01002"))).scalar_one()
    draft.status = ErrataDraftStatus.WAITING_PUBLISH
    await db.commit()

    response = await client.put(
        "/api/errata-drafts/01002",
        headers={"Authorization": f"Bearer {token}"},
        json={"modified_faces": {"a": {"name": "锁定后修改"}}, "changed_faces": ["a"]},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "该卡牌已进入待发布包，请管理员解锁后再修改"


@pytest.mark.asyncio
async def test_save_draft_rejects_when_preview_render_fails(client: AsyncClient, db, monkeypatch):
    card = CardIndex(arkhamdb_id="01003", name_zh="坏 JSON 卡", category="玩家卡")
    file_a = LocalCardFile(arkhamdb_id="01003", face="a", relative_path="玩家卡/01003_a.card")
    user = User(username="render-user", password_hash=hash_password("pw"), role=UserRole.ERRATA)
    db.add_all([card, file_a, user])
    await db.commit()

    monkeypatch.setattr("app.services.errata_drafts.render_card_preview", lambda *args, **kwargs: None)
    token = await login_token(client, "render-user", "pw")
    response = await client.put(
        "/api/errata-drafts/01003",
        headers={"Authorization": f"Bearer {token}"},
        json={"modified_faces": {"a": {"name": "坏 JSON 卡"}}, "changed_faces": ["a"]},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "a 面渲染失败，请先修正 JSON 或卡图资源后再保存"
    drafts = (await db.execute(select(ErrataDraft).where(ErrataDraft.arkhamdb_id == "01003"))).scalars().all()
    assert drafts == []


@pytest.mark.asyncio
async def test_save_draft_updates_card_tree_content_index(client: AsyncClient, db, monkeypatch, tmp_path):
    project_root = tmp_path / "project"
    card_root = project_root / "cards"
    card_dir = card_root / "玩家卡" / "01_基础游戏"
    card_dir.mkdir(parents=True)
    relative_path = Path("玩家卡/01_基础游戏/01008_a.card")
    (card_root / relative_path).write_text(
        '{"name":"原始标题","subtitle":"原始副标题","body":"原始内容"}',
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "project_root", project_root)
    monkeypatch.setattr(settings, "local_card_db", Path("cards"))
    monkeypatch.setattr(settings, "cache_dir", Path("cache"))

    def fake_render(content, output_dir, filename, dpi=150, quality=90):
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / f"{filename}.jpg"
        path.write_text("ok", encoding="utf-8")
        return str(path)

    monkeypatch.setattr("app.services.errata_drafts.render_card_preview", fake_render)

    card = CardIndex(arkhamdb_id="01008", name_zh="原始标题", category="玩家卡", cycle="01_基础游戏")
    file_a = LocalCardFile(
        arkhamdb_id="01008",
        face="a",
        relative_path=relative_path.as_posix(),
        content_hash="hash",
        last_modified="0",
    )
    user = User(username="index-user", password_hash=hash_password("pw"), role=UserRole.ERRATA)
    reviewer = User(username="index-reviewer", password_hash=hash_password("pw"), role=UserRole.REVIEWER)
    db.add_all([card, file_a, user, reviewer])
    await db.commit()

    token = await login_token(client, "index-user", "pw")
    save_response = await client.put(
        "/api/errata-drafts/01008",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "modified_faces": {
                "a": {
                    "name": "勘误后标题",
                    "subtitle": "勘误后副标题",
                    "body": "唯一勘误搜索词",
                }
            },
            "changed_faces": ["a"],
        },
    )
    assert save_response.status_code == 200
    local_card_root = settings.project_root / settings.local_card_db
    assert relative_path.as_posix() in search_local_card_index(local_card_root, "唯一勘误搜索词")

    build_local_card_index(local_card_root)

    tree_response = await client.get("/api/cards/tree", params={"keyword": "唯一勘误搜索词"})

    assert tree_response.status_code == 200
    cards = {}
    for category in tree_response.json()["tree"]:
        for cycle in category["children"]:
            for node in cycle["children"]:
                cards[node["key"]] = node["card"]
    assert cards["01008"]["face_titles"]["a"] == "勘误后标题"
    assert cards["01008"]["face_subtitles"]["a"] == "勘误后副标题"

    reviewer_token = await login_token(client, "index-reviewer", "pw")
    cancel_response = await client.post(
        "/api/errata-drafts/01008/cancel",
        headers={"Authorization": f"Bearer {reviewer_token}"},
        json={"note": "恢复索引测试"},
    )
    assert cancel_response.status_code == 200

    stale_response = await client.get("/api/cards/tree", params={"keyword": "唯一勘误搜索词"})
    assert stale_response.status_code == 200
    assert "01008" not in json.dumps(stale_response.json(), ensure_ascii=False)

    original_response = await client.get("/api/cards/tree", params={"keyword": "原始内容"})
    assert original_response.status_code == 200
    original_cards = {}
    for category in original_response.json()["tree"]:
        for cycle in category["children"]:
            for node in cycle["children"]:
                original_cards[node["key"]] = node["card"]
    assert original_cards["01008"]["face_titles"]["a"] == "原始标题"
    assert original_cards["01008"]["face_subtitles"]["a"] == "原始副标题"


@pytest.mark.asyncio
async def test_reviewer_can_cancel_errata_draft_to_normal(client: AsyncClient, db):
    card = CardIndex(arkhamdb_id="01988", name_zh="误点卡", category="玩家卡", cycle="01_基础游戏")
    file_a = LocalCardFile(arkhamdb_id="01988", face="a", relative_path="玩家卡/01988_a.card")
    owner = User(username="cancel-owner", password_hash=hash_password("pw"), role=UserRole.ERRATA)
    reviewer = User(username="cancel-reviewer", password_hash=hash_password("pw"), role=UserRole.REVIEWER)
    db.add_all([card, file_a, owner, reviewer])
    await db.commit()
    await db.refresh(owner)

    draft = ErrataDraft(
        arkhamdb_id="01988",
        status=ErrataDraftStatus.ERRATA,
        original_faces={"a": {"name": "误点卡"}},
        modified_faces={"a": {"name": "误点卡"}},
        changed_faces=["a"],
        created_by=owner.id,
        updated_by=owner.id,
    )
    db.add(draft)
    await db.commit()

    token = await login_token(client, "cancel-reviewer", "pw")
    response = await client.post(
        "/api/errata-drafts/01988/cancel",
        headers={"Authorization": f"Bearer {token}"},
        json={"note": "用户点错了"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "正常"

    await db.refresh(draft)
    assert draft.status == ErrataDraftStatus.ARCHIVED
    assert draft.archived_at is not None

    tree = await client.get("/api/cards/tree")
    cards = {}
    for category in tree.json()["tree"]:
        for cycle in category["children"]:
            for node in cycle["children"]:
                cards[node["key"]] = node["card"]
    assert cards["01988"]["errata_state"] == "正常"

    logs = await client.get("/api/errata-drafts/01988/logs", headers={"Authorization": f"Bearer {token}"})
    assert any(log["action"] == "取消勘误" for log in logs.json())
