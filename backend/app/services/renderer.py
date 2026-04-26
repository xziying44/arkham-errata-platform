"""卡牌渲染预览服务 - 将 .card JSON 渲染为预览图"""

import json
import os
import threading
from contextlib import contextmanager
from pathlib import Path

from app.config import settings


_render_lock = threading.Lock()


@contextmanager
def _arkham_card_maker_cwd():
    """临时切换到 arkham-card-maker 根目录，确保字体和图片映射可被加载"""
    assets_root = settings.project_root.parent / "arkham-card-maker"
    previous_cwd = os.getcwd()
    if assets_root.exists():
        os.chdir(assets_root)
    try:
        yield str(assets_root) if assets_root.exists() else ""
    finally:
        os.chdir(previous_cwd)


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

        output_dir.mkdir(parents=True, exist_ok=True)
        temp_card = output_dir / f"{filename}.card"
        temp_card.write_text(json.dumps(card_content, ensure_ascii=False), encoding="utf-8")

        with _render_lock:
            with _arkham_card_maker_cwd() as assets_path:
                config = {
                    "encounter_groups_dir": str(settings.project_root.parent / "卡牌数据库" / "exported_icons")
                }
                renderer = CardRenderer(assets_path=assets_path or None, config=config)
                options = RenderOptions(
                    dpi=150,
                    format="JPG",
                    bleed=0,
                    working_dir=str((settings.project_root / settings.local_card_db).resolve()),
                )
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
