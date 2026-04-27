from pathlib import Path
from PIL import Image
from app.services.sheet_generator import create_decksheet


def test_create_decksheet_uses_publish_quality_dimensions_and_dpi(tmp_path: Path):
    source = tmp_path / "card.jpg"
    Image.new("RGB", (750, 1050), (120, 80, 40)).save(source, "JPEG", quality=95, dpi=(300, 300))
    output = tmp_path / "sheet.jpg"

    create_decksheet([str(source)], output_path=str(output))

    with Image.open(output) as image:
        assert image.size == (750, 1050)
        assert image.info.get("dpi", (0, 0))[0] == 300
        assert image.info.get("dpi", (0, 0))[1] == 300
