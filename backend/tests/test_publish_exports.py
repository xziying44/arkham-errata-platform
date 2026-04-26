import json
from pathlib import Path

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
