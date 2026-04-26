"""
本地 .card 文件扫描器测试

使用临时目录模拟卡牌数据库目录结构，无需真实数据文件。
"""
import json
import tempfile
from pathlib import Path
from app.services.scanner import scan_card_database, detect_double_sided, load_card_content


def test_scan_card_database():
    """测试扫描卡牌数据库目录，验证字段提取和 base64 剥离"""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        # 模拟 category/cycle 二级目录结构
        card_dir = root / "剧本卡" / "01_基础游戏"
        card_dir.mkdir(parents=True)

        # 创建正面卡牌（双面卡）
        front = {
            "name": "测试卡",
            "type": "事件卡",
            "double_sided": True,
            "picture_base64": "AAAA",
        }
        (card_dir / "01150_a.card").write_text(
            json.dumps(front, ensure_ascii=False)
        )

        # 创建背面卡牌
        back = {
            "name": "测试卡(背面)",
            "type": "事件卡",
            "picture_base64": "BBBB",
        }
        (card_dir / "01150_b.card").write_text(
            json.dumps(back, ensure_ascii=False)
        )

        cards = scan_card_database(root)
        assert len(cards) == 2

        c = cards[0]
        assert c.arkhamdb_id == "01150"
        assert c.face == "a"
        assert c.category == "剧本卡"
        assert c.cycle == "01_基础游戏"
        assert "picture_base64" not in c.content_json

        # 验证双面卡检测
        double_sided = detect_double_sided(cards)
        assert "01150" in double_sided


def test_detect_double_sided_requires_both_faces():
    """只有同时存在 a 面和 b 面，才应按文件结构识别为双面卡"""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        card_dir = root / "玩家卡" / "01_基础游戏"
        card_dir.mkdir(parents=True)

        (card_dir / "01001_a.card").write_text(
            json.dumps({"name": "单面卡", "type": "支援卡"}, ensure_ascii=False)
        )
        (card_dir / "01002_a.card").write_text(
            json.dumps({"name": "双面正面", "type": "调查员"}, ensure_ascii=False)
        )
        (card_dir / "01002_b.card").write_text(
            json.dumps({"name": "双面背面", "type": "调查员"}, ensure_ascii=False)
        )

        double_sided = detect_double_sided(scan_card_database(root))

        assert "01001" not in double_sided
        assert "01002" in double_sided


def test_load_card_content_can_include_picture_base64():
    """渲染预览需要保留 picture_base64 作为卡图背景"""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        card_dir = root / "剧本卡" / "01_基础游戏"
        card_dir.mkdir(parents=True)
        (card_dir / "01112_a.card").write_text(json.dumps({
            "name": "走廊",
            "type": "地点卡",
            "picture_base64": "data:image/png;base64,AAAA",
        }, ensure_ascii=False), encoding="utf-8")

        stripped = load_card_content(root, "剧本卡/01_基础游戏/01112_a.card")
        full = load_card_content(root, "剧本卡/01_基础游戏/01112_a.card", include_picture=True)

        assert "picture_base64" not in stripped
        assert full["picture_base64"] == "data:image/png;base64,AAAA"
