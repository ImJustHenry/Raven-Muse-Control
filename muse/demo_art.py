"""Original geometric demo covers, generated locally; not real album artwork."""
from functools import lru_cache
from io import BytesIO
from PIL import Image, ImageDraw


@lru_cache(maxsize=3)
def demo_cover(index):
    palettes = [("#101B30", "#EF996A", "#5FCBC3"),
                ("#2B1833", "#FFD377", "#E28160"),
                ("#102A36", "#C7F2F2", "#4271B5")]
    bg, sun, ridge = palettes[index % 3]
    image = Image.new("RGB", (128, 128), bg)
    draw = ImageDraw.Draw(image)
    draw.ellipse((59, 17, 108, 66), fill=sun)
    draw.polygon([(0, 78), (39, 42), (78, 85), (112, 61), (128, 72), (128, 128), (0, 128)], fill=ridge)
    draw.polygon([(0, 98), (36, 81), (72, 110), (128, 77), (128, 128), (0, 128)], fill=bg)
    for x in (15, 26, 37):
        draw.line((x, 15, x, 22), fill=sun, width=2)
    draw.line((12, 116, 116, 116), fill=sun, width=2)
    out = BytesIO()
    image.save(out, "PNG")
    return out.getvalue()
