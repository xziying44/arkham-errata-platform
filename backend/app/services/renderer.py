"""卡牌渲染预览服务 - 将 .card JSON 渲染为预览图"""

import json
from pathlib import Path


def render_card_preview(card_content: dict, output_dir: Path, filename: str) -> str | None:
    """将 .card JSON 渲染为卡牌预览图

    Args:
        card_content: .card 文件内容的字典表示
        output_dir: 输出目录
        filename: 输出文件名（不含扩展名）

    Returns:
        渲染后的图片路径，若渲染失败则返回 None
    """
    try:
        from arkham_card_maker import CardRenderer, RenderOptions

        renderer = CardRenderer()
        temp_card = output_dir / f"{filename}.card"
        temp_card.write_text(json.dumps(card_content, ensure_ascii=False), encoding="utf-8")

        options = RenderOptions(dpi=150, format="JPEG", bleed=0)
        result = renderer.render(str(temp_card), options)

        output_path = output_dir / f"{filename}.jpg"
        result.save(str(output_path))
        temp_card.unlink(missing_ok=True)
        return str(output_path)
    except ImportError:
        # arkham_card_maker 未安装时返回 None
        return None
    except Exception as e:
        print(f"渲染失败: {e}")
        return None
