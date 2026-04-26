"""发布目录预设：决定新增中文 TTS 对象写入哪个目标 Bag。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.errata_draft import PublishDirectoryPreset


async def resolve_directory_preset(db: AsyncSession, local_relative_path: str) -> PublishDirectoryPreset | None:
    result = await db.execute(select(PublishDirectoryPreset).where(PublishDirectoryPreset.is_active.is_(True)))
    presets = list(result.scalars().all())
    matches = [preset for preset in presets if local_relative_path.startswith(preset.local_dir_prefix)]
    if not matches:
        return None
    return sorted(matches, key=lambda item: len(item.local_dir_prefix), reverse=True)[0]
