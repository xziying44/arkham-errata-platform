"""图片上传服务 - 支持多种图床后端"""

import base64
import httpx
from abc import ABC, abstractmethod


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
    """本地上传器（开发用桩实现）"""

    def __init__(self, port: int = 8234, host: str = "localhost"):
        self.port = port
        self.host = host

    async def check_exists(self, filename: str) -> str | None:
        return None

    async def upload(self, filepath: str, filename: str) -> str | None:
        return f"http://{self.host}:{self.port}/sheets/{filename}"


def create_uploader(config: dict) -> ImageUploader:
    """根据配置创建对应的图片上传器实例

    Args:
        config: 包含 image_host 等键的配置字典
            - image_host="cloudinary" 时需提供 cloud_name, api_key, api_secret
            - image_host="imgbb" 时需提供 imgbb_api_key
            - image_host="local"（默认）时可选 localhost_port

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

    return LocalUploader(port=config.get("localhost_port", 8234))
