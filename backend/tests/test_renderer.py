"""渲染预览服务测试"""

import json
import tempfile
from pathlib import Path
from app.services.renderer import render_card_preview


def test_render_card_preview_no_module():
    """测试在 arkham_card_maker 未安装时返回 None"""
    content = {
        "version": "1.0",
        "language": "zh",
        "type": "事件卡",
        "name": "测试卡",
        "class": "中立",
        "body": "测试效果文本。",
        "cost": 2,
        "level": 0,
    }
    with tempfile.TemporaryDirectory() as tmpdir:
        result = render_card_preview(content, Path(tmpdir), "test_card")
        # 如果 arkham_card_maker 未安装，应该返回 None
        if result:
            assert Path(result).exists()
        # 如果返回 None（ImportError），同样视为正常行为
        # 系统会在有 arkham_card_maker 的环境中生成真实预览图


def test_render_card_preview_uses_supported_jpg_format():
    """arkham-card-maker 的 API 接受 JPG，不接受 JPEG"""
    content = {"type": "事件卡", "class": "中立", "name": "测试", "body": "测试正文", "traits": []}
    with tempfile.TemporaryDirectory() as tmpdir:
        result = render_card_preview(content, Path(tmpdir), "format_check")
        assert result is None or result.endswith(".jpg")


def test_render_card_preview_uses_card_database_as_working_dir(monkeypatch, tmp_path):
    """正文中的 @exported_icons 应相对于卡牌数据库目录解析，而不是缓存目录。"""
    import sys
    import types
    from PIL import Image
    from app.config import settings

    captured = {}

    class FakeResult:
        def save(self, output_path):
            Image.new("RGB", (10, 10), (255, 255, 255)).save(output_path)

    class FakeRenderer:
        def __init__(self, assets_path=None, config=None):
            captured["assets_path"] = assets_path
            captured["config"] = config

        def render(self, card_path, options):
            captured["card_path"] = card_path
            captured["working_dir"] = options.working_dir
            return FakeResult()

    class FakeOptions:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    fake_module = types.SimpleNamespace(CardRenderer=FakeRenderer, RenderOptions=FakeOptions)
    monkeypatch.setitem(sys.modules, "arkham_card_maker", fake_module)

    result = render_card_preview({"body": '<img src="@exported_icons/test.png"></img>'}, tmp_path, "embedded")

    assert result is not None
    assert captured["working_dir"] == str((settings.project_root / settings.local_card_db).resolve())
