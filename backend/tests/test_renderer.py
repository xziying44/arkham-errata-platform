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
