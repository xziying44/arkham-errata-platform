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
    assert cached.size == (375, 525)


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
    assert cached.size == (375, 525)
    center = cached.getpixel((187, 262))
    assert center[0] > 200 and center[1] < 40 and center[2] < 40


def test_download_and_cut_sheet_uses_preview_scale_and_quality(tmp_path, monkeypatch):
    """TTS 参考图缓存应按预览配置半尺寸降采样，减少服务器带宽占用。"""
    from app.services import image_cache

    source = Image.new("RGB", (750, 1050), (255, 0, 0))
    buffer = BytesIO()
    source.save(buffer, format="JPEG")

    class FakeResponse:
        content = buffer.getvalue()

        def raise_for_status(self):
            return None

    saved = {}
    original_save = Image.Image.save

    def capture_save(self, fp, format=None, **params):
        saved["quality"] = params.get("quality")
        return original_save(self, fp, format=format, **params)

    monkeypatch.setattr(image_cache.httpx, "get", lambda *args, **kwargs: FakeResponse())
    monkeypatch.setattr(image_cache.settings, "preview_image_scale", 0.5, raising=False)
    monkeypatch.setattr(image_cache.settings, "preview_jpeg_quality", 70, raising=False)
    monkeypatch.setattr(Image.Image, "save", capture_save)

    result = image_cache.download_and_cut_sheet(
        sheet_url="https://example.test/card.jpg",
        grid_position=0,
        grid_width=1,
        grid_height=1,
        cache_dir=tmp_path,
        cache_key="preview-compressed",
    )

    assert result is not None
    cached = Image.open(result)
    assert cached.size == (375, 525)
    assert saved["quality"] == 70


def test_ensure_preview_cached_image_downscales_existing_cache(tmp_path, monkeypatch):
    """已缓存的旧大图再次访问时应自动降采样，避免继续传输大文件。"""
    from app.services import image_cache

    cached_path = tmp_path / "old-cache.jpg"
    Image.new("RGB", (750, 1050), (0, 255, 0)).save(cached_path, "JPEG", quality=90)
    monkeypatch.setattr(image_cache.settings, "preview_image_scale", 0.5, raising=False)
    monkeypatch.setattr(image_cache.settings, "preview_jpeg_quality", 70, raising=False)

    image_cache.ensure_preview_cached_image(cached_path)

    cached = Image.open(cached_path)
    assert cached.size == (375, 525)
