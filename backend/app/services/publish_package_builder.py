"""发布补丁包构建：生成替换计划和校验报告。"""

import json
from pathlib import Path


def _gmnotes_id(data: dict) -> str:
    try:
        notes = json.loads(data.get("GMNotes", "{}"))
    except json.JSONDecodeError:
        return ""
    card_id = notes.get("id")
    return card_id if isinstance(card_id, str) else ""


def _find_existing_chinese_cards(chinese_roots: list[tuple[str, Path]]) -> dict[str, tuple[str, Path, dict]]:
    found: dict[str, tuple[str, Path, dict]] = {}
    for relative_root, root in chinese_roots:
        if not root.exists():
            continue
        for json_file in sorted(root.rglob("*.json")):
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            if data.get("Name") != "Card":
                continue
            card_id = _gmnotes_id(data)
            if card_id and card_id not in found:
                found[card_id] = (f"{relative_root}/{json_file.relative_to(root).as_posix()}", json_file, data)
    return found


def build_replacement_plan(
    chinese_roots: list[tuple[str, Path]],
    package_cards: list[dict],
    url_mapping: dict[str, dict],
) -> list[dict]:
    existing = _find_existing_chinese_cards(chinese_roots)
    plan: list[dict] = []
    for card in package_cards:
        card_id = card["arkhamdb_id"]
        mapping = url_mapping.get(card_id)
        blocking_errors: list[str] = []
        if not mapping:
            blocking_errors.append("缺少新 URL 映射")
        if card_id in existing:
            relative_path, _path, data = existing[card_id]
            custom_deck = data.get("CustomDeck", {}) if isinstance(data.get("CustomDeck"), dict) else {}
            deck_key = next(iter(custom_deck.keys()), "")
            sheet = custom_deck.get(deck_key, {}) if deck_key else {}
            plan.append({
                "arkhamdb_id": card_id,
                "name_zh": card.get("name_zh", ""),
                "action": "替换",
                "source_path": relative_path,
                "target_path": relative_path,
                "old_face_url": sheet.get("FaceURL", "") if isinstance(sheet, dict) else "",
                "old_back_url": sheet.get("BackURL", "") if isinstance(sheet, dict) else "",
                "new_face_url": mapping.get("face_url", "") if mapping else "",
                "new_back_url": mapping.get("back_url", "") if mapping else "",
                "blocking_errors": blocking_errors,
            })
        else:
            blocking_errors.append("缺少中文 TTS 记录，需要目录预设新增对象")
            plan.append({
                "arkhamdb_id": card_id,
                "name_zh": card.get("name_zh", ""),
                "action": "新增",
                "source_path": None,
                "target_path": None,
                "old_face_url": "",
                "old_back_url": "",
                "new_face_url": mapping.get("face_url", "") if mapping else "",
                "new_back_url": mapping.get("back_url", "") if mapping else "",
                "blocking_errors": blocking_errors,
            })
    return plan
