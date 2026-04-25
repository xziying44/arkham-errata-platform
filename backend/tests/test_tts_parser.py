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
