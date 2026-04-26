"""发布 API - 审核通过后的发布管线（生成精灵图 → 上传 → 导出 → URL 替换）"""

import json
import shutil
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.card import CardIndex
from app.models.errata_draft import ErrataDraft, ErrataPackage, ErrataPackageStatus, PublishArtifact, PublishArtifactKind, PublishArtifactStatus, PublishDirectoryPreset, PublishSession, PublishSessionStatus
from app.models.user import User
from app.api.auth import require_admin
from app.services.sheet_generator import create_decksheet, group_cards_by_sheet
from app.services.uploader import create_uploader
from app.services.url_replacer import (
    generate_tts_bag_json,
    export_chinese_card_url_replacements,
    extract_steam_urls_from_json,
)
from app.services.renderer import render_card_preview
from app.config import settings
from app.schemas.publish import PublishDirectoryPresetUpdateRequest, PublishSessionCreateRequest
from app.services.publish_package_builder import build_replacement_plan
from app.services.publish_sessions import add_artifact, create_publish_session, list_session_artifacts, load_publish_session, supersede_artifacts_after_step

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


@router.get("/directory-presets")
async def list_directory_presets(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    result = await db.execute(select(PublishDirectoryPreset).order_by(PublishDirectoryPreset.local_dir_prefix))
    return {"items": [serialize_directory_preset(preset) for preset in result.scalars().all()]}


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
        back = faces.get("b")
        front_path = render_card_preview(front, cards_dir, f"{draft.arkhamdb_id}_a")
        await add_artifact(db, session, PublishArtifactKind.CARD_IMAGE, Path(front_path), {"arkhamdb_id": draft.arkhamdb_id, "face": "a"})
        back_path = None
        if isinstance(back, dict):
            back_path = render_card_preview(back, cards_dir, f"{draft.arkhamdb_id}_b")
            await add_artifact(db, session, PublishArtifactKind.CARD_IMAGE, Path(back_path), {"arkhamdb_id": draft.arkhamdb_id, "face": "b"})
        card_images.append({
            "arkhamdb_id": draft.arkhamdb_id,
            "front_path": front_path,
            "back_path": back_path,
            "name_zh": front.get("name", ""),
            "unique_back": isinstance(back, dict),
        })

    sheets = group_cards_by_sheet(card_images, max_per_sheet=30)
    for sheet in sheets:
        grid_height = max(1, (len(sheet["arkhamdb_ids"]) + 9) // 10)
        front_sheet_path = sheets_dir / f"{sheet['sheet_name']}.jpg"
        create_decksheet(sheet["front_images"], output_path=str(front_sheet_path))
        await add_artifact(
            db,
            session,
            PublishArtifactKind.SHEET_FRONT,
            front_sheet_path,
            {"sheet_name": sheet["sheet_name"], "card_ids": sheet["arkhamdb_ids"], "grid_width": 10, "grid_height": grid_height},
        )
        if any(sheet["back_images"]):
            back_sheet_path = sheets_dir / f"{sheet['sheet_name']}-back.jpg"
            create_decksheet(sheet["back_images"], output_path=str(back_sheet_path))
            await add_artifact(
                db,
                session,
                PublishArtifactKind.SHEET_BACK,
                back_sheet_path,
                {"sheet_name": f"{sheet['sheet_name']}-back", "front_sheet_name": sheet["sheet_name"], "card_ids": sheet["arkhamdb_ids"], "grid_width": 10, "grid_height": grid_height},
            )

    session.status = PublishSessionStatus.SHEETS_READY
    session.current_step = "confirm_sheets"
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
    return {"items": build_replacement_plan(roots, build_approved_cards_from_package(drafts), url_mapping)}


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


def _sheet_names_for_drafts(drafts: list[ErrataDraft], max_per_sheet: int = 30) -> dict[str, str]:
    names: dict[str, str] = {}
    for start_index in range(0, len(drafts), max_per_sheet):
        chunk = drafts[start_index:start_index + max_per_sheet]
        sheet_name = f"SheetZH{chunk[0].arkhamdb_id}-{chunk[-1].arkhamdb_id}"
        for draft in chunk:
            names[draft.arkhamdb_id] = sheet_name
    return names


def build_approved_cards_from_package(drafts: list[ErrataDraft]) -> list[dict]:
    sheet_names = _sheet_names_for_drafts(drafts)
    cards: list[dict] = []
    for draft in drafts:
        faces = draft.modified_faces or {}
        front = faces.get("a") or next(iter(faces.values()), {})
        cards.append({
            "arkhamdb_id": draft.arkhamdb_id,
            "name_zh": front.get("name", draft.arkhamdb_id) if isinstance(front, dict) else draft.arkhamdb_id,
            "sheet_name": sheet_names[draft.arkhamdb_id],
            "unique_back": len(faces) > 1,
        })
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
        back = faces.get("b")
        is_double = isinstance(back, dict)

        front_path = render_card_preview(front, temp_dir, f"{draft.arkhamdb_id}")
        back_path = None
        if is_double:
            back_path = render_card_preview(back, temp_dir, f"{draft.arkhamdb_id}_back")

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

    sheets = group_cards_by_sheet(card_images, max_per_sheet=30)

    generated = []
    for sheet in sheets:
        front_sheet_path = str(temp_dir / f"{sheet['sheet_name']}.jpg")
        create_decksheet(sheet["front_images"], output_path=front_sheet_path)

        back_sheet_path = None
        if any(sheet["back_images"]):
            back_sheet_path = str(temp_dir / f"{sheet['sheet_name']}-back.jpg")
            create_decksheet(sheet["back_images"], output_path=back_sheet_path)

        generated.append(
            {
                "sheet_name": sheet["sheet_name"],
                "front_sheet": front_sheet_path,
                "back_sheet": back_sheet_path,
                "card_ids": sheet["arkhamdb_ids"],
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
