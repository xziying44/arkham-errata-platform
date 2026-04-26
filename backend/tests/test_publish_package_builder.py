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
