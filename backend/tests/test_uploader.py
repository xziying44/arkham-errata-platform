from pathlib import Path

import pytest

from app.config import settings
from app.services.uploader import LocalUploader, create_uploader


@pytest.fixture
def isolated_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(settings, "project_root", tmp_path)
    monkeypatch.setattr(settings, "cache_dir", Path("cache"))
    return tmp_path / "cache"


@pytest.mark.asyncio
async def test_local_uploader_copies_file_to_static_cache(tmp_path: Path, isolated_cache: Path):
    source = tmp_path / "SheetZH-test.jpg"
    source.write_bytes(b"image")
    uploader = LocalUploader(cache_subdir="test-sheets")

    url = await uploader.upload(str(source), "SheetZH-test.jpg")

    assert url == "/static/cache/test-sheets/SheetZH-test.jpg"
    assert (isolated_cache / "test-sheets" / "SheetZH-test.jpg").read_bytes() == b"image"
    assert await uploader.check_exists("SheetZH-test.jpg") == url


@pytest.mark.asyncio
async def test_create_local_uploader_uses_static_cache_url(tmp_path: Path, isolated_cache: Path):
    source = tmp_path / "sheet.jpg"
    source.write_bytes(b"image")
    uploader = create_uploader({"image_host": "local", "cache_subdir": "publish-sheets"})

    url = await uploader.upload(str(source), "sheet.jpg")

    assert url == "/static/cache/publish-sheets/sheet.jpg"
    assert (isolated_cache / "publish-sheets" / "sheet.jpg").exists()
