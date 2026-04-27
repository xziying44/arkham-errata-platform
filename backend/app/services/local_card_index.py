"""本地 .card 内容索引缓存，避免卡牌树每次请求反复读文件。"""

import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.scanner import load_card_content, scan_card_database


@dataclass(frozen=True)
class LocalCardFaceIndex:
    """单个本地 .card 文件的轻量索引。"""

    relative_path: str
    title: str
    subtitle: str
    search_text: str


_lock = threading.RLock()
_index_root: Path | None = None
_index_by_path: dict[str, LocalCardFaceIndex] = {}


def _normalize_root(root: Path) -> Path:
    return root.resolve()


def _build_search_text(content: dict[str, Any], relative_path: str) -> str:
    payload = {
        "relative_path": relative_path,
        "content": content,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True).lower()


def _clean_content(content: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in content.items() if key != "picture_base64"}


def _index_item_from_content(relative_path: str, content: dict[str, Any]) -> LocalCardFaceIndex:
    clean_content = _clean_content(content)
    return LocalCardFaceIndex(
        relative_path=relative_path,
        title=clean_content.get("name", "") if isinstance(clean_content.get("name"), str) else "",
        subtitle=clean_content.get("subtitle", "") if isinstance(clean_content.get("subtitle"), str) else "",
        search_text=_build_search_text(clean_content, relative_path),
    )


def build_local_card_index(root: Path) -> dict[str, LocalCardFaceIndex]:
    """扫描本地卡牌数据库并重建内存索引。"""
    normalized_root = _normalize_root(root)
    cards = scan_card_database(normalized_root)
    next_index = {
        card.relative_path: _index_item_from_content(card.relative_path, card.content_json)
        for card in cards
    }
    with _lock:
        global _index_root, _index_by_path
        _index_root = normalized_root
        _index_by_path = next_index
    return next_index


def ensure_local_card_index(root: Path) -> None:
    """确保索引已构建；根目录变化时自动重建。"""
    normalized_root = _normalize_root(root)
    with _lock:
        needs_build = _index_root != normalized_root or not _index_by_path
    if needs_build:
        build_local_card_index(normalized_root)


def get_local_card_face_index(root: Path, relative_path: str) -> LocalCardFaceIndex | None:
    """读取指定 .card 文件的索引项。"""
    ensure_local_card_index(root)
    with _lock:
        return _index_by_path.get(relative_path)


def search_local_card_index(root: Path, keyword: str) -> set[str]:
    """按预构建索引搜索本地 .card 内容，返回匹配的相对路径集合。"""
    normalized_keyword = keyword.strip().lower()
    if not normalized_keyword:
        return set()
    ensure_local_card_index(root)
    with _lock:
        return {
            relative_path
            for relative_path, item in _index_by_path.items()
            if normalized_keyword in item.search_text
        }


def update_local_card_index_faces(
    root: Path,
    face_paths: dict[str, str],
    modified_faces: dict[str, dict[str, Any]],
) -> None:
    """用勘误副本内容覆盖指定卡牌面的内存索引。"""
    ensure_local_card_index(root)
    updates: dict[str, LocalCardFaceIndex] = {}
    for face, relative_path in face_paths.items():
        content = modified_faces.get(face)
        if isinstance(content, dict):
            updates[relative_path] = _index_item_from_content(relative_path, content)
    if not updates:
        return
    with _lock:
        _index_by_path.update(updates)


def restore_local_card_index_paths(root: Path, relative_paths: list[str]) -> None:
    """从磁盘重新读取指定 .card 文件，恢复原始索引内容。"""
    ensure_local_card_index(root)
    normalized_root = _normalize_root(root)
    restored: dict[str, LocalCardFaceIndex] = {}
    missing_or_invalid: list[str] = []
    for relative_path in relative_paths:
        content = load_card_content(normalized_root, relative_path)
        if isinstance(content, dict):
            restored[relative_path] = _index_item_from_content(relative_path, content)
        else:
            missing_or_invalid.append(relative_path)
    with _lock:
        _index_by_path.update(restored)
        for relative_path in missing_or_invalid:
            _index_by_path.pop(relative_path, None)
