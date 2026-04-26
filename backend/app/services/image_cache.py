import httpx
from pathlib import Path
from PIL import Image
from io import BytesIO

CARD_W = 750
CARD_H = 1050


def calc_grid_coords(grid_position: int, grid_width: int) -> tuple[int, int, int, int]:
    """计算卡牌在精灵图中的像素坐标范围"""
    row = grid_position // grid_width
    col = grid_position % grid_width
    x = col * CARD_W
    y = row * CARD_H
    return (x, y, x + CARD_W, y + CARD_H)


def download_and_cut_sheet(
    sheet_url: str,
    grid_position: int,
    grid_width: int,
    grid_height: int,
    cache_dir: Path,
    cache_key: str,
) -> str | None:
    """下载精灵图大图，裁切指定位置单张卡图，缓存到本地"""
    expected_path = cache_dir / f"{cache_key}.jpg"
    if expected_path.exists():
        return str(expected_path)

    try:
        resp = httpx.get(sheet_url, timeout=30, follow_redirects=True)
        resp.raise_for_status()
        sheet_img = Image.open(BytesIO(resp.content))
    except Exception:
        return None

    if sheet_img.width <= CARD_W and sheet_img.height <= CARD_H:
        card_img = sheet_img.copy()
    else:
        cell_w = sheet_img.width / max(grid_width, 1)
        cell_h = sheet_img.height / max(grid_height, 1)
        row = grid_position // max(grid_width, 1)
        col = grid_position % max(grid_width, 1)
        x1 = round(col * cell_w)
        y1 = round(row * cell_h)
        x2 = round((col + 1) * cell_w)
        y2 = round((row + 1) * cell_h)
        if x1 >= sheet_img.width or y1 >= sheet_img.height:
            card_img = sheet_img.copy()
        else:
            card_img = sheet_img.crop((x1, y1, min(x2, sheet_img.width), min(y2, sheet_img.height)))
            if card_img.size != (CARD_W, CARD_H):
                card_img = card_img.resize((CARD_W, CARD_H), Image.Resampling.LANCZOS)
    if card_img.mode not in {"RGB", "L"}:
        card_img = card_img.convert("RGB")
    expected_path.parent.mkdir(parents=True, exist_ok=True)
    card_img.save(expected_path, "JPEG", quality=90)
    return str(expected_path)


def cache_all_tts_images(tts_cards: list, cache_dir: Path) -> dict[str, tuple[str | None, str | None]]:
    """批量预切割所有 TTS 卡图。返回 {arkhamdb_id: (front_cache_path, back_cache_path)}"""
    result = {}
    for card in tts_cards:
        front_path = None
        back_path = None
        if card.face_url:
            front_path = download_and_cut_sheet(
                sheet_url=card.face_url,
                grid_position=card.grid_position,
                grid_width=card.grid_width,
                grid_height=card.grid_height,
                cache_dir=cache_dir,
                cache_key=f"{card.source}_{card.arkhamdb_id}_front",
            )
        if card.unique_back and card.back_url:
            back_path = download_and_cut_sheet(
                sheet_url=card.back_url,
                grid_position=card.grid_position,
                grid_width=card.grid_width,
                grid_height=card.grid_height,
                cache_dir=cache_dir,
                cache_key=f"{card.source}_{card.arkhamdb_id}_back",
            )
        result[card.arkhamdb_id] = (front_path, back_path)
    return result
