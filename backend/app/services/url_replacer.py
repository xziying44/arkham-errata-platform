"""URL 替换服务 - 生成 TTS 存档包 + 替换中文卡牌 JSON 中的图片 URL"""

import json
from pathlib import Path

from app.services.mapping_index import load_mapping_index
from app.services.tts_object_walker import extract_tts_card_mappings


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


def extract_steam_urls_from_json(uploaded_json: dict) -> dict:
    """从 TTS 存档 JSON 中提取卡牌 URL 映射。"""
    return extract_tts_card_mappings(uploaded_json)


def _replace_card_urls_in_data(data: dict, card_id: str, mapping: dict, mapping_index: dict) -> dict:
    """返回替换 URL 后的新 TTS 卡牌 JSON 数据。"""
    next_data = json.loads(json.dumps(data, ensure_ascii=False))
    new_deck_key = mapping["deck_key"]
    next_data["CardID"] = mapping["card_id"]

    old_deck_key = (
        list(next_data.get("CustomDeck", {}).keys())[0]
        if next_data.get("CustomDeck")
        else None
    )
    sheet = next_data["CustomDeck"].pop(old_deck_key, {}) if old_deck_key else {}
    sheet["FaceURL"] = mapping["face_url"]
    sheet["BackURL"] = mapping.get("back_url", sheet.get("BackURL", ""))
    sheet["NumWidth"] = mapping.get("grid_w", sheet.get("NumWidth", 10))
    sheet["NumHeight"] = mapping.get("grid_h", sheet.get("NumHeight", 1))
    sheet["UniqueBack"] = mapping.get("unique_back", sheet.get("UniqueBack", False))
    _apply_back_override(sheet, _back_override_for(mapping_index, card_id))
    next_data["CustomDeck"] = {new_deck_key: sheet}
    return next_data


def export_chinese_card_url_replacements(
    chinese_root: Path, output_root: Path, url_mapping: dict
) -> list[str]:
    """遍历中文卡牌目录，将替换后的 JSON 导出到 output_root，不修改官方仓库。"""
    modified: list[str] = []
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

        relative_path = json_file.relative_to(chinese_root)
        next_data = _replace_card_urls_in_data(data, card_id, url_mapping[card_id], mapping_index)
        export_path = output_root / relative_path
        export_path.parent.mkdir(parents=True, exist_ok=True)
        export_path.write_text(
            json.dumps(next_data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        modified.append(str(relative_path))

    return modified


def replace_chinese_card_urls(
    chinese_root: Path, url_mapping: dict
) -> list[str]:
    """兼容旧调用：直接替换中文包。新发布流程不得调用此函数修改官方仓库。"""
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

        next_data = _replace_card_urls_in_data(data, card_id, url_mapping[card_id], mapping_index)
        json_file.write_text(
            json.dumps(next_data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        modified.append(str(json_file.relative_to(chinese_root)))

    return modified
