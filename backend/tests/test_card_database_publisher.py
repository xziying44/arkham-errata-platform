import json
from pathlib import Path

import pytest

from app.config import settings
from app.models.card import CardIndex, LocalCardFile
from app.models.errata_draft import ErrataDraft, ErrataDraftStatus, ErrataPackage, ErrataPackageStatus
from app.models.user import User, UserRole
from app.services.card_database_publisher import publish_package_to_card_database
from app.utils.security import hash_password


@pytest.mark.asyncio
async def test_publish_package_to_card_database_preserves_picture_base64_and_commits(db, tmp_path, monkeypatch):
    project_root = tmp_path / "project"
    card_root = project_root / "cards"
    card_dir = card_root / "剧本卡" / "01_基础游戏"
    card_dir.mkdir(parents=True)
    card_path = card_dir / "01104_a.card"
    card_path.write_text(json.dumps({"name": "旧名称", "picture_base64": "BASE64_OLD"}, ensure_ascii=False, indent=2), encoding="utf-8")

    import subprocess
    subprocess.run([settings.git_executable, "init"], cwd=card_root, check=True, capture_output=True)
    subprocess.run([settings.git_executable, "add", "剧本卡/01_基础游戏/01104_a.card"], cwd=card_root, check=True, capture_output=True)
    subprocess.run([
        settings.git_executable,
        "-c",
        "user.name=xziying",
        "-c",
        "user.email=xziying@vip.qq.com",
        "commit",
        "-m",
        "初始化卡牌",
    ], cwd=card_root, check=True, capture_output=True)

    monkeypatch.setattr(settings, "project_root", project_root)
    monkeypatch.setattr(settings, "local_card_db", Path("cards"))

    admin = User(username="publisher", password_hash=hash_password("pw"), role=UserRole.ADMIN)
    card = CardIndex(arkhamdb_id="01104", name_zh="旧名称", category="剧本卡", cycle="01_基础游戏")
    file_record = LocalCardFile(
        arkhamdb_id="01104",
        face="a",
        relative_path="剧本卡/01_基础游戏/01104_a.card",
        content_hash="old",
        last_modified="0",
    )
    db.add(admin)
    await db.flush()
    package = ErrataPackage(package_no="ERRATA-TEST", status=ErrataPackageStatus.WAITING_PUBLISH, created_by=admin.id)
    db.add_all([card, file_record, package])
    await db.flush()
    draft = ErrataDraft(
        arkhamdb_id="01104",
        status=ErrataDraftStatus.WAITING_PUBLISH,
        original_faces={"a": {"picture_base64": "BASE64_OLD"}},
        modified_faces={"a": {"name": "新名称"}},
        changed_faces=["a"],
        package_id=package.id,
        created_by=admin.id,
        updated_by=admin.id,
    )
    db.add(draft)
    await db.commit()

    result = await publish_package_to_card_database(db, package, [draft])

    saved = json.loads(card_path.read_text(encoding="utf-8"))
    assert saved["name"] == "新名称"
    assert saved["picture_base64"] == "BASE64_OLD"
    assert result["written_files"] == ["剧本卡/01_基础游戏/01104_a.card"]
    assert result["commit"]
    assert file_record.content_hash != "old"
