"""
本地 .card 文件扫描器

遍历卡牌数据库目录，解析 .card JSON 文件，提取字段、计算哈希、
检测双面卡，并剥离 base64 图片数据以减少内存占用。
"""
import json
import hashlib
import os
from pathlib import Path
from dataclasses import dataclass


@dataclass
class ScannedCard:
    """单张扫描卡牌的元数据"""
    arkhamdb_id: str
    face: str
    relative_path: str
    category: str
    cycle: str
    name_zh: str
    card_type: str
    is_double_sided: bool
    content_hash: str
    last_modified: str
    content_json: dict


def scan_card_database(root: Path) -> list[ScannedCard]:
    """遍历卡牌数据库目录，返回所有 .card 文件的扫描结果"""
    cards: list[ScannedCard] = []
    for card_file in sorted(root.rglob("*.card")):
        # 跳过隐藏文件
        if card_file.name.startswith("."):
            continue
        relative = card_file.relative_to(root)
        parts = relative.parts

        # 目录结构必须至少是 category/cycle/filename.card
        if len(parts) < 3:
            continue

        category = parts[0]
        cycle = parts[1]
        filename = parts[2]

        # 文件名格式: arkhamdb_id_face.card
        stem = filename.replace(".card", "")
        if "_" not in stem:
            continue
        arkhamdb_id, face = stem.rsplit("_", 1)
        if face not in ("a", "b", "a-c"):
            continue

        content_bytes = card_file.read_bytes()
        content_hash = hashlib.sha256(content_bytes).hexdigest()
        last_modified = str(os.path.getmtime(str(card_file)))

        try:
            data = json.loads(content_bytes)
        except json.JSONDecodeError:
            continue

        # 剥离 base64 图片数据以减少内存占用
        clean_data = {k: v for k, v in data.items() if k != "picture_base64"}

        card = ScannedCard(
            arkhamdb_id=arkhamdb_id,
            face=face,
            relative_path=str(relative),
            category=category,
            cycle=cycle,
            name_zh=data.get("name", ""),
            card_type=data.get("type", ""),
            is_double_sided=data.get("double_sided", False) or "back" in data,
            content_hash=content_hash,
            last_modified=last_modified,
            content_json=clean_data,
        )
        cards.append(card)

    return cards


def detect_double_sided(cards: list[ScannedCard]) -> set[str]:
    """检测双面卡：找出同时存在 a 面和 b 面的 arkhamdb_id"""
    face_map: dict[str, set[str]] = {}
    for c in cards:
        face_map.setdefault(c.arkhamdb_id, set()).add(c.face)
    return {aid for aid, faces in face_map.items() if faces & {"a", "b"}}


def load_card_content(root: Path, relative_path: str) -> dict | None:
    """加载单张 .card 完整内容（不包含 picture_base64）"""
    filepath = root / relative_path
    if not filepath.exists():
        return None
    data = json.loads(filepath.read_bytes())
    return {k: v for k, v in data.items() if k != "picture_base64"}
