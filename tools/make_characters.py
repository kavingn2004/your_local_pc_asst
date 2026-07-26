#!/usr/bin/env python3
"""Turn a folder of character artwork into transparent overlay sprites.

Backgrounds are removed by flood-filling inward from the image edges, so
enclosed light areas (eyes, logos, highlights) survive — a plain "make white
transparent" pass would punch holes in them.

Usage:  python3 make_characters.py <source-dir> [dest-dir]
"""
import sys, re
from pathlib import Path
from PIL import Image, ImageDraw

SPRITE_H = 260          # stored tall; the overlay scales down at runtime
SENTINEL = (255, 0, 255)
THRESH   = 60           # how far a pixel may differ and still count as background
# Some artwork has a textured (not flat) backdrop and needs a looser match.
# Too loose eats into the character, so these are tuned per image.
THRESH_OVERRIDE = {"cap": 150, "captain-america": 150}

PRETTY = {
    "bp": "Black Panther", "bw": "Black Widow", "cap": "Captain America",
    "wnada": "Wanda", "wanda": "Wanda", "hero-spiderman": "Spider-Man",
    "iron man": "Iron Man", "ironman": "Iron Man",
}


def nice_name(stem: str) -> str:
    key = re.sub(r"\.[0-9a-f]{6,}$", "", stem).strip().lower()
    if key in PRETTY:
        return PRETTY[key]
    return key.replace("-", " ").replace("_", " ").title()


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def cutout(path: Path, height: int = SPRITE_H, thresh: int = None):
    im = Image.open(path).convert("RGBA")
    w, h = im.size
    rgb = im.convert("RGB")
    seeds = [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1),
             (w // 2, 0), (w // 2, h - 1), (0, h // 2), (w - 1, h // 2)]
    for s in seeds:
        try:
            ImageDraw.floodfill(rgb, s, SENTINEL, thresh=thresh or THRESH)
        except Exception:
            pass
    src, dst = rgb.load(), im.load()
    cleared = 0
    for y in range(h):
        for x in range(w):
            if src[x, y] == SENTINEL:
                dst[x, y] = (0, 0, 0, 0)
                cleared += 1
    box = im.getbbox()
    if box:
        im = im.crop(box)
    ratio = height / im.height
    im = im.resize((max(1, int(im.width * ratio)), height), Image.LANCZOS)
    return im, cleared / float(w * h)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    src = Path(sys.argv[1]).expanduser()
    dst = Path(sys.argv[2]).expanduser() if len(sys.argv) > 2 else \
        Path.home() / ".config" / "spiderman" / "characters"
    dst.mkdir(parents=True, exist_ok=True)

    exts = {".png", ".jpg", ".jpeg", ".webp"}
    made = []
    for f in sorted(src.iterdir()):
        if f.is_dir() or f.suffix.lower() not in exts:
            continue
        name = nice_name(f.stem)
        try:
            th = THRESH_OVERRIDE.get(f.stem.lower()) or THRESH_OVERRIDE.get(slug(name))
            im, removed = cutout(f, thresh=th)
        except Exception as e:
            print(f"  ❌ {f.name}: {e}")
            continue
        out = dst / f"{slug(name)}.png"
        im.save(out, "PNG")
        flag = "✅" if 0.05 < removed < 0.92 else "⚠️ check"
        print(f"  {flag} {name:<18} {im.size}  bg removed {removed:.0%}  -> {out.name}")
        made.append(name)
    print(f"\n  {len(made)} character(s) in {dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
