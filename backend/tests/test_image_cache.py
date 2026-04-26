from app.services.image_cache import calc_grid_coords


def test_calc_grid_coords_top_left():
    assert calc_grid_coords(0, 10) == (0, 0, 750, 1050)


def test_calc_grid_coords_first_row():
    result = calc_grid_coords(5, 10)
    assert result == (3750, 0, 4500, 1050)


def test_calc_grid_coords_second_row():
    result = calc_grid_coords(12, 10)
    assert result == (1500, 1050, 2250, 2100)

from io import BytesIO

from PIL import Image


def test_single_card_back_image_is_not_cropped_with_grid_offset(tmp_path, monkeypatch):
    """共享卡背是单张图时，即使 grid_position 很大也应直接缓存整张背图。"""
    from app.services import image_cache

    source = Image.new("RGBA", (750, 1050), (0, 0, 255, 255))
    buffer = BytesIO()
    source.save(buffer, format="PNG")

    class FakeResponse:
        content = buffer.getvalue()

        def raise_for_status(self):
            return None

    monkeypatch.setattr(image_cache.httpx, "get", lambda *args, **kwargs: FakeResponse())

    result = image_cache.download_and_cut_sheet(
        sheet_url="https://example.test/card-back.png",
        grid_position=27,
        grid_width=10,
        grid_height=7,
        cache_dir=tmp_path,
        cache_key="shared-back",
    )

    assert result is not None
    cached = Image.open(result)
    assert cached.size == (750, 1050)


def test_downscaled_deck_sheet_is_cropped_and_resized(tmp_path, monkeypatch):
    """SCED 玩家卡精灵图可能是缩小版，应按实际尺寸裁切后缩放到标准卡图。"""
    from app.services import image_cache

    sheet = Image.new("RGB", (4230, 4200), (0, 0, 0))
    cell_w = 423
    cell_h = 600
    target_col = 8
    target_row = 2
    for x in range(target_col * cell_w, (target_col + 1) * cell_w):
        for y in range(target_row * cell_h, (target_row + 1) * cell_h):
            sheet.putpixel((x, y), (255, 0, 0))
    buffer = BytesIO()
    sheet.save(buffer, format="JPEG")

    class FakeResponse:
        content = buffer.getvalue()

        def raise_for_status(self):
            return None

    monkeypatch.setattr(image_cache.httpx, "get", lambda *args, **kwargs: FakeResponse())

    result = image_cache.download_and_cut_sheet(
        sheet_url="https://example.test/downscaled-sheet.jpg",
        grid_position=28,
        grid_width=10,
        grid_height=7,
        cache_dir=tmp_path,
        cache_key="downscaled-front",
    )

    assert result is not None
    cached = Image.open(result)
    assert cached.size == (750, 1050)
    center = cached.getpixel((375, 525))
    assert center[0] > 200 and center[1] < 40 and center[2] < 40
