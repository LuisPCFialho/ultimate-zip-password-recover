#!/usr/bin/env python3
"""Generate packaging/win/uzpr.ico with a padlock motif at multiple sizes."""

from __future__ import annotations

import io
import struct
import subprocess
import sys
from pathlib import Path


def _ensure_pillow() -> None:
    try:
        import PIL  # noqa: F401
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "Pillow"])


def _draw_padlock(size: int):  # returns PIL.Image
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGBA", (size, size), (30, 30, 62, 255))  # #1e1e3e
    draw = ImageDraw.Draw(img)

    cx = size // 2

    # Body rectangle (gold)
    body_top = size * 52 // 100
    body_bottom = size * 88 // 100
    body_left = cx - size * 28 // 100
    body_right = cx + size * 28 // 100
    body_color = (240, 192, 64)  # #f0c040 gold
    r = max(size // 16, 2)
    draw.rounded_rectangle(
        [body_left, body_top, body_right, body_bottom],
        radius=r,
        fill=body_color,
    )

    # Keyhole: circle + slot
    kc_x, kc_y = cx, (body_top + body_bottom) // 2 - size // 20
    kc_r = max(size // 12, 3)
    draw.ellipse([kc_x - kc_r, kc_y - kc_r, kc_x + kc_r, kc_y + kc_r], fill=(30, 30, 62))
    kh_w = max(size // 20, 2)
    kh_h = max(size // 9, 3)
    draw.rectangle([kc_x - kh_w // 2, kc_y, kc_x + kh_w // 2, kc_y + kh_h], fill=(30, 30, 62))

    # Shackle arc + legs
    shackle_left = cx - size * 18 // 100
    shackle_right = cx + size * 18 // 100
    shackle_top = size * 16 // 100
    shackle_bottom = body_top + size // 16
    shackle_width = max(size // 14, 2)
    draw.arc(
        [shackle_left, shackle_top, shackle_right, shackle_bottom],
        start=180,
        end=0,
        fill=body_color,
        width=shackle_width,
    )
    mid_y = (shackle_top + shackle_bottom) // 2
    draw.line(
        [(shackle_left, mid_y), (shackle_left, shackle_bottom)],
        fill=body_color,
        width=shackle_width,
    )
    draw.line(
        [(shackle_right, mid_y), (shackle_right, shackle_bottom)],
        fill=body_color,
        width=shackle_width,
    )

    # "ZIP" text inside body (larger sizes only)
    if size >= 48:
        font_size = max(size // 9, 8)
        try:
            font = ImageFont.truetype("arial.ttf", font_size)
        except OSError:
            font = ImageFont.load_default()
        text = "ZIP"
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text((cx - tw // 2, body_bottom - th - size // 20), text, fill=(30, 30, 62), font=font)

    return img


def _build_ico(images) -> bytes:
    """Assemble a valid ICO binary from a list of RGBA PIL images (PNG-compressed)."""
    num = len(images)
    png_datas = []
    for img in images:
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        png_datas.append(buf.getvalue())

    # ICO file header: reserved=0, type=1 (icon), count
    header = struct.pack("<HHH", 0, 1, num)

    # Directory entries (16 bytes each); offset starts after header + all entries
    offset = 6 + num * 16
    entries = b""
    for img, data in zip(images, png_datas, strict=True):
        w = img.width if img.width < 256 else 0
        h = img.height if img.height < 256 else 0
        entries += struct.pack("<BBBBHHII", w, h, 0, 0, 1, 32, len(data), offset)
        offset += len(data)

    return header + entries + b"".join(png_datas)


def main() -> None:
    _ensure_pillow()

    import click

    root = Path(__file__).parent.parent
    ico_path = root / "packaging" / "win" / "uzpr.ico"
    ico_path.parent.mkdir(parents=True, exist_ok=True)

    sizes = [16, 32, 48, 64, 128, 256]
    images = [_draw_padlock(s) for s in sizes]

    ico_bytes = _build_ico(images)
    ico_path.write_bytes(ico_bytes)

    size_kb = ico_path.stat().st_size / 1024
    click.echo(f"Created {ico_path}  ({size_kb:.1f} KB, {len(sizes)} sizes)")


if __name__ == "__main__":
    main()
