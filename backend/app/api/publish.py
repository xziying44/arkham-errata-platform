"""发布 API - 审核通过后的发布管线（生成精灵图 → 上传 → 导出 → URL 替换）"""

import hashlib
import json
import shutil
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.card import CardIndex, LocalCardFile, TTSCardImage
from app.models.errata_draft import ErrataDraft, ErrataPackage, ErrataPackageStatus, PublishArtifact, PublishArtifactKind, PublishArtifactStatus, PublishDirectoryPreset, PublishDirectoryTargetArea, PublishSession, PublishSessionStatus
from app.models.user import User
from app.api.auth import require_admin
from app.services.sheet_generator import create_decksheet, group_cards_by_sheet
from app.services.uploader import create_uploader
from app.services.url_replacer import (
    generate_tts_bag_json,
    export_chinese_card_url_replacements,
    extract_steam_urls_from_json,
)
from app.services.errata_drafts import merge_original_picture_for_face
from app.services.renderer import render_card_preview
from app.config import settings
from app.schemas.publish import PublishDirectoryPresetCreateRequest, PublishDirectoryPresetUpdateRequest, PublishRollbackRequest, PublishSessionCreateRequest, PublishUrlImportRequest
from app.services.publish_package_builder import build_replacement_plan
from app.services.publish_sessions import add_artifact, create_publish_session, import_url_mapping, list_session_artifacts, load_publish_session, rollback_session_to_step, supersede_artifacts_after_step

router = APIRouter(prefix="/api/admin/publish", tags=["发布"])


def serialize_directory_preset(preset: PublishDirectoryPreset) -> dict:
    return {
        "id": preset.id,
        "local_dir_prefix": preset.local_dir_prefix,
        "target_area": preset.target_area.value,
        "target_bag_path": preset.target_bag_path,
        "target_bag_guid": preset.target_bag_guid,
        "target_object_dir": preset.target_object_dir,
        "label": preset.label,
        "is_active": preset.is_active,
        "created_at": preset.created_at,
        "updated_at": preset.updated_at,
    }


def _preset_target_from_tts_path(relative_json_path: str) -> tuple[str, str, str] | None:
    path = Path(relative_json_path)
    parts = path.parts
    if len(parts) < 2:
        return None
    object_dir = parts[-2]
    bag_path = "/".join([*parts[:-1], f"{object_dir}.json"])
    guid = object_dir.rsplit(".", 1)[-1] if "." in object_dir else object_dir
    return bag_path, guid, object_dir


def _preset_area_from_path(relative_json_path: str) -> PublishDirectoryTargetArea:
    if "Simplified Chinese - Player Cards" in relative_json_path:
        return PublishDirectoryTargetArea.PLAYER_CARDS
    return PublishDirectoryTargetArea.CAMPAIGNS


@router.post("/directory-presets/initialize-from-existing")
async def initialize_directory_presets_from_existing(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    result = await db.execute(
        select(LocalCardFile, TTSCardImage)
        .join(TTSCardImage, TTSCardImage.arkhamdb_id == LocalCardFile.arkhamdb_id)
        .where(LocalCardFile.face == "a")
        .where(TTSCardImage.source == "中文")
    )
    candidates: dict[str, tuple[LocalCardFile, TTSCardImage]] = {}
    for local_file, tts_image in result.all():
        local_prefix = str(Path(local_file.relative_path).parent)
        target = _preset_target_from_tts_path(tts_image.relative_json_path)
        if not target:
            continue
        candidates.setdefault(local_prefix, (local_file, tts_image))

    created = 0
    updated = 0
    for local_prefix, (_local_file, tts_image) in sorted(candidates.items()):
        target = _preset_target_from_tts_path(tts_image.relative_json_path)
        if target is None:
            continue
        target_bag_path, target_bag_guid, target_object_dir = target
        existing = (await db.execute(select(PublishDirectoryPreset).where(PublishDirectoryPreset.local_dir_prefix == local_prefix))).scalar_one_or_none()
        if existing is None:
            db.add(PublishDirectoryPreset(
                local_dir_prefix=local_prefix,
                target_area=_preset_area_from_path(tts_image.relative_json_path),
                target_bag_path=target_bag_path,
                target_bag_guid=target_bag_guid,
                target_object_dir=target_object_dir,
                label=f"{local_prefix} -> {target_object_dir}",
                is_active=True,
            ))
            created += 1
        else:
            existing.target_area = _preset_area_from_path(tts_image.relative_json_path)
            existing.target_bag_path = target_bag_path
            existing.target_bag_guid = target_bag_guid
            existing.target_object_dir = target_object_dir
            existing.label = f"{local_prefix} -> {target_object_dir}"
            existing.is_active = True
            updated += 1
    await db.commit()
    return {"created": created, "updated": updated}


@router.get("/directory-presets")
async def list_directory_presets(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    result = await db.execute(select(PublishDirectoryPreset).order_by(PublishDirectoryPreset.local_dir_prefix))
    return {"items": [serialize_directory_preset(preset) for preset in result.scalars().all()]}


@router.post("/directory-presets")
async def create_directory_preset(
    body: PublishDirectoryPresetCreateRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    local_dir_prefix = body.local_dir_prefix.strip().strip("/")
    target_bag_path = body.target_bag_path.strip().strip("/")
    target_bag_guid = body.target_bag_guid.strip()
    target_object_dir = body.target_object_dir.strip().strip("/")
    if not local_dir_prefix:
        raise HTTPException(status_code=400, detail="本地目录不能为空")
    if not target_bag_path or not target_bag_guid or not target_object_dir:
        raise HTTPException(status_code=400, detail="目标 Bag 路径、GUID 和对象目录不能为空")
    try:
        target_area = PublishDirectoryTargetArea(body.target_area)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="目标区域无效") from exc

    existing = (await db.execute(select(PublishDirectoryPreset).where(PublishDirectoryPreset.local_dir_prefix == local_dir_prefix))).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="本地目录已存在发布预设")

    preset = PublishDirectoryPreset(
        local_dir_prefix=local_dir_prefix,
        target_area=target_area,
        target_bag_path=target_bag_path,
        target_bag_guid=target_bag_guid,
        target_object_dir=target_object_dir,
        label=(body.label or f"{local_dir_prefix} -> {target_object_dir}").strip(),
        is_active=body.is_active,
    )
    db.add(preset)
    await db.commit()
    await db.refresh(preset)
    return serialize_directory_preset(preset)


@router.patch("/directory-presets/{preset_id}")
async def update_directory_preset(
    preset_id: int,
    body: PublishDirectoryPresetUpdateRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    preset = await db.get(PublishDirectoryPreset, preset_id)
    if preset is None:
        raise HTTPException(status_code=404, detail="发布目录预设不存在")
    for field in ["target_bag_path", "target_bag_guid", "target_object_dir", "label", "is_active"]:
        value = getattr(body, field)
        if value is not None:
            setattr(preset, field, value)
    await db.commit()
    await db.refresh(preset)
    return serialize_directory_preset(preset)


def serialize_publish_artifact(artifact: PublishArtifact) -> dict:
    return {
        "id": artifact.id,
        "session_id": artifact.session_id,
        "kind": artifact.kind.value,
        "status": artifact.status.value,
        "path": artifact.path,
        "public_url": artifact.public_url,
        "checksum": artifact.checksum,
        "metadata": artifact.artifact_metadata,
        "created_at": artifact.created_at,
        "updated_at": artifact.updated_at,
    }


def _active_publish_artifacts(artifacts: list[PublishArtifact]) -> list[PublishArtifact]:
    return [
        artifact
        for artifact in artifacts
        if artifact.status in {PublishArtifactStatus.ACTIVE, PublishArtifactStatus.CONFIRMED}
    ]


def _absolute_artifact_url(request: Request, artifact: PublishArtifact) -> str:
    if artifact.public_url is None:
        return ""
    base_url = str(request.base_url).rstrip("/")
    return f"{base_url}{artifact.public_url}"


def _sheet_export_payload(request: Request, artifacts: list[PublishArtifact]) -> tuple[dict[str, str], dict[str, dict]]:
    sheet_urls: dict[str, str] = {}
    sheet_grids: dict[str, dict] = {}
    active_artifacts = _active_publish_artifacts(artifacts)
    for artifact in active_artifacts:
        if artifact.kind not in {PublishArtifactKind.SHEET_FRONT, PublishArtifactKind.SHEET_BACK}:
            continue
        metadata = artifact.artifact_metadata or {}
        sheet_name = str(metadata.get("sheet_name") or "")
        if not sheet_name:
            continue
        sheet_urls[sheet_name] = _absolute_artifact_url(request, artifact)
        sheet_grids[sheet_name] = {
            "deck_key": str(int(hashlib.sha1(f"{artifact.session_id}:{sheet_name}".encode("utf-8")).hexdigest()[:8], 16) % 90000 + 10000),
            "width": int(metadata.get("grid_width") or 10),
            "height": int(metadata.get("grid_height") or 1),
        }
    return sheet_urls, sheet_grids


async def serialize_publish_session(db: AsyncSession, session: PublishSession) -> dict:
    artifacts = await list_session_artifacts(db, session.id)
    return {
        "id": session.id,
        "package_id": session.package_id,
        "status": session.status.value,
        "current_step": session.current_step,
        "artifact_root": session.artifact_root,
        "error_message": session.error_message,
        "cleanup_at": session.cleanup_at,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
        "artifacts": [serialize_publish_artifact(artifact) for artifact in artifacts],
    }


@router.post("/sessions")
async def create_session(
    body: PublishSessionCreateRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    session = await create_publish_session(db, body.package_id, admin)
    return await serialize_publish_session(db, session)


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    session = await load_publish_session(db, session_id)
    return await serialize_publish_session(db, session)


@router.post("/sessions/{session_id}/generate-sheets")
async def generate_session_sheets(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    session = await load_publish_session(db, session_id)
    _package, drafts = await load_publish_package(db, session.package_id)
    await supersede_artifacts_after_step(
        db,
        session.id,
        {
            PublishArtifactKind.CARD_IMAGE,
            PublishArtifactKind.SHEET_FRONT,
            PublishArtifactKind.SHEET_BACK,
            PublishArtifactKind.MANIFEST,
            PublishArtifactKind.URL_MAPPING,
            PublishArtifactKind.PATCH_ZIP,
            PublishArtifactKind.REPORT,
        },
    )

    root = settings.project_root / session.artifact_root
    cards_dir = root / "cards"
    sheets_dir = root / "sheets"
    cards_dir.mkdir(parents=True, exist_ok=True)
    sheets_dir.mkdir(parents=True, exist_ok=True)

    card_images = []
    for draft in drafts:
        faces = draft.modified_faces or {}
        front = faces.get("a") or next(iter(faces.values()), {})
        if not isinstance(front, dict):
            front = {}
        front = merge_original_picture_for_face(draft.original_faces or {}, "a", front)
        back = faces.get("b")
        front_path = render_card_preview(front, cards_dir, f"{draft.arkhamdb_id}_a", dpi=300, quality=85)
        await add_artifact(db, session, PublishArtifactKind.CARD_IMAGE, Path(front_path), {"arkhamdb_id": draft.arkhamdb_id, "face": "a"})
        back_path = None
        if isinstance(back, dict):
            back = merge_original_picture_for_face(draft.original_faces or {}, "b", back)
            back_path = render_card_preview(back, cards_dir, f"{draft.arkhamdb_id}_b", dpi=300, quality=85)
            await add_artifact(db, session, PublishArtifactKind.CARD_IMAGE, Path(back_path), {"arkhamdb_id": draft.arkhamdb_id, "face": "b"})
        card_images.append({
            "arkhamdb_id": draft.arkhamdb_id,
            "front_path": front_path,
            "back_path": back_path,
            "name_zh": front.get("name", ""),
            "unique_back": isinstance(back, dict),
        })

    sheets = _split_cards_by_back_type(card_images)
    for sheet in sheets:
        card_count = len(sheet["arkhamdb_ids"])
        grid_width = min(card_count, 10)
        grid_height = max(1, (card_count + 9) // 10)
        grid_size = (grid_height, grid_width)
        front_sheet_path = sheets_dir / f"{sheet['sheet_name']}.jpg"
        create_decksheet(sheet["front_images"], grid_size=grid_size, output_path=str(front_sheet_path))
        await add_artifact(
            db,
            session,
            PublishArtifactKind.SHEET_FRONT,
            front_sheet_path,
            {"sheet_name": sheet["sheet_name"], "card_ids": sheet["arkhamdb_ids"], "grid_width": grid_width, "grid_height": grid_height},
        )
        if any(sheet["back_images"]):
            back_sheet_path = sheets_dir / f"{sheet['sheet_name']}-back.jpg"
            create_decksheet(sheet["back_images"], grid_size=grid_size, output_path=str(back_sheet_path))
            await add_artifact(
                db,
                session,
                PublishArtifactKind.SHEET_BACK,
                back_sheet_path,
                {"sheet_name": f"{sheet['sheet_name']}-back", "front_sheet_name": sheet["sheet_name"], "card_ids": sheet["arkhamdb_ids"], "grid_width": grid_width, "grid_height": grid_height},
            )

    session.status = PublishSessionStatus.SHEETS_READY
    session.current_step = "confirm_sheets"
    session.updated_by = admin.id
    await db.commit()
    await db.refresh(session)
    return await serialize_publish_session(db, session)


@router.post("/sessions/{session_id}/confirm-sheets")
async def confirm_session_sheets(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    session = await load_publish_session(db, session_id)
    artifacts = await list_session_artifacts(db, session.id)
    sheet_artifacts = [
        artifact
        for artifact in artifacts
        if artifact.kind in {PublishArtifactKind.SHEET_FRONT, PublishArtifactKind.SHEET_BACK}
        and artifact.status == PublishArtifactStatus.ACTIVE
    ]
    if not sheet_artifacts:
        raise HTTPException(status_code=409, detail="请先生成精灵图")
    for artifact in artifacts:
        if artifact.kind in {PublishArtifactKind.CARD_IMAGE, PublishArtifactKind.SHEET_FRONT, PublishArtifactKind.SHEET_BACK} and artifact.status == PublishArtifactStatus.ACTIVE:
            artifact.status = PublishArtifactStatus.CONFIRMED
    session.status = PublishSessionStatus.URLS_READY
    session.current_step = "prepare_urls"
    session.updated_by = admin.id
    await db.commit()
    await db.refresh(session)
    return await serialize_publish_session(db, session)


@router.get("/sessions/{session_id}/sheet-urls")
async def get_session_sheet_urls(
    session_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    session = await load_publish_session(db, session_id)
    artifacts = await list_session_artifacts(db, session.id)
    sheet_urls, sheet_grids = _sheet_export_payload(request, artifacts)
    items = [
        {
            "sheet_name": sheet_name,
            "url": sheet_urls[sheet_name],
            "grid": sheet_grids.get(sheet_name, {}),
        }
        for sheet_name in sorted(sheet_urls)
    ]
    return {"items": items, "sheet_urls": sheet_urls, "sheet_grids": sheet_grids}


@router.get("/sessions/{session_id}/tts-bag")
async def export_session_tts_bag(
    session_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    session = await load_publish_session(db, session_id)
    package, drafts = await load_publish_package(
        db,
        session.package_id,
        {ErrataPackageStatus.WAITING_PUBLISH, ErrataPackageStatus.PUBLISHING},
    )
    artifacts = await list_session_artifacts(db, session.id)
    sheet_urls, sheet_grids = _sheet_export_payload(request, artifacts)
    if not sheet_urls:
        raise HTTPException(status_code=409, detail="请先生成并确认精灵图")

    await supersede_artifacts_after_step(db, session.id, {PublishArtifactKind.TTS_BAG, PublishArtifactKind.URL_MAPPING, PublishArtifactKind.PATCH_ZIP, PublishArtifactKind.MANIFEST, PublishArtifactKind.REPORT})
    bag_json = generate_tts_bag_json(build_approved_cards_from_package(drafts), sheet_urls, sheet_grids)
    export_dir = settings.project_root / session.artifact_root / "tts"
    export_dir.mkdir(parents=True, exist_ok=True)
    export_path = export_dir / f"tts_bag_{package.package_no}.json"
    export_path.write_text(json.dumps(bag_json, ensure_ascii=False, indent=2), encoding="utf-8")
    await add_artifact(
        db,
        session,
        PublishArtifactKind.TTS_BAG,
        export_path,
        {"package_no": package.package_no, "sheet_urls": sheet_urls, "sheet_grids": sheet_grids},
        PublishArtifactStatus.CONFIRMED,
    )
    session.status = PublishSessionStatus.URLS_READY
    session.current_step = "prepare_urls"
    session.updated_by = admin.id
    await db.commit()
    return FileResponse(export_path, media_type="application/json", filename=f"{package.package_no}-TTS存档.json")


@router.post("/sessions/{session_id}/upload-tts-json")
async def upload_session_tts_json(
    session_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    session = await load_publish_session(db, session_id)
    content = await file.read()
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="上传的 TTS JSON 无法解析") from exc
    url_mapping = extract_steam_urls_from_json(data)
    if not url_mapping:
        raise HTTPException(status_code=400, detail="未从 TTS JSON 中识别到卡牌 URL")
    await import_url_mapping(db, session, f"tts-json:{file.filename or 'uploaded'}", url_mapping)
    session.updated_by = admin.id
    await db.commit()
    await db.refresh(session)
    return await serialize_publish_session(db, session)


@router.get("/sessions/{session_id}/replacement-preview")
async def get_replacement_preview(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    session = await load_publish_session(db, session_id)
    _package, drafts = await load_publish_package(
        db, session.package_id, {ErrataPackageStatus.WAITING_PUBLISH, ErrataPackageStatus.PUBLISHING}
    )
    artifacts = await list_session_artifacts(db, session.id)
    url_artifact = next(
        (
            artifact
            for artifact in artifacts
            if artifact.kind == PublishArtifactKind.URL_MAPPING
            and artifact.status in {PublishArtifactStatus.ACTIVE, PublishArtifactStatus.CONFIRMED}
        ),
        None,
    )
    url_mapping = url_artifact.artifact_metadata.get("url_mapping", {}) if url_artifact else {}
    roots = [
        (
            "decomposed/language-pack/Simplified Chinese - Campaigns",
            settings.project_root
            / settings.sced_downloads
            / "decomposed"
            / "language-pack"
            / "Simplified Chinese - Campaigns",
        ),
        (
            "decomposed/language-pack/Simplified Chinese - Player Cards",
            settings.project_root
            / settings.sced_downloads
            / "decomposed"
            / "language-pack"
            / "Simplified Chinese - Player Cards",
        ),
    ]
    local_paths = await _local_card_paths_for_package(db, drafts)
    directory_presets = await _directory_presets_for_plan(db)
    return {"items": build_replacement_plan(roots, build_approved_cards_from_package(drafts, local_paths), url_mapping, directory_presets)}


@router.post("/sessions/{session_id}/import-urls")
async def import_session_urls(
    session_id: int,
    body: PublishUrlImportRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    session = await load_publish_session(db, session_id)
    await import_url_mapping(db, session, body.source, body.url_mapping)
    session.updated_by = admin.id
    await db.commit()
    await db.refresh(session)
    return await serialize_publish_session(db, session)


@router.post("/sessions/{session_id}/rollback-step")
async def rollback_session_step(
    session_id: int,
    body: PublishRollbackRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    session = await load_publish_session(db, session_id)
    await rollback_session_to_step(db, session, body.target_step)
    session.updated_by = admin.id
    await db.commit()
    await db.refresh(session)
    return await serialize_publish_session(db, session)


@router.post("/sessions/{session_id}/export-patch")
async def export_session_patch(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    session = await load_publish_session(db, session_id)
    package, drafts = await load_publish_package(
        db, session.package_id, {ErrataPackageStatus.WAITING_PUBLISH, ErrataPackageStatus.PUBLISHING}
    )
    artifacts = await list_session_artifacts(db, session.id)
    url_artifact = next(
        (
            artifact
            for artifact in artifacts
            if artifact.kind == PublishArtifactKind.URL_MAPPING
            and artifact.status in {PublishArtifactStatus.ACTIVE, PublishArtifactStatus.CONFIRMED}
        ),
        None,
    )
    if url_artifact is None:
        raise HTTPException(status_code=409, detail="缺少 URL 映射，不能导出补丁包")
    url_mapping = url_artifact.artifact_metadata.get("url_mapping", {})
    roots = [
        (
            "decomposed/language-pack/Simplified Chinese - Campaigns",
            settings.project_root / settings.sced_downloads / "decomposed" / "language-pack" / "Simplified Chinese - Campaigns",
        ),
        (
            "decomposed/language-pack/Simplified Chinese - Player Cards",
            settings.project_root / settings.sced_downloads / "decomposed" / "language-pack" / "Simplified Chinese - Player Cards",
        ),
    ]
    local_paths = await _local_card_paths_for_package(db, drafts)
    directory_presets = await _directory_presets_for_plan(db)
    plan = build_replacement_plan(roots, build_approved_cards_from_package(drafts, local_paths), url_mapping, directory_presets)
    blocking = [item for item in plan if item["blocking_errors"]]
    if blocking:
        raise HTTPException(status_code=409, detail={"message": "替换计划存在阻断问题", "items": blocking})
    await supersede_artifacts_after_step(db, session.id, {PublishArtifactKind.PATCH_ZIP, PublishArtifactKind.REPORT, PublishArtifactKind.MANIFEST})

    patch_root = settings.project_root / session.artifact_root / "patch"
    if patch_root.exists():
        shutil.rmtree(patch_root)
    patch_root.mkdir(parents=True, exist_ok=True)

    all_modified: list[str] = []
    for relative_root, source_root in roots:
        if not source_root.exists():
            continue
        output_root = patch_root / relative_root
        modified = export_chinese_card_url_replacements(source_root, output_root, url_mapping)
        all_modified.extend([f"{relative_root}/{item}" for item in modified])
    all_modified.extend(_write_new_tts_objects_to_patch(patch_root, plan, url_mapping))
    all_modified = sorted(set(all_modified))

    manifest = {
        "说明": "请将本压缩包内容复制到你的 SCED-downloads fork 仓库根目录，检查后提交 PR。官方仓库未被本系统直接修改。",
        "package_no": package.package_no,
        "modified_files": all_modified,
        "total_modified": len(all_modified),
    }
    manifest_path = patch_root / "MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    report_path = patch_root / "validation_report.json"
    report_path.write_text(json.dumps({"package_no": package.package_no, "items": plan}, ensure_ascii=False, indent=2), encoding="utf-8")

    archive_base = settings.project_root / session.artifact_root / f"SCED-downloads-{package.package_no}-PR补丁包"
    archive_path = Path(shutil.make_archive(str(archive_base), "zip", patch_root))

    await add_artifact(db, session, PublishArtifactKind.MANIFEST, manifest_path, manifest, PublishArtifactStatus.CONFIRMED)
    await add_artifact(db, session, PublishArtifactKind.REPORT, report_path, {"items": plan}, PublishArtifactStatus.CONFIRMED)
    await add_artifact(
        db,
        session,
        PublishArtifactKind.PATCH_ZIP,
        archive_path,
        {"package_no": package.package_no, "modified_files": all_modified, "total_modified": len(all_modified)},
        PublishArtifactStatus.CONFIRMED,
    )
    session.status = PublishSessionStatus.PATCH_READY
    session.current_step = "complete"
    session.updated_by = admin.id
    await db.commit()
    await db.refresh(session)
    return await serialize_publish_session(db, session)


def _new_card_tts_object(item: dict, mapping: dict) -> dict:
    target_key = item.get("target_object_key") or f"{item['name_zh']}.{item['arkhamdb_id']}"
    guid = str(target_key).rsplit(".", 1)[-1]
    deck_key = str(mapping.get("deck_key") or "10000")
    return {
        "Name": "Card",
        "GUID": guid,
        "Nickname": item.get("name_zh") or item["arkhamdb_id"],
        "CardID": mapping.get("card_id", 0),
        "GMNotes": json.dumps({"id": item["arkhamdb_id"]}, ensure_ascii=False, indent=2),
        "Transform": {"scaleX": 1, "scaleY": 1, "scaleZ": 1},
        "CustomDeck": {
            deck_key: {
                "FaceURL": mapping.get("face_url", ""),
                "BackURL": mapping.get("back_url", ""),
                "NumWidth": mapping.get("grid_w", 10),
                "NumHeight": mapping.get("grid_h", 1),
                "Type": 0,
                "UniqueBack": mapping.get("unique_back", False),
                "BackIsHidden": True,
            }
        },
    }


def _write_new_tts_objects_to_patch(patch_root: Path, plan: list[dict], url_mapping: dict[str, dict]) -> list[str]:
    written: list[str] = []
    for item in plan:
        if item.get("action") != "新增" or item.get("blocking_errors"):
            continue
        target_path = item.get("target_path")
        target_bag_path = item.get("target_bag_path")
        target_object_key = item.get("target_object_key")
        if not target_path or not target_bag_path or not target_object_key:
            continue
        mapping = url_mapping[item["arkhamdb_id"]]
        object_path = patch_root / target_path
        object_path.parent.mkdir(parents=True, exist_ok=True)
        object_path.write_text(json.dumps(_new_card_tts_object(item, mapping), ensure_ascii=False, indent=2), encoding="utf-8")
        written.append(target_path)

        source_bag_path = settings.project_root / settings.sced_downloads / target_bag_path
        patched_bag_path = patch_root / target_bag_path
        if patched_bag_path.exists():
            bag = json.loads(patched_bag_path.read_text(encoding="utf-8"))
        elif source_bag_path.exists():
            bag = json.loads(source_bag_path.read_text(encoding="utf-8"))
        else:
            bag = {
                "Name": "Custom_Model_Bag",
                "GUID": item.get("directory_preset", {}).get("target_bag_guid", "000000"),
                "Nickname": item.get("directory_preset", {}).get("label", "新增中文包"),
                "ContainedObjects_order": [],
                "ContainedObjects_path": item.get("directory_preset", {}).get("target_object_dir", ""),
                "Transform": {"scaleX": 1, "scaleY": 1, "scaleZ": 1},
            }
        order = bag.setdefault("ContainedObjects_order", [])
        if target_object_key not in order:
            order.append(target_object_key)
        bag["ContainedObjects_path"] = item.get("directory_preset", {}).get("target_object_dir", bag.get("ContainedObjects_path", ""))
        patched_bag_path.parent.mkdir(parents=True, exist_ok=True)
        patched_bag_path.write_text(json.dumps(bag, ensure_ascii=False, indent=2), encoding="utf-8")
        if target_bag_path not in written:
            written.append(target_bag_path)
    return written


async def load_publish_package(
    db: AsyncSession,
    package_id: int,
    allowed_statuses: set[ErrataPackageStatus] | None = None,
) -> tuple[ErrataPackage, list[ErrataDraft]]:
    package = await db.get(ErrataPackage, package_id)
    if package is None:
        raise HTTPException(status_code=404, detail="勘误包不存在")
    allowed = allowed_statuses or {ErrataPackageStatus.WAITING_PUBLISH}
    if package.status not in allowed:
        raise HTTPException(status_code=409, detail="只有待发布的勘误包可以进入发布流程")

    result = await db.execute(
        select(ErrataDraft)
        .where(ErrataDraft.package_id == package_id)
        .where(ErrataDraft.archived_at.is_(None))
        .order_by(ErrataDraft.arkhamdb_id)
    )
    drafts = list(result.scalars().all())
    if not drafts:
        raise HTTPException(status_code=404, detail="勘误包没有可发布卡牌")
    return package, drafts


async def _local_card_paths_for_package(db: AsyncSession, drafts: list[ErrataDraft]) -> dict[str, str]:
    ids = [draft.arkhamdb_id for draft in drafts]
    if not ids:
        return {}
    result = await db.execute(
        select(LocalCardFile)
        .where(LocalCardFile.arkhamdb_id.in_(ids))
        .order_by(LocalCardFile.arkhamdb_id, LocalCardFile.face)
    )
    paths: dict[str, str] = {}
    for record in result.scalars().all():
        paths.setdefault(record.arkhamdb_id, record.relative_path)
    return paths


async def _directory_presets_for_plan(db: AsyncSession) -> list[dict]:
    result = await db.execute(select(PublishDirectoryPreset).where(PublishDirectoryPreset.is_active.is_(True)))
    return [
        {
            "id": preset.id,
            "local_dir_prefix": preset.local_dir_prefix,
            "target_area": preset.target_area.value,
            "target_bag_path": preset.target_bag_path,
            "target_bag_guid": preset.target_bag_guid,
            "target_object_dir": preset.target_object_dir,
            "label": preset.label,
            "is_active": preset.is_active,
        }
        for preset in result.scalars().all()
    ]


def _split_cards_by_back_type(cards: list[dict]) -> list[dict]:
    groups: list[dict] = []
    single_cards = [card for card in cards if not card.get("unique_back")]
    double_cards = [card for card in cards if card.get("unique_back")]
    if single_cards:
        groups.extend(group_cards_by_sheet(single_cards, max_per_sheet=30))
    if double_cards:
        groups.extend(group_cards_by_sheet(double_cards, max_per_sheet=30))
    return groups


def build_approved_cards_from_package(drafts: list[ErrataDraft], local_paths: dict[str, str] | None = None) -> list[dict]:
    cards: list[dict] = []
    for draft in drafts:
        faces = draft.modified_faces or {}
        front = faces.get("a") or next(iter(faces.values()), {})
        cards.append({
            "arkhamdb_id": draft.arkhamdb_id,
            "name_zh": front.get("name", draft.arkhamdb_id) if isinstance(front, dict) else draft.arkhamdb_id,
            "sheet_name": "",
            "unique_back": isinstance(faces.get("b"), dict),
            "local_relative_path": (local_paths or {}).get(draft.arkhamdb_id, ""),
        })

    sheet_names: dict[str, str] = {}
    for sheet in _split_cards_by_back_type(cards):
        for arkhamdb_id in sheet["arkhamdb_ids"]:
            sheet_names[arkhamdb_id] = sheet["sheet_name"]

    for card in cards:
        card["sheet_name"] = sheet_names[card["arkhamdb_id"]]
    return cards


@router.post("/step1-generate-sheets")
async def step1_generate_sheets(
    body: dict,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """步骤1：为指定勘误包生成卡牌精灵图。"""
    package_id = body.get("package_id")
    if package_id is None:
        raise HTTPException(status_code=400, detail="缺少勘误包 ID")
    package, drafts = await load_publish_package(db, int(package_id))

    temp_dir = settings.project_root / settings.cache_dir / "publish" / package.package_no
    temp_dir.mkdir(parents=True, exist_ok=True)

    card_images = []
    for draft in drafts:
        faces = draft.modified_faces or {}
        front = faces.get("a") or next(iter(faces.values()), {})
        if not isinstance(front, dict):
            front = {}
        front = merge_original_picture_for_face(draft.original_faces or {}, "a", front)
        back = faces.get("b")
        is_double = isinstance(back, dict)

        front_path = render_card_preview(front, temp_dir, f"{draft.arkhamdb_id}", dpi=300, quality=85)
        back_path = None
        if is_double:
            back = merge_original_picture_for_face(draft.original_faces or {}, "b", back)
            back_path = render_card_preview(back, temp_dir, f"{draft.arkhamdb_id}_back", dpi=300, quality=85)

        card_images.append(
            {
                "arkhamdb_id": draft.arkhamdb_id,
                "front_path": front_path,
                "back_path": back_path,
                "is_double_sided": is_double,
                "name_zh": front.get("name", ""),
                "unique_back": is_double,
            }
        )

    sheets = _split_cards_by_back_type(card_images)

    generated = []
    for sheet in sheets:
        card_count = len(sheet["arkhamdb_ids"])
        grid_width = min(card_count, 10)
        grid_height = max(1, (card_count + 9) // 10)
        grid_size = (grid_height, grid_width)
        front_sheet_path = str(temp_dir / f"{sheet['sheet_name']}.jpg")
        create_decksheet(sheet["front_images"], grid_size=grid_size, output_path=front_sheet_path)

        back_sheet_path = None
        if any(sheet["back_images"]):
            back_sheet_path = str(temp_dir / f"{sheet['sheet_name']}-back.jpg")
            create_decksheet(sheet["back_images"], grid_size=grid_size, output_path=back_sheet_path)

        generated.append(
            {
                "sheet_name": sheet["sheet_name"],
                "front_sheet": front_sheet_path,
                "back_sheet": back_sheet_path,
                "card_ids": sheet["arkhamdb_ids"],
                "grid_width": grid_width,
                "grid_height": grid_height,
            }
        )

    return {
        "package_id": package.id,
        "package_no": package.package_no,
        "generated_sheets": generated,
        "approved_cards": build_approved_cards_from_package(drafts),
        "total_cards": len(card_images),
        "total_sheets": len(generated),
    }


@router.post("/step2-upload")
async def step2_upload(
    body: dict,
    admin: User = Depends(require_admin),
):
    """步骤2：将精灵图上传到图床"""
    uploader = create_uploader(body.get("upload_config", {}))
    sheets = body["sheets"]
    urls = {}

    for sheet in sheets:
        name = sheet["sheet_name"]
        url = await uploader.upload(sheet["front_sheet"], f"{name}.jpg")
        if url:
            urls[name] = url

        if sheet.get("back_sheet"):
            back_url = await uploader.upload(
                sheet["back_sheet"], f"{name}-back.jpg"
            )
            if back_url:
                urls[f"{name}-back"] = back_url

    return {"urls": urls}


@router.post("/step3-export-tts")
async def step3_export_tts(
    body: dict,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """步骤3：按勘误包导出 TTS 存档包 JSON 文件。"""
    package_id = body.get("package_id")
    if package_id is None:
        raise HTTPException(status_code=400, detail="缺少勘误包 ID")
    package, drafts = await load_publish_package(
        db,
        int(package_id),
        {ErrataPackageStatus.WAITING_PUBLISH, ErrataPackageStatus.PUBLISHING},
    )
    bag_json = generate_tts_bag_json(
        build_approved_cards_from_package(drafts),
        body["sheet_urls"],
        body.get("sheet_grids", {}),
    )

    export_path = (
        settings.project_root / settings.cache_dir / "exports" / f"tts_bag_{package.package_no}.json"
    )
    export_path.parent.mkdir(parents=True, exist_ok=True)
    export_path.write_text(
        json.dumps(bag_json, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return FileResponse(
        export_path,
        media_type="application/json",
        filename="勘误发布包.json",
    )


@router.post("/step5-upload-tts-json")
async def step5_upload_tts_json(
    file: UploadFile = File(...),
    admin: User = Depends(require_admin),
):
    """步骤5：上传 TTS 存档 JSON，提取卡牌 URL 映射"""
    content = await file.read()
    data = json.loads(content)

    url_mapping = extract_steam_urls_from_json(data)

    return {
        "url_mapping": url_mapping,
        "total_cards": len(url_mapping),
    }


@router.post("/step6-export-replacements")
async def step6_export_replacements(
    body: dict,
    admin: User = Depends(require_admin),
):
    """步骤6：导出 SCED-downloads 中文包替换文件，不直接修改官方仓库。"""
    export_base = settings.project_root / settings.cache_dir / "exports" / "sced_downloads_patch"
    if export_base.exists():
        shutil.rmtree(export_base)
    export_base.mkdir(parents=True, exist_ok=True)

    roots = [
        (
            "decomposed/language-pack/Simplified Chinese - Campaigns",
            settings.project_root
            / settings.sced_downloads
            / "decomposed"
            / "language-pack"
            / "Simplified Chinese - Campaigns",
        ),
        (
            "decomposed/language-pack/Simplified Chinese - Player Cards",
            settings.project_root
            / settings.sced_downloads
            / "decomposed"
            / "language-pack"
            / "Simplified Chinese - Player Cards",
        ),
    ]

    all_modified: list[str] = []
    for relative_root, source_root in roots:
        if not source_root.exists():
            continue
        output_root = export_base / relative_root
        modified = export_chinese_card_url_replacements(
            source_root,
            output_root,
            body["url_mapping"],
        )
        all_modified.extend([f"{relative_root}/{item}" for item in modified])

    manifest = {
        "说明": "请将本压缩包内容复制到你的 SCED-downloads fork 仓库根目录，检查后提交 PR。官方仓库未被本系统直接修改。",
        "modified_files": all_modified,
        "total_modified": len(all_modified),
    }
    (export_base / "MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    archive_path = shutil.make_archive(str(export_base), "zip", export_base)
    return FileResponse(
        archive_path,
        media_type="application/zip",
        filename="SCED-downloads-PR补丁包.zip",
    )


@router.post("/step6-replace-urls")
async def step6_replace_urls(
    body: dict,
    admin: User = Depends(require_admin),
):
    """兼容旧前端路径：实际只导出补丁包，不修改官方仓库。"""
    return await step6_export_replacements(body, admin)
