"""
本地 .card 文件扫描器测试

使用临时目录模拟卡牌数据库目录结构，无需真实数据文件。
"""
import json
import tempfile
from pathlib import Path
from app.services.scanner import scan_card_database, detect_double_sided


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
