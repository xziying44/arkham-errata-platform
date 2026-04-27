"""图片上传服务 - 支持多种图床后端"""

import base64
import shutil
from pathlib import Path

import httpx
from abc import ABC, abstractmethod

from app.config import settings


class ImageUploader(ABC):
    """图片上传器抽象基类"""

    @abstractmethod
    async def check_exists(self, filename: str) -> str | None:
        """检查图片是否已存在，返回已有 URL 或 None"""
        ...

    @abstractmethod
    async def upload(self, filepath: str, filename: str) -> str | None:
        """上传图片，返回公开访问 URL 或 None"""
        ...


class CloudinaryUploader(ImageUploader):
    """Cloudinary 图床上传器"""

    def __init__(self, cloud_name: str, api_key: str, api_secret: str):
        self.cloud_name = cloud_name
        self.api_key = api_key
        self.api_secret = api_secret

    async def check_exists(self, filename: str) -> str | None:
        return None

    async def upload(self, filepath: str, filename: str) -> str | None:
        try:
            import cloudinary
            import cloudinary.uploader

            cloudinary.config(
                cloud_name=self.cloud_name,
                api_key=self.api_key,
                api_secret=self.api_secret,
            )
            result = cloudinary.uploader.upload(
                filepath,
                public_id=filename,
                folder="AH LCG - ZH",
                unique_filename=False,
            )
            return result.get("secure_url")
        except Exception:
            return None


class ImgBBUploader(ImageUploader):
    """ImgBB 图床上传器"""

    def __init__(self, api_key: str):
        self.api_key = api_key

    async def check_exists(self, filename: str) -> str | None:
        return None

    async def upload(self, filepath: str, filename: str) -> str | None:
        with open(filepath, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.imgbb.com/1/upload",
                data={"key": self.api_key, "image": b64, "name": filename},
                timeout=60,
            )

        if resp.status_code == 200:
            return resp.json()["data"]["url"]
        return None


class LocalUploader(ImageUploader):
    """本地上传器：复制到缓存目录，并返回前端可反代访问的相对 URL。"""

    def __init__(self, cache_subdir: str = "sheets"):
        self.cache_subdir = cache_subdir.strip("/") or "sheets"

    async def check_exists(self, filename: str) -> str | None:
        target_path = self._target_path(filename)
        if target_path.exists():
            return self._public_url(target_path)
        return None

    async def upload(self, filepath: str, filename: str) -> str | None:
        source_path = Path(filepath)
        if not source_path.exists() or not source_path.is_file():
            return None

        target_path = self._target_path(filename)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if source_path.resolve() != target_path.resolve():
            shutil.copy2(source_path, target_path)
        return self._public_url(target_path)

    def _target_path(self, filename: str) -> Path:
        safe_name = Path(filename).name
        return settings.project_root / settings.cache_dir / self.cache_subdir / safe_name

    def _public_url(self, path: Path) -> str:
        cache_root = settings.project_root / settings.cache_dir
        relative = path.relative_to(cache_root)
        return f"/static/cache/{relative.as_posix()}"


def create_uploader(config: dict) -> ImageUploader:
    """根据配置创建对应的图片上传器实例

    Args:
        config: 包含 image_host 等键的配置字典
            - image_host="cloudinary" 时需提供 cloud_name, api_key, api_secret
            - image_host="imgbb" 时需提供 imgbb_api_key
            - image_host="local"（默认）时可选 cache_subdir

    Returns:
        ImageUploader 实例
    """
    host = config.get("image_host", "local")

    if host == "cloudinary":
        return CloudinaryUploader(
            config["cloud_name"],
            config["api_key"],
            config["api_secret"],
        )
    elif host == "imgbb":
        return ImgBBUploader(config["imgbb_api_key"])

    return LocalUploader(cache_subdir=config.get("cache_subdir", "sheets"))
