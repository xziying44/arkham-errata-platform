"""发布 API - 审核通过后的发布管线（生成精灵图 → 上传 → 导出 → URL 替换）"""

import json
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.errata import Errata, ErrataStatus
from app.models.user import User
from app.api.auth import require_admin
from app.services.sheet_generator import create_decksheet, group_cards_by_sheet
from app.services.uploader import create_uploader
from app.services.url_replacer import (
    generate_tts_bag_json,
    replace_chinese_card_urls,
    extract_steam_urls_from_json,
)
from app.services.renderer import render_card_preview
from app.config import settings

router = APIRouter(prefix="/api/admin/publish", tags=["发布"])


@router.post("/step1-generate-sheets")
async def step1_generate_sheets(
    body: dict,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """步骤1：为指定批次的已批准勘误生成卡牌精灵图"""
    batch_id = body["batch_id"]

    result = await db.execute(
        select(Errata).where(
            Errata.batch_id == batch_id,
            Errata.status == ErrataStatus.APPROVED,
        )
    )
    errata_items = result.scalars().all()

    if not errata_items:
        raise HTTPException(status_code=404, detail="未找到已通过的勘误")

    temp_dir = settings.project_root / settings.cache_dir / "publish" / batch_id
    temp_dir.mkdir(parents=True, exist_ok=True)

    card_images = []
    for e in errata_items:
        modified = json.loads(e.modified_content)
        is_double = modified.get("double_sided", False) or "back" in modified

        front_path = render_card_preview(modified, temp_dir, f"{e.arkhamdb_id}")
        back_path = None

        if is_double and "back" in modified:
            back_path = render_card_preview(
                modified["back"], temp_dir, f"{e.arkhamdb_id}_back"
            )

        card_images.append(
            {
                "arkhamdb_id": e.arkhamdb_id,
                "front_path": front_path,
                "back_path": back_path,
                "is_double_sided": is_double,
                "name_zh": modified.get("name", ""),
                "unique_back": modified.get("unique_back", False),
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
            create_decksheet(
                sheet["back_images"], output_path=back_sheet_path
            )

        generated.append(
            {
                "sheet_name": sheet["sheet_name"],
                "front_sheet": front_sheet_path,
                "back_sheet": back_sheet_path,
                "card_ids": sheet["arkhamdb_ids"],
            }
        )

    return {
        "generated_sheets": generated,
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
async def step3_export_tts(body: dict):
    """步骤3：导出 TTS 存档包 JSON 文件"""
    bag_json = generate_tts_bag_json(
        body["approved_cards"],
        body["sheet_urls"],
        body.get("sheet_grids", {}),
    )

    export_path = (
        settings.project_root / settings.cache_dir / "exports" / "tts_bag.json"
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


@router.post("/step6-replace-urls")
async def step6_replace_urls(
    body: dict,
    admin: User = Depends(require_admin),
):
    """步骤6：将中文卡牌 JSON 中的图片 URL 替换为图床 URL"""
    zh_roots = [
        settings.project_root
        / settings.sced_downloads
        / "language-pack"
        / "Simplified Chinese - Campaigns",
        settings.project_root
        / settings.sced_downloads
        / "language-pack"
        / "Simplified Chinese - Player Cards",
    ]

    all_modified = []
    for zh_root in zh_roots:
        if zh_root.exists():
            modified = replace_chinese_card_urls(zh_root, body["url_mapping"])
            all_modified.extend(modified)

    return {
        "modified_files": all_modified,
        "total_modified": len(all_modified),
    }
