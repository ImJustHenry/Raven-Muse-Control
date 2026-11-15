"""Compose a design preview from the REAL SDK widget test captures.
Run after RMC_TEST_SDK=1 pytest: python tools/create_preview.py
No UI state is invented or painted here; the controls are captured test images.
"""
import argparse
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

parser = argparse.ArgumentParser()
parser.add_argument("--input", default="test-output")
parser.add_argument("--output", default="test-output/design-preview.png")
args = parser.parse_args()
source, output = Path(args.input), Path(args.output)

def font(size, bold=False):
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
    ]
    for path in paths:
        if Path(path).exists(): return ImageFont.truetype(path, size)
    try: return ImageFont.load_default(size=size)
    except TypeError: return ImageFont.load_default()

canvas = Image.new("RGB", (1280, 780), "#000000")
draw = ImageDraw.Draw(canvas)
white, muted, accent = "#F6FAFC", "#A9BAC6", "#8CEBD4"
draw.text((48, 28), "Raven-Muse-Control", font=font(32, True), fill=white)
draw.text((48, 79), "Cover art. Same tiny footprint.", font=font(21), fill=muted)
draw.text((1110, 42), "v1.3", font=font(20, True), fill=accent)
draw.line((48, 126, 1232, 126), fill="#263B43", width=1)
draw.text((48, 151), "COMPACT  /  256 x 112  /  SHOWN AT 2x", font=font(14, True), fill=accent)
draw.text((720, 151), "OPEN ONLY WHEN NEEDED", font=font(14, True), fill=accent)

def paste(name, xy, size):
    image = Image.open(source / name).convert("RGBA").resize(size, Image.Resampling.LANCZOS)
    canvas.paste(image, xy, image)

paste("cover-midnight.png", (48, 195), (512, 224))
paste("focused-panel.png", (720, 195), (432, 320))
draw.text((48, 444), "64-pixel artwork. The whole card is one gaze target.", font=font(17), fill=white)
draw.text((48, 478), "CHANGES WITH THE TRACK", font=font(12, True), fill=accent)
draw.text((328, 478), "SAFE MISSING-ART FALLBACK", font=font(12, True), fill=accent)
paste("cover-golden.png", (48, 510), (256, 112))
paste("cover-unavailable.png", (328, 510), (256, 112))
draw.text((720, 551), "Playback controls stay the same.", font=font(18), fill=white)
draw.text((720, 584), "No separate music library or player.", font=font(16), fill=muted)
draw.text((48, 660), "Android: exposed phone artwork", font=font(16), fill=muted)
draw.text((48, 688), "iPhone: optional online metadata match, OFF by default", font=font(16), fill=muted)
draw.line((48, 728, 1232, 728), fill="#263B43", width=1)
draw.text((48, 746), "Actual Raven SDK captures | Original DEMO images | No physical phone or glasses validation", font=font(14), fill=muted)
output.parent.mkdir(parents=True, exist_ok=True)
canvas.save(output)
print(output)
