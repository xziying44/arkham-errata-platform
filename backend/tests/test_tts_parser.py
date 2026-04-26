import json
import tempfile
from pathlib import Path
from app.services.tts_parser import parse_tts_card_json, scan_tts_directory, extract_arkhamdb_id

SAMPLE_CARD = {
    "CardID": 232405,
    "CustomDeck": {
        "2324": {
            "FaceURL": "https://example.com/face.jpg",
            "BackURL": "https://example.com/back.jpg",
            "NumWidth": 10,
            "NumHeight": 2,
            "UniqueBack": True
        }
    },
    "GMNotes": '{\n  "id": "01150"\n}',
    "GUID": "abc123",
    "Name": "Card",
    "Nickname": "Test Card",
    "SidewaysCard": False
}


def test_extract_arkhamdb_id():
    assert extract_arkhamdb_id('{"id": "01150"}') == "01150"
    assert extract_arkhamdb_id('{"id": "01033-t"}') == "01033-t"
    assert extract_arkhamdb_id('{"id": "7f2a7b44-7e7d-4523-8709-f90177100575"}') is None
    assert extract_arkhamdb_id("{}") is None


def test_parse_tts_card_json():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        filepath = root / "TestCard.abc123.json"
        filepath.write_text(json.dumps(SAMPLE_CARD))
        card = parse_tts_card_json(filepath, "英文", root)
        assert card is not None
        assert card.arkhamdb_id == "01150"
        assert card.deck_key == "2324"
        assert card.grid_position == 5
        assert card.grid_height == 2
        assert card.face_url == "https://example.com/face.jpg"
        assert card.unique_back is True


def test_scan_tts_directory():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        sub = root / "TestCampaign" / "TestScenario"
        sub.mkdir(parents=True)
        (sub / "Card1.abc.json").write_text(json.dumps(SAMPLE_CARD))
        bag = {"Name": "Custom_Model_Bag", "GUID": "xyz"}
        (sub / "Bag.xyz.json").write_text(json.dumps(bag))
        cards = scan_tts_directory(root, "英文")
        assert len(cards) == 1
        assert cards[0].arkhamdb_id == "01150"


def test_parse_tts_card_json_reads_companion_gmnotes():
    """英文 SCED 数据常把 GMNotes 放在同名 .gmnotes 文件中"""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        filepath = root / "Study.377b20.json"
        card_data = dict(SAMPLE_CARD)
        card_data.pop("GMNotes")
        card_data["GMNotes_path"] = "Study.377b20.gmnotes"
        filepath.write_text(json.dumps(card_data), encoding="utf-8")
        filepath.with_suffix(".gmnotes").write_text(
            json.dumps({"id": "01111", "type": "Location"}), encoding="utf-8"
        )

        card = parse_tts_card_json(filepath, "英文", root)

        assert card is not None
        assert card.arkhamdb_id == "01111"


def test_scan_sced_player_card_fixture_if_present():
    from app.config import settings

    root = settings.project_root / settings.sced_repo / "objects" / "AllPlayerCards.15bb07"
    if not root.exists():
        return

    cards = scan_tts_directory(root, "英文")
    roland_cards = [card for card in cards if card.arkhamdb_id == "01001"]

    assert roland_cards
    assert any(card.relative_json_path == "RolandBanks.9e9e98/RolandBanks.a684e0.json" for card in roland_cards)
    assert all(not Path(card.relative_json_path).is_absolute() for card in roland_cards)
    assert all("SCED/objects/AllPlayerCards.15bb07" not in card.relative_json_path for card in roland_cards)
