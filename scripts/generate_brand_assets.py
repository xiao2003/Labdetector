#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate LabDetector desktop branding assets."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = PROJECT_ROOT / 'assets' / 'branding'
PNG_PATH = ASSET_DIR / 'labdetector_logo.png'
ICO_PATH = ASSET_DIR / 'labdetector.ico'


def _draw_gradient(draw: ImageDraw.ImageDraw, size: int) -> None:
    top = (8, 19, 32)
    bottom = (18, 73, 96)
    for y in range(size):
        ratio = y / max(size - 1, 1)
        color = tuple(int(top[idx] * (1 - ratio) + bottom[idx] * ratio) for idx in range(3))
        draw.line((0, y, size, y), fill=color)


def build_logo(size: int = 1024) -> Image.Image:
    canvas = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    _draw_gradient(draw, size)

    shadow = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_draw.rounded_rectangle((110, 110, size - 110, size - 110), radius=220, fill=(0, 0, 0, 160))
    shadow = shadow.filter(ImageFilter.GaussianBlur(28))
    canvas.alpha_composite(shadow)

    draw.rounded_rectangle((92, 92, size - 92, size - 92), radius=220, fill=(11, 28, 44, 255), outline=(92, 227, 255, 255), width=18)

    shield = [
        (size * 0.50, size * 0.18),
        (size * 0.77, size * 0.29),
        (size * 0.72, size * 0.70),
        (size * 0.50, size * 0.84),
        (size * 0.28, size * 0.70),
        (size * 0.23, size * 0.29),
    ]
    draw.polygon(shield, fill=(16, 52, 68, 255), outline=(112, 240, 255, 255))
    draw.line(shield + [shield[0]], fill=(112, 240, 255, 255), width=18, joint='curve')

    beaker = [
        (size * 0.40, size * 0.31),
        (size * 0.46, size * 0.31),
        (size * 0.46, size * 0.42),
        (size * 0.60, size * 0.69),
        (size * 0.40, size * 0.69),
        (size * 0.54, size * 0.42),
        (size * 0.54, size * 0.31),
        (size * 0.60, size * 0.31),
    ]
    draw.line(beaker, fill=(255, 255, 255, 255), width=22, joint='curve')
    draw.line((size * 0.37, size * 0.69, size * 0.63, size * 0.69), fill=(255, 255, 255, 255), width=22)

    liquid = [
        (size * 0.42, size * 0.56),
        (size * 0.47, size * 0.54),
        (size * 0.52, size * 0.58),
        (size * 0.57, size * 0.55),
        (size * 0.59, size * 0.64),
        (size * 0.41, size * 0.64),
    ]
    draw.polygon(liquid, fill=(52, 223, 206, 255))
    draw.line(liquid[:4], fill=(136, 255, 243, 255), width=10)

    for offset in (0.0, 0.06, 0.12):
        bbox = (
            size * (0.58 + offset),
            size * (0.31 - offset * 0.55),
            size * (0.84 + offset),
            size * (0.57 - offset * 0.15),
        )
        draw.arc(bbox, start=230, end=320, fill=(112, 240, 255, 255), width=16)

    node_centers = [
        (size * 0.71, size * 0.23),
        (size * 0.78, size * 0.19),
        (size * 0.82, size * 0.26),
    ]
    for x, y in node_centers:
        draw.ellipse((x - 18, y - 18, x + 18, y + 18), fill=(255, 255, 255, 255))
        draw.ellipse((x - 12, y - 12, x + 12, y + 12), fill=(52, 223, 206, 255))

    return canvas


def main() -> None:
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    logo = build_logo(1024)
    logo.resize((512, 512), Image.Resampling.LANCZOS).save(PNG_PATH)
    logo.save(ICO_PATH, sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
    print(f'Wrote {PNG_PATH}')
    print(f'Wrote {ICO_PATH}')


if __name__ == '__main__':
    main()
