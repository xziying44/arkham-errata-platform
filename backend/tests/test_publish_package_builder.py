import json

import pytest

from app.services.publish_package_builder import build_replacement_plan


@pytest.mark.asyncio
async def test_replacement_plan_marks_existing_card_as_replace(tmp_path):
    chinese_root = tmp_path / "zh"
    card_path = chinese_root / "pack" / "测试.abc123.json"
    card_path.parent.mkdir(parents=True)
    card_path.write_text(json.dumps({
        "Name": "Card",
        "CardID": 100,
        "GMNotes": json.dumps({"id": "01104"}),
        "CustomDeck": {"1": {"FaceURL": "old-face", "BackURL": "old-back", "NumWidth": 10, "NumHeight": 1, "UniqueBack": False}},
    }, ensure_ascii=False), encoding="utf-8")

    plan = build_replacement_plan(
        chinese_roots=[("decomposed/language-pack/Test", chinese_root)],
        package_cards=[{"arkhamdb_id": "01104", "name_zh": "测试"}],
        url_mapping={"01104": {"face_url": "new-face", "back_url": "new-back", "deck_key": "9", "card_id": 900, "grid_w": 10, "grid_h": 1, "unique_back": False}},
    )

    assert plan[0]["action"] == "替换"
    assert plan[0]["source_path"] == "decomposed/language-pack/Test/pack/测试.abc123.json"
    assert plan[0]["blocking_errors"] == []


def test_replacement_plan_blocks_missing_url_mapping(tmp_path):
    plan = build_replacement_plan(
        chinese_roots=[],
        package_cards=[{"arkhamdb_id": "09999", "name_zh": "新增卡"}],
        url_mapping={},
    )

    assert plan[0]["action"] == "新增"
    assert "缺少新 URL 映射" in plan[0]["blocking_errors"]
    assert "缺少中文 TTS 记录，需要目录预设新增对象" in plan[0]["blocking_errors"]


def test_replacement_plan_uses_directory_preset_for_new_card(tmp_path):
    plan = build_replacement_plan(
        chinese_roots=[],
        package_cards=[{"arkhamdb_id": "09999", "name_zh": "新增场景", "local_relative_path": "剧本卡/09_绯红密钥/09999_a.card"}],
        url_mapping={"09999": {"face_url": "new-face", "back_url": "new-back", "deck_key": "9", "card_id": 900, "grid_w": 1, "grid_h": 1, "unique_back": False}},
        directory_presets=[{
            "local_dir_prefix": "剧本卡/09_绯红密钥",
            "target_bag_path": "decomposed/language-pack/Simplified Chinese - Campaigns/Pack/Scarlet.abc123.json",
            "target_object_dir": "Scarlet.abc123",
            "target_bag_guid": "abc123",
            "is_active": True,
        }],
    )

    assert plan[0]["action"] == "新增"
    assert plan[0]["blocking_errors"] == []
    assert plan[0]["target_path"].startswith("decomposed/language-pack/Simplified Chinese - Campaigns/Pack/Scarlet.abc123/")
    assert plan[0]["target_bag_path"].endswith("Scarlet.abc123.json")


def test_replacement_plan_strips_medal_from_new_card_filename(tmp_path):
    plan = build_replacement_plan(
        chinese_roots=[],
        package_cards=[{"arkhamdb_id": "09538", "name_zh": "🏅拉辛·法瑞", "local_relative_path": "剧本卡/09_绯红密钥/09538_a.card"}],
        url_mapping={"09538": {"face_url": "new-face", "back_url": "", "deck_key": "9", "card_id": 953800, "grid_w": 1, "grid_h": 1, "unique_back": False}},
        directory_presets=[{
            "local_dir_prefix": "剧本卡/09_绯红密钥",
            "target_bag_path": "decomposed/language-pack/Simplified Chinese - Campaigns/Pack/Scarlet.abc123.json",
            "target_object_dir": "Scarlet.abc123",
            "target_bag_guid": "abc123",
            "is_active": True,
        }],
    )

    assert "🏅" not in plan[0]["target_path"]
    assert "拉辛·法瑞" in plan[0]["target_path"]
