"""精灵图生成服务 - 将多张卡牌图片拼接为一张大图"""

import math
import os
from pathlib import Path
from PIL import Image

CARD_W = 750
CARD_H = 1050
MAX_COLS = 10
MAX_BYTES = 10_485_670


def create_decksheet(
    img_path_list: list[str],
    grid_size: tuple[int, int] | None = None,
    output_path: str = "",
    quality: int = 90,
) -> str:
    """将卡牌图片列表拼接为精灵图（decksheet）

    Args:
        img_path_list: 卡牌图片路径列表
        grid_size: 可选的 (rows, cols) 网格尺寸，默认自动计算
        output_path: 输出文件路径
        quality: JPEG 质量（1-100），会自动降低直至文件 <= 10MB

    Returns:
        生成的精灵图文件路径
    """
    if not img_path_list:
        raise ValueError("图片列表为空")

    count = len(img_path_list)

    if grid_size is None:
        cols = min(count, MAX_COLS)
        rows = math.ceil(count / cols)
    else:
        rows, cols = grid_size

    canvas_w = cols * CARD_W
    canvas_h = rows * CARD_H
    canvas = Image.new("RGB", (canvas_w, canvas_h), (0, 0, 0))

    for idx, img_path in enumerate(img_path_list):
        row = idx // cols
        col = idx % cols
        x = col * CARD_W
        y = row * CARD_H
        try:
            img = Image.open(img_path)
            # 横版卡牌旋转为竖版
            if img.width > img.height:
                img = img.rotate(270, expand=True)
            img = img.resize((CARD_W, CARD_H), Image.LANCZOS)
            canvas.paste(img, (x, y))
        except Exception:
            continue

    output_path = str(output_path)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    current_quality = quality
    while current_quality >= 5:
        canvas.save(output_path, "JPEG", quality=current_quality)
        if os.path.getsize(output_path) <= MAX_BYTES:
            break
        current_quality -= 5

    return output_path


def group_cards_by_sheet(
    card_images: list[dict], max_per_sheet: int = 30
) -> list[dict]:
    """将卡牌图片按每张精灵图最大数量分组

    Args:
        card_images: 卡牌信息列表，每项包含 arkhamdb_id, front_path, back_path 等
        max_per_sheet: 每张精灵图最多包含的卡牌数

    Returns:
        分组后的精灵图信息列表
    """
    sheets = []
    current = {"front_images": [], "back_images": [], "arkhamdb_ids": []}

    for card in card_images:
        if len(current["arkhamdb_ids"]) >= max_per_sheet:
            sheets.append(current)
            current = {"front_images": [], "back_images": [], "arkhamdb_ids": []}

        current["front_images"].append(card.get("front_path", ""))
        current["back_images"].append(card.get("back_path", ""))
        current["arkhamdb_ids"].append(card["arkhamdb_id"])

    if current["arkhamdb_ids"]:
        sheets.append(current)

    for i, sheet in enumerate(sheets):
        start = sheet["arkhamdb_ids"][0]
        end = sheet["arkhamdb_ids"][-1]
        sheet["sheet_name"] = f"SheetZH{start}-{end}"

    return sheets
