"""URL 替换服务 - 生成 TTS 存档包 + 替换中文卡牌 JSON 中的图片 URL"""

import json
from pathlib import Path

from app.services.mapping_index import load_mapping_index


def _back_override_for(index: dict, arkhamdb_id: str) -> dict | None:
    record = index.get("cards", {}).get(arkhamdb_id, {})
    faces = record.get("faces", {}) if isinstance(record, dict) else {}
    for face_record in faces.values():
        if isinstance(face_record, dict) and isinstance(face_record.get("back_override"), dict):
            return face_record["back_override"]
    return None


def _apply_back_override(sheet: dict, override: dict | None) -> None:
    if not override or not override.get("back_url"):
        return
    sheet["BackURL"] = override["back_url"]
    sheet["UniqueBack"] = False
    sheet["BackIsHidden"] = True


def generate_tts_bag_json(
    approved_cards: list[dict],
    sheet_urls: dict[str, str],
    sheet_grids: dict[str, dict],
    template_path: str | None = None,
) -> dict:
    """根据已批准的勘误卡牌生成 TTS 存档包 JSON

    Args:
        approved_cards: 已批准的卡牌列表，每项包含 arkhamdb_id, name_zh, sheet_name 等
        sheet_urls: {sheet_name: url} 精灵图 URL 映射
        sheet_grids: {sheet_name: {deck_key, width, height}} 精灵图网格信息
        template_path: 可选的模板路径（保留参数，当前未使用）

    Returns:
        TTS Custom Model Bag JSON 对象
    """
    bag = {
        "Name": "Custom_Model_Bag",
        "GUID": "000000",
        "Nickname": "勘误发布包",
        "Transform": {"scaleX": 1, "scaleY": 1, "scaleZ": 1},
        "ContainedObjects_order": [],
        "ContainedObjects_path": "",
    }

    mapping_index = load_mapping_index()

    for idx, card in enumerate(approved_cards):
        sheet_name = card.get("sheet_name", "")
        sheet_info = sheet_grids.get(sheet_name, {})
        deck_key = sheet_info.get("deck_key", "10000")

        sheet = {
            "FaceURL": sheet_urls.get(sheet_name, ""),
            "BackURL": sheet_urls.get(
                f"{sheet_name}-back", sheet_urls.get(sheet_name, "")
            ),
            "NumWidth": sheet_info.get("width", 10),
            "NumHeight": sheet_info.get("height", 1),
            "Type": 0,
            "UniqueBack": card.get("unique_back", False),
            "BackIsHidden": True,
        }
        _apply_back_override(sheet, _back_override_for(mapping_index, card["arkhamdb_id"]))

        card_obj = {
            "Name": "Card",
            "GUID": f"{idx:06x}",
            "Nickname": card.get("name_zh", ""),
            "CardID": int(deck_key) * 100 + (idx % 100),
            "GMNotes": json.dumps(
                {"id": card["arkhamdb_id"]}, ensure_ascii=False
            ),
            "Transform": {"scaleX": 1, "scaleY": 1, "scaleZ": 1},
            "CustomDeck": {deck_key: sheet},
        }

        bag["ContainedObjects_order"].append(
            f"{card_obj['Nickname']}.{card_obj['GUID']}"
        )
        # 将卡牌对象作为动态键添加到 bag 中
        bag[f"{card_obj['Nickname']}.{card_obj['GUID']}"] = card_obj

    return bag


def _extract_from_object(obj: dict, mapping: dict):
    """从 TTS 对象中递归提取卡牌 URL 映射信息"""
    if obj.get("Name") == "Card":
        try:
            gm = json.loads(obj.get("GMNotes", "{}"))
            card_id = gm.get("id", "")
            if card_id:
                custom_deck = obj.get("CustomDeck", {})
                deck_key = list(custom_deck.keys())[0] if custom_deck else ""
                sheet = custom_deck.get(deck_key, {})
                mapping[card_id] = {
                    "face_url": sheet.get("FaceURL", ""),
                    "back_url": sheet.get("BackURL", ""),
                    "card_id": obj.get("CardID", 0),
                    "deck_key": deck_key,
                    "grid_w": sheet.get("NumWidth", 10),
                    "grid_h": sheet.get("NumHeight", 1),
                    "unique_back": sheet.get("UniqueBack", False),
                }
        except (json.JSONDecodeError, KeyError):
            pass

    for child in obj.get("ContainedObjects", []):
        _extract_from_object(child, mapping)


def extract_steam_urls_from_json(uploaded_json: dict) -> dict:
    """从 TTS 存档 JSON 中提取卡牌 URL 映射

    Args:
        uploaded_json: TTS 存档 JSON 数据（已解析为 dict）

    Returns:
        {arkhamdb_id: {face_url, back_url, card_id, deck_key, grid_w, grid_h, ...}} 映射表
    """
    mapping = {}
    for obj in uploaded_json.get("ObjectStates", []):
        _extract_from_object(obj, mapping)
    return mapping


def replace_chinese_card_urls(
    chinese_root: Path, url_mapping: dict
) -> list[str]:
    """遍历中文卡牌目录，替换 .card JSON 中的图片 URL

    Args:
        chinese_root: 中文卡牌 JSON 文件根目录
        url_mapping: 从 extract_steam_urls_from_json 获取的 URL 映射表

    Returns:
        被修改的文件相对路径列表
    """
    modified = []
    mapping_index = load_mapping_index()

    for json_file in sorted(chinese_root.rglob("*.json")):
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue

        if data.get("Name") != "Card":
            continue

        try:
            gm = json.loads(data.get("GMNotes", "{}"))
            card_id = gm.get("id", "")
        except json.JSONDecodeError:
            continue

        if card_id not in url_mapping:
            continue

        mapping = url_mapping[card_id]
        new_deck_key = mapping["deck_key"]

        data["CardID"] = mapping["card_id"]

        # 替换 CustomDeck 中的 URL
        old_deck_key = (
            list(data.get("CustomDeck", {}).keys())[0]
            if data.get("CustomDeck")
            else None
        )
        sheet = data["CustomDeck"].pop(old_deck_key, {}) if old_deck_key else {}

        sheet["FaceURL"] = mapping["face_url"]
        sheet["BackURL"] = mapping.get("back_url", sheet.get("BackURL", ""))
        sheet["NumWidth"] = mapping.get("grid_w", sheet.get("NumWidth", 10))
        sheet["NumHeight"] = mapping.get("grid_h", sheet.get("NumHeight", 1))
        sheet["UniqueBack"] = mapping.get("unique_back", sheet.get("UniqueBack", False))
        _apply_back_override(sheet, _back_override_for(mapping_index, card_id))
        data["CustomDeck"] = {new_deck_key: sheet}

        json_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        modified.append(str(json_file.relative_to(chinese_root)))

    return modified
