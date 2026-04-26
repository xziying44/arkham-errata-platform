"""发布 API - 审核通过后的发布管线（生成精灵图 → 上传 → 导出 → URL 替换）"""

import json
import shutil
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.card import CardIndex
from app.models.errata_draft import ErrataDraft, ErrataPackage, ErrataPackageStatus
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

router = APIRouter(prefix="/api/admin/publish", tags=["发布"])


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
