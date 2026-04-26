"""从历史重置目录和旧工具规则导入卡图映射索引。"""

from __future__ import annotations

import argparse
import json
import math
import shutil
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageStat
from sqlalchemy import select

from app.config import settings
from app.database import async_session
from app.models.card import LocalCardFile, TTSCardImage
from app.services.image_cache import download_and_cut_sheet
from app.services.mapping_index import get_mapping_index_path, load_mapping_index, save_mapping_index
from app.services.renderer import render_card_preview
from app.services.scanner import load_card_content

DEFAULT_RULE_ROOTS = [
    Path("/Volumes/RepoVault/诡镇简中包/分类合并包/重置剧本卡"),
    Path("/Volumes/RepoVault/诡镇简中包/分类合并包/重置玩家卡"),
    Path("/Volumes/RepoVault/诡镇简中包/重置剧本卡"),
    Path("/Volumes/RepoVault/诡镇简中包/重置玩家卡"),
]
SPECIAL_ID_REPLACEMENTS = {
    "10015b1": "10015-b1",
    "10015b2": "10015-b2",
}


@dataclass
class ProposedMapping:
    arkhamdb_id: str
    local_face: str
    tts_lookup_id: str
    tts_id: int | None
    tts_side: str
    source_reason: str
    current_tts_id: int | None
    current_tts_side: str | None
    action: str
    relative_path: str
    tts_path: str | None


def load_id_replacement_rules(roots: list[Path]) -> dict[str, str]:
    rules = dict(SPECIAL_ID_REPLACEMENTS)
    for root in roots:
        if not root.exists():
            continue
        for txt_path in sorted(root.rglob("注意.txt")):
            for raw_line in txt_path.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "-" not in line:
                    continue
                left, right = line.split("-", 1)
                left = left.strip()
                right = right.strip()
                if left and right:
                    rules[left] = right
    return rules


def side_from_location_type(content: dict[str, Any]) -> tuple[str, str] | None:
    if content.get("type") != "地点卡":
        return None
    location_type = str(content.get("location_type") or "").strip()
    if location_type == "未揭示":
        return "front", "location_type_unrevealed"
    if location_type == "已揭示":
        return "back", "location_type_revealed"
    return None


def side_from_notes(content: dict[str, Any]) -> tuple[str, str] | None:
    notes = str(content.get("Notes") or "").strip().lower()
    if notes in {"front", "back"}:
        return notes, "card_notes"
    return None


def side_from_card_content(content: dict[str, Any], local_face: str) -> tuple[str, str]:
    notes_side = side_from_notes(content)
    if notes_side:
        return notes_side
    location_side = side_from_location_type(content)
    if location_side:
        return location_side
    return ("back" if local_face == "b" else "front"), "face_suffix_default"


def resolve_location_pair_overrides(items: list[tuple[LocalCardFile, dict[str, Any]]]) -> dict[int, tuple[str, str]]:
    location_items = [(item, content) for item, content in items if content.get("type") == "地点卡"]
    if len(location_items) != 2:
        return {}

    notes_sides = [side_from_notes(content) for _, content in location_items]
    if not all(notes_sides):
        return {}
    if len({side for side, _ in notes_sides if side}) != 1:
        return {}

    overrides: dict[int, tuple[str, str]] = {}
    for item, content in location_items:
        location_side = side_from_location_type(content)
        if location_side:
            overrides[item.id] = location_side
    return overrides if len(overrides) == len(location_items) else {}


def card_lookup_id(arkhamdb_id: str, replacements: dict[str, str]) -> tuple[str, str]:
    if arkhamdb_id in replacements:
        return replacements[arkhamdb_id], "notice_txt"
    base_id = arkhamdb_id[:-1] if arkhamdb_id[-1:].isalpha() else arkhamdb_id
    if base_id in replacements:
        return replacements[base_id], "notice_txt_base"
    return base_id, "same_or_base_id"




def tts_candidate_priority(tts: TTSCardImage) -> tuple[int, int, int, str]:
    """同一 arkhamdb_id 存在多个 TTS 对象时的默认候选优先级。"""
    path = tts.relative_json_path or ""
    is_nested_state = "/" in path
    is_promo = "promo" in path.lower() or "parallel" in path.lower()
    return (1 if is_nested_state else 0, 1 if is_promo else 0, tts.id or 0, path)

def read_current_mapping(index: dict[str, Any], arkhamdb_id: str, face: str) -> tuple[int | None, str | None]:
    record = index.get("cards", {}).get(arkhamdb_id, {})
    mapping = record.get("faces", {}).get(face, {}).get("英文", {}) if isinstance(record, dict) else {}
    return mapping.get("tts_id"), mapping.get("tts_side")


def merge_mapping(index: dict[str, Any], item: ProposedMapping) -> None:
    cards = index.setdefault("cards", {})
    card = cards.setdefault(item.arkhamdb_id, {"faces": {}, "confirmed": False})
    faces = card.setdefault("faces", {})
    face = faces.setdefault(item.local_face, {})
    face["英文"] = {
        "tts_id": item.tts_id,
        "tts_side": item.tts_side,
        "updated_by": "import_mapping_index",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source_reason": item.source_reason,
        "tts_lookup_id": item.tts_lookup_id,
    }
    card["confirmed"] = False
    card.pop("confirmed_by", None)
    card.pop("confirmed_at", None)


async def build_proposals(roots: list[Path]) -> tuple[list[ProposedMapping], dict[str, int], dict[str, TTSCardImage]]:
    replacements = load_id_replacement_rules(roots)
    index = load_mapping_index()
    local_root = settings.project_root / settings.local_card_db
    proposals: list[ProposedMapping] = []
    stats = {"local_files": 0, "with_tts": 0, "missing_tts": 0, "same": 0, "update": 0, "new": 0}

    zh_tts_by_id: dict[str, TTSCardImage] = {}
    async with async_session() as db:
        local_files = list((await db.execute(select(LocalCardFile).order_by(LocalCardFile.arkhamdb_id, LocalCardFile.face))).scalars().all())
        content_by_file: dict[int, dict[str, Any]] = {}
        files_by_card: dict[str, list[LocalCardFile]] = {}
        for local_file in local_files:
            files_by_card.setdefault(local_file.arkhamdb_id, []).append(local_file)
            content = load_card_content(local_root, local_file.relative_path, include_picture=False)
            if content:
                content_by_file[local_file.id] = content

        side_override_by_file: dict[int, tuple[str, str]] = {}
        for card_files in files_by_card.values():
            items_with_content = [(item, content_by_file.get(item.id, {})) for item in card_files]
            location_overrides = resolve_location_pair_overrides(items_with_content)
            if location_overrides:
                side_override_by_file.update(location_overrides)
                continue

            explicit = []
            for item, content in items_with_content:
                note_side = side_from_notes(content)
                if note_side:
                    explicit.append((item, note_side[0]))
            if len(card_files) == 2 and len(explicit) == 1:
                known_file, known_side = explicit[0]
                opposite_side = "front" if known_side == "back" else "back"
                side_override_by_file[known_file.id] = (known_side, "card_notes")
                for item in card_files:
                    if item.id != known_file.id:
                        side_override_by_file[item.id] = (opposite_side, "card_notes_complement")
            else:
                for item, note in explicit:
                    side_override_by_file[item.id] = (note, "card_notes")

        tts_items = list((await db.execute(select(TTSCardImage))).scalars().all())
        first_tts_by_id: dict[str, TTSCardImage] = {}
        for tts in sorted(tts_items, key=tts_candidate_priority):
            if tts.source == "英文":
                first_tts_by_id.setdefault(tts.arkhamdb_id, tts)
            elif tts.source == "中文":
                zh_tts_by_id.setdefault(tts.arkhamdb_id, tts)

        for local_file in local_files:
            stats["local_files"] += 1
            content = content_by_file.get(local_file.id)
            if not content:
                continue
            side, side_reason = side_override_by_file.get(local_file.id) or side_from_card_content(content, local_file.face)
            lookup_id, id_reason = card_lookup_id(local_file.arkhamdb_id, replacements)
            tts = first_tts_by_id.get(lookup_id)
            if not tts:
                stats["missing_tts"] += 1
            else:
                stats["with_tts"] += 1
            current_tts_id, current_tts_side = read_current_mapping(index, local_file.arkhamdb_id, local_file.face)
            if current_tts_id == (tts.id if tts else None) and current_tts_side == side:
                action = "same"
                stats["same"] += 1
            elif current_tts_id or current_tts_side:
                action = "update"
                stats["update"] += 1
            else:
                action = "new"
                stats["new"] += 1
            proposals.append(ProposedMapping(
                arkhamdb_id=local_file.arkhamdb_id,
                local_face=local_file.face,
                tts_lookup_id=lookup_id,
                tts_id=tts.id if tts else None,
                tts_side=side,
                source_reason=f"{id_reason}+{side_reason}",
                current_tts_id=current_tts_id,
                current_tts_side=current_tts_side,
                action=action,
                relative_path=local_file.relative_path,
                tts_path=tts.relative_json_path if tts else None,
            ))
    return proposals, stats, zh_tts_by_id


def write_report(report_path: Path, proposals: list[ProposedMapping], stats: dict[str, int]) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stats": stats,
        "actions": {name: sum(1 for item in proposals if item.action == name) for name in ["new", "update", "same"]},
        "missing_tts_examples": [asdict(item) for item in proposals if item.tts_id is None][:200],
        "update_examples": [asdict(item) for item in proposals if item.action == "update"][:200],
        "proposals": [asdict(item) for item in proposals],
    }
    report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")



def validate_image_diffs(proposals: list[ProposedMapping], zh_tts_by_id: dict[str, TTSCardImage], limit: int) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    local_root = settings.project_root / settings.local_card_db
    preview_dir = settings.project_root / settings.cache_dir / "mapping-diff" / "local"
    zh_cache_dir = settings.project_root / settings.cache_dir / "mapping-diff" / "zh"
    for proposal in proposals:
        if len(results) >= limit:
            break
        if proposal.tts_id is None:
            continue
        zh_tts = zh_tts_by_id.get(proposal.tts_lookup_id)
        if not zh_tts:
            continue
        if proposal.tts_side == "back" and not zh_tts.unique_back:
            results.append({**asdict(proposal), "diff_status": "skipped_shared_back"})
            continue
        content = load_card_content(local_root, proposal.relative_path, include_picture=True)
        if not content:
            results.append({**asdict(proposal), "diff_status": "local_read_failed"})
            continue
        local_path = render_card_preview(content, preview_dir, f"{proposal.arkhamdb_id}_{proposal.local_face}")
        sheet_url = zh_tts.back_url if proposal.tts_side == "back" else zh_tts.face_url
        zh_path = download_and_cut_sheet(
            sheet_url=sheet_url,
            grid_position=zh_tts.grid_position,
            grid_width=zh_tts.grid_width,
            grid_height=zh_tts.grid_height,
            cache_dir=zh_cache_dir,
            cache_key=f"zh_{zh_tts.id}_{proposal.tts_side}",
        )
        if not local_path or not zh_path:
            results.append({**asdict(proposal), "diff_status": "image_generate_failed"})
            continue
        score, orientation = best_orientation_rmse(Path(local_path), Path(zh_path))
        results.append({
            **asdict(proposal),
            "diff_status": "ok",
            "rmse": score,
            "orientation_used": orientation,
            "is_suspicious": score > 65,
            "local_image": str(local_path),
            "zh_image": str(zh_path),
            "zh_tts_id": zh_tts.id,
            "zh_tts_path": zh_tts.relative_json_path,
        })
    return results


def image_rmse(path_a: Path, path_b: Path) -> float:
    with Image.open(path_a) as image_a, Image.open(path_b) as image_b:
        return image_rmse_from_images(image_a, image_b)


def image_rmse_from_images(image_a: Image.Image, image_b: Image.Image) -> float:
    a = image_a.convert("RGB").resize((240, 336))
    b = image_b.convert("RGB").resize((240, 336))
    diff = ImageChops.difference(a, b)
    stat = ImageStat.Stat(diff)
    return math.sqrt(sum(value ** 2 for value in stat.rms) / len(stat.rms))


def best_orientation_rmse(path_a: Path, path_b: Path) -> tuple[float, str]:
    with Image.open(path_a) as image_a, Image.open(path_b) as image_b:
        original = image_rmse_from_images(image_a, image_b)
        rotated_ccw = image_rmse_from_images(image_a, image_b.rotate(90, expand=True))
        if rotated_ccw < original:
            return rotated_ccw, "tts_rotated_ccw_90"
        return original, "original"


async def main() -> None:
    parser = argparse.ArgumentParser(description="导入历史映射规则到 卡牌数据库/mapping_index.json")
    parser.add_argument("--apply", action="store_true", help="实际写入卡牌数据库/mapping_index.json；未指定时只生成预览报告")
    parser.add_argument("--report", default="data/mapping_import_preview.json", help="预览报告输出路径")
    parser.add_argument("--validate-images", type=int, default=0, help="抽样校验本地渲染图与中文 TTS 图的数量")
    parser.add_argument("--validate-offset", type=int, default=0, help="图片校验候选起始偏移")
    parser.add_argument("--diff-report", default="data/mapping_image_diff_preview.json", help="图片差异报告输出路径")
    args = parser.parse_args()

    proposals, stats, zh_tts_by_id = await build_proposals(DEFAULT_RULE_ROOTS)
    report_path = settings.project_root / args.report
    write_report(report_path, proposals, stats)
    diff_report_path = None
    if args.validate_images > 0:
        eligible = [item for item in proposals if item.tts_id is not None and item.tts_lookup_id in zh_tts_by_id]
        selected = eligible[args.validate_offset:args.validate_offset + args.validate_images]
        diff_results = validate_image_diffs(selected, zh_tts_by_id, args.validate_images)
        diff_report_path = settings.project_root / args.diff_report
        diff_report_path.parent.mkdir(parents=True, exist_ok=True)
        diff_report_path.write_text(json.dumps(diff_results, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({"stats": stats, "report": str(report_path), "diff_report": str(diff_report_path) if diff_report_path else None}, ensure_ascii=False, indent=2))

    if not args.apply:
        print("未指定 --apply，只生成预览报告，未写入卡牌数据库/mapping_index.json")
        return

    index_path = get_mapping_index_path()
    if index_path.exists():
        backup_path = index_path.with_name(f"mapping_index.backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json")
        shutil.copy2(index_path, backup_path)
        print(f"已备份旧索引: {backup_path}")

    index = load_mapping_index()
    for proposal in proposals:
        if proposal.tts_id is None:
            continue
        merge_mapping(index, proposal)
    save_mapping_index(index)
    print(f"已写入索引: {index_path}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
