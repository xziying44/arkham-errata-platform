import json

from app.services.tts_object_walker import extract_tts_card_mappings


def _card(card_id: str, guid: str = "abc123") -> dict:
    return {
        "Name": "Card",
        "GUID": guid,
        "Nickname": f"卡{card_id}",
        "CardID": 123405,
        "GMNotes": json.dumps({"id": card_id}, ensure_ascii=False),
        "CustomDeck": {
            "1234": {
                "FaceURL": f"https://example.com/{card_id}-face.jpg",
                "BackURL": f"https://example.com/{card_id}-back.jpg",
                "NumWidth": 10,
                "NumHeight": 3,
                "UniqueBack": True,
            }
        },
    }


def test_extract_from_object_states_save():
    data = {"ObjectStates": [{"Name": "Custom_Model_Bag", "ContainedObjects": [_card("01104")]}]}
    mapping = extract_tts_card_mappings(data)
    assert mapping["01104"]["face_url"] == "https://example.com/01104-face.jpg"
    assert mapping["01104"]["deck_key"] == "1234"
    assert mapping["01104"]["source_path"].endswith("ObjectStates[0].ContainedObjects[0]")


def test_extract_from_single_dynamic_bag():
    card = _card("01105", "def456")
    data = {
        "Name": "Custom_Model_Bag",
        "GUID": "000000",
        "ContainedObjects_order": ["测试.def456"],
        "测试.def456": card,
    }
    mapping = extract_tts_card_mappings(data)
    assert set(mapping) == {"01105"}
    assert mapping["01105"]["card_id"] == 123405


def test_extract_from_single_card():
    mapping = extract_tts_card_mappings(_card("01001"))
    assert mapping["01001"]["grid_w"] == 10
    assert mapping["01001"]["grid_h"] == 3
