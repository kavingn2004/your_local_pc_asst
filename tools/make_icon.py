#!/usr/bin/env python3
"""Generate the spider notification icon (black spider on a red web).

Usage:  python3 make_icon.py [output.png]
"""
import sys, math
from pathlib import Path
from PIL import Image, ImageDraw

S = 256

def main():
    out = sys.argv[1] if len(sys.argv) > 1 else str(
        Path.home() / ".config" / "spiderman" / "spiderman.png")

    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx = cy = S // 2

    # red disc
    d.ellipse([6, 6, S-6, S-6], fill=(206, 32, 39, 255))
    d.ellipse([6, 6, S-6, S-6], outline=(120, 12, 16, 255), width=7)

    # web
    for ang in range(0, 360, 45):
        a = math.radians(ang)
        d.line([cx, cy, cx + 118*math.cos(a), cy + 118*math.sin(a)],
               fill=(150, 18, 22, 120), width=2)
    for r in (40, 72, 104):
        d.arc([cx-r, cy-r, cx+r, cy+r], 0, 360, fill=(150, 18, 22, 110), width=2)

    # spider body
    bx, by = 128, 138
    d.ellipse([bx-17, by-4,  bx+17, by+50], fill=(10, 10, 10, 255))   # abdomen
    d.ellipse([bx-12, by-34, bx+12, by-4],  fill=(10, 10, 10, 255))   # thorax

    # eight bent legs
    anchor_y = by - 20
    for side, ang in [(-1, 58), (-1, 26), (-1, -6), (-1, -34),
                      ( 1, 58), ( 1, 26), ( 1, -6), ( 1, -34)]:
        a = math.radians(ang)
        kx = bx + side*40*math.cos(a); ky = anchor_y - 40*math.sin(a)
        a2 = a - 0.7
        fx = kx + side*30*math.cos(a2); fy = ky - 30*math.sin(a2)
        d.line([bx, anchor_y, kx, ky], fill=(10, 10, 10, 255), width=6)
        d.line([kx, ky, fx, fy],       fill=(10, 10, 10, 255), width=6)

    Path(out).parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "PNG")
    print("saved", out)

if __name__ == "__main__":
    main()
