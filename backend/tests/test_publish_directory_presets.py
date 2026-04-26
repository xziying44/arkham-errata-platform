import pytest

from app.models.errata_draft import PublishDirectoryPreset, PublishDirectoryTargetArea
from app.services.publish_directory_presets import resolve_directory_preset


@pytest.mark.asyncio
async def test_resolve_directory_preset_uses_longest_prefix(db):
    broad = PublishDirectoryPreset(
        local_dir_prefix="剧本卡",
        target_area=PublishDirectoryTargetArea.CAMPAIGNS,
        target_bag_path="broad.json",
        target_bag_guid="111111",
        target_object_dir="Broad.111111",
        label="宽泛规则",
        is_active=True,
    )
    narrow = PublishDirectoryPreset(
        local_dir_prefix="剧本卡/09_绯红密钥",
        target_area=PublishDirectoryTargetArea.CAMPAIGNS,
        target_bag_path="scarlet.json",
        target_bag_guid="222222",
        target_object_dir="Scarlet.222222",
        label="绯红密钥",
        is_active=True,
    )
    db.add_all([broad, narrow])
    await db.commit()

    preset = await resolve_directory_preset(db, "剧本卡/09_绯红密钥/09586_a.card")
    assert preset is not None
    assert preset.target_bag_path == "scarlet.json"
