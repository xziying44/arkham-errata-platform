import json
import re
from pathlib import Path
from dataclasses import dataclass
from typing import Optional


@dataclass
class ParsedTTSCard:
    """解析后的 TTS 卡牌数据"""
    arkhamdb_id: str
    source: str
    relative_json_path: str
    card_id: int
    deck_key: str
    face_url: str
    back_url: str
    grid_width: int
    grid_height: int
    grid_position: int
    unique_back: bool
    nickname: str
    guid: str
    sideways_card: bool


def parse_gmnotes(gmnotes_raw: str) -> dict:
    """解析 GMNotes JSON 字符串"""
    try:
        return json.loads(gmnotes_raw)
    except json.JSONDecodeError:
        return {}


def extract_arkhamdb_id(gmnotes_raw: str) -> Optional[str]:
    """从 GMNotes 提取 arkhamdb id"""
    data = parse_gmnotes(gmnotes_raw)
    card_id = data.get("id")
    if not isinstance(card_id, str):
        return None
    if not re.fullmatch(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)?", card_id):
        return None
    if len(card_id) > 16:
        return None
    return card_id


def load_gmnotes(data: dict, filepath: Path, root: Path) -> str:
    """读取 TTS 卡牌的 GMNotes，兼容内嵌字段和伴生 .gmnotes 文件"""
    gmnotes = data.get("GMNotes")
    if gmnotes:
        return gmnotes

    candidates = [filepath.with_suffix(".gmnotes")]
    gmnotes_path = data.get("GMNotes_path")
    if gmnotes_path:
        candidates.append(root / gmnotes_path)
        candidates.append(filepath.parent / Path(gmnotes_path).name)

    for candidate in candidates:
        if candidate.exists():
            try:
                return candidate.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
    return "{}"


def parse_tts_card_json(filepath: Path, source: str, root: Path) -> Optional[ParsedTTSCard]:
    """解析单个 TTS Card JSON 文件"""
    if not filepath.suffix == ".json":
        return None
    try:
        data = json.loads(filepath.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None

    if data.get("Name") not in {"Card", "CardCustom"}:
        return None

    gmnotes = load_gmnotes(data, filepath, root)
    arkhamdb_id = extract_arkhamdb_id(gmnotes)
    if not arkhamdb_id:
        return None

    card_id = data.get("CardID", 0)
    card_id_str = str(card_id)

    if len(card_id_str) <= 2:
        return None
    deck_key = card_id_str[:-2]
    grid_position = int(card_id_str[-2:])

    custom_deck = data.get("CustomDeck", {})
    sheet = custom_deck.get(deck_key, {})

    return ParsedTTSCard(
        arkhamdb_id=arkhamdb_id,
        source=source,
        relative_json_path=str(filepath.relative_to(root)),
        card_id=card_id,
        deck_key=deck_key,
        face_url=sheet.get("FaceURL", ""),
        back_url=sheet.get("BackURL", ""),
        grid_width=sheet.get("NumWidth", 10),
        grid_height=sheet.get("NumHeight", 1),
        grid_position=grid_position,
        unique_back=sheet.get("UniqueBack", False),
        nickname=data.get("Nickname", ""),
        guid=data.get("GUID", ""),
        sideways_card=data.get("SidewaysCard", False),
    )


def scan_tts_directory(root: Path, source: str) -> list[ParsedTTSCard]:
    """递归遍历 TTS 目录，解析所有 Card JSON"""
    cards: list[ParsedTTSCard] = []
    for json_file in sorted(root.rglob("*.json")):
        result = parse_tts_card_json(json_file, source, root)
        if result:
            cards.append(result)
    return cards


def find_shared_backs(cards: list[ParsedTTSCard], source: str) -> list[dict]:
    """提取共享卡背"""
    back_map: dict[str, dict] = {}
    for c in cards:
        if not c.unique_back and c.back_url:
            key = c.back_url
            if key not in back_map:
                back_map[key] = {
                    "back_url": c.back_url,
                    "source": source,
                    "deck_key": c.deck_key,
                }
    return list(back_map.values())
