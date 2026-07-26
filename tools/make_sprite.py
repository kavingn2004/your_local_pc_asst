#!/usr/bin/env python3
"""Turn a Spider-Man artwork PNG into a transparent overlay sprite.

Removes the background (flood-fills from the edges, so enclosed white areas
like the eyes are preserved), crops to content, and scales to SPRITE_H.

Usage:  python3 make_sprite.py <source.png> [output.png]
"""
import sys
from pathlib import Path
from PIL import Image, ImageDraw

SPRITE_H = 220          # stored at 220; the overlay scales it down at runtime
SENTINEL = (255, 0, 255)

def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    src = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else str(
        Path.home() / ".config" / "spiderman" / "spiderman-hero.png")

    im = Image.open(src).convert("RGBA")
    w, h = im.size
    rgb = im.convert("RGB")
    # flood-fill background from edges -> sentinel colour
    for seed in [(0, 0), (w-1, 0), (0, h-1), (w-1, h-1), (w//2, 0), (w//2, h-1)]:
        try:
            ImageDraw.floodfill(rgb, seed, SENTINEL, thresh=50)
        except Exception:
            pass
    src_px, out_px = rgb.load(), im.load()
    for y in range(h):
        for x in range(w):
            if src_px[x, y] == SENTINEL:
                out_px[x, y] = (0, 0, 0, 0)

    im = im.crop(im.getbbox())
    ratio = SPRITE_H / im.height
    im = im.resize((int(im.width * ratio), SPRITE_H), Image.LANCZOS)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    im.save(out, "PNG")
    print("saved", out, im.size)

if __name__ == "__main__":
    main()
