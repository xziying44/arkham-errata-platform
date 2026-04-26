"""从当前中文 TTS 数据初始化单面卡发布卡背索引。"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.database import async_session
from app.models.card import LocalCardFile, TTSCardImage
from app.services.mapping_index import BACK_PRESETS, load_mapping_index, save_mapping_index


def _now_tag() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _index_path() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "mapping_index.json"


def _preset_by_url() -> dict[str, dict[str, str]]:
    return {preset["back_url"]: preset for preset in BACK_PRESETS.values()}


def _face_for_single(local_faces: set[str]) -> str:
    return sorted(local_faces)[0]


def _build_override(preset: dict[str, str]) -> dict[str, str]:
    return {
        "preset_key": preset["key"],
        "label": preset["label"],
        "back_url": preset["back_url"],
        "source": "中文TTS现状导入",
        "reason": "从当前中文 TTS CustomDeck.BackURL 初始化单面卡卡背",
        "updated_by": "system",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


async def collect_changes(overwrite: bool) -> dict[str, Any]:
    async with async_session() as db:
        local_files = (await db.execute(select(LocalCardFile))).scalars().all()
        zh_items = (await db.execute(select(TTSCardImage).where(TTSCardImage.source == "中文"))).scalars().all()

    local_faces: dict[str, set[str]] = defaultdict(set)
    for item in local_files:
        local_faces[item.arkhamdb_id].add(item.face)

    single_faces = {arkhamdb_id: _face_for_single(faces) for arkhamdb_id, faces in local_faces.items() if len(faces) == 1}
    double_ids = {arkhamdb_id for arkhamdb_id, faces in local_faces.items() if len(faces) > 1}
    preset_by_url = _preset_by_url()
    zh_by_card: dict[str, list[TTSCardImage]] = defaultdict(list)
    for item in zh_items:
        zh_by_card[item.arkhamdb_id].append(item)

    index = load_mapping_index()
    cards = index.setdefault("cards", {})
    planned: list[dict[str, Any]] = []
    skipped_existing: list[str] = []
    skipped_missing_zh: list[str] = []
    skipped_unknown: list[dict[str, str]] = []
    conflicts: list[dict[str, Any]] = []

    for arkhamdb_id, face in sorted(single_faces.items()):
        zh_candidates = zh_by_card.get(arkhamdb_id, [])
        if not zh_candidates:
            skipped_missing_zh.append(arkhamdb_id)
            continue
        known = []
        unknown = []
        for zh in zh_candidates:
            preset = preset_by_url.get(zh.back_url)
            if preset:
                known.append((zh, preset))
            elif zh.back_url:
                unknown.append(zh.back_url)
        if not known:
            skipped_unknown.append({"arkhamdb_id": arkhamdb_id, "back_url": unknown[0] if unknown else ""})
            continue
        keys = {preset["key"] for _, preset in known}
        if len(keys) > 1:
            conflicts.append({"arkhamdb_id": arkhamdb_id, "preset_keys": sorted(keys)})
            continue
        zh, preset = known[0]
        record = cards.setdefault(arkhamdb_id, {"faces": {}, "confirmed": False})
        face_record = record.setdefault("faces", {}).setdefault(face, {})
        if face_record.get("back_override") and not overwrite:
            skipped_existing.append(arkhamdb_id)
            continue
        planned.append({
            "arkhamdb_id": arkhamdb_id,
            "face": face,
            "preset_key": preset["key"],
            "label": preset["label"],
            "back_url": preset["back_url"],
            "zh_tts_id": zh.id,
            "zh_path": zh.relative_json_path,
        })
        face_record["back_override"] = _build_override(preset)
        record["confirmed"] = False

    summary = {
        "total_local_single": len(single_faces),
        "total_local_double": len(double_ids),
        "planned_updates": len(planned),
        "skipped_existing": len(skipped_existing),
        "skipped_missing_chinese_tts": len(skipped_missing_zh),
        "skipped_unknown_back_url": len(skipped_unknown),
        "conflicts": len(conflicts),
        "by_preset": Counter(item["preset_key"] for item in planned),
        "planned_examples": planned[:10],
        "unknown_examples": skipped_unknown[:20],
        "conflict_examples": conflicts[:20],
        "index": index,
    }
    return summary


async def main() -> None:
    parser = argparse.ArgumentParser(description="从中文 TTS 初始化单面卡卡背索引")
    parser.add_argument("--apply", action="store_true", help="实际写入 data/mapping_index.json")
    parser.add_argument("--overwrite", action="store_true", help="覆盖已有 back_override")
    args = parser.parse_args()

    summary = await collect_changes(overwrite=args.overwrite)
    printable = {key: value for key, value in summary.items() if key != "index"}
    printable["by_preset"] = dict(printable["by_preset"])
    print(json.dumps(printable, ensure_ascii=False, indent=2))

    if not args.apply:
        print("DRY-RUN：未写入映射索引。")
        return

    index_path = _index_path()
    if index_path.exists():
        backup_path = index_path.with_suffix(f".backup-{_now_tag()}.json")
        shutil.copy2(index_path, backup_path)
        print(f"已备份：{backup_path}")
    save_mapping_index(summary["index"])
    print(f"已写入：{index_path}")


if __name__ == "__main__":
    asyncio.run(main())
