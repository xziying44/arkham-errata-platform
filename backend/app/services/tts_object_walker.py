"""TTS 对象遍历器：从多种 TTS JSON 结构中提取卡牌 URL 映射。"""

import json
from typing import Any


def _load_gmnotes_id(raw_notes: Any) -> str:
    if not isinstance(raw_notes, str) or not raw_notes.strip():
        return ""
    try:
        notes = json.loads(raw_notes)
    except json.JSONDecodeError:
        return ""
    card_id = notes.get("id")
    return card_id if isinstance(card_id, str) else ""


def _extract_card(obj: dict, source_path: str) -> tuple[str, dict] | None:
    if obj.get("Name") != "Card":
        return None
    arkhamdb_id = _load_gmnotes_id(obj.get("GMNotes"))
    if not arkhamdb_id:
        return None
    custom_deck = obj.get("CustomDeck") if isinstance(obj.get("CustomDeck"), dict) else {}
    deck_key = next(iter(custom_deck.keys()), "")
    sheet = custom_deck.get(deck_key, {}) if deck_key else {}
    if not isinstance(sheet, dict):
        sheet = {}
    return arkhamdb_id, {
        "face_url": sheet.get("FaceURL", ""),
        "back_url": sheet.get("BackURL", ""),
        "card_id": obj.get("CardID", 0),
        "deck_key": deck_key,
        "grid_w": sheet.get("NumWidth", 10),
        "grid_h": sheet.get("NumHeight", 1),
        "unique_back": sheet.get("UniqueBack", False),
        "source_path": source_path,
    }


def _walk(obj: Any, source_path: str, mapping: dict[str, dict], seen: set[int]) -> None:
    if not isinstance(obj, dict):
        return
    marker = id(obj)
    if marker in seen:
        return
    seen.add(marker)

    extracted = _extract_card(obj, source_path)
    if extracted:
        arkhamdb_id, payload = extracted
        mapping[arkhamdb_id] = payload

    children = obj.get("ContainedObjects")
    if isinstance(children, list):
        for index, child in enumerate(children):
            _walk(child, f"{source_path}.ContainedObjects[{index}]", mapping, seen)

    order = obj.get("ContainedObjects_order")
    if isinstance(order, list):
        for key in order:
            if isinstance(key, str) and isinstance(obj.get(key), dict):
                _walk(obj[key], f"{source_path}.{key}", mapping, seen)

    for key, value in obj.items():
        if key in {"CustomDeck", "Transform"}:
            continue
        if isinstance(value, dict) and value.get("Name") in {"Card", "Custom_Model_Bag", "Deck"}:
            _walk(value, f"{source_path}.{key}", mapping, seen)


def extract_tts_card_mappings(uploaded_json: dict) -> dict[str, dict]:
    mapping: dict[str, dict] = {}
    seen: set[int] = set()
    object_states = uploaded_json.get("ObjectStates")
    if isinstance(object_states, list):
        for index, obj in enumerate(object_states):
            _walk(obj, f"ObjectStates[{index}]", mapping, seen)
    else:
        _walk(uploaded_json, "$", mapping, seen)
    return mapping
