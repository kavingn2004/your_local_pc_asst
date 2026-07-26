#!/usr/bin/env python3
"""Generate the Local_Asst application logo.

A rounded-square app icon: deep gradient, an "LA" lettermark, and a small
speech-bubble tail marking it as an assistant. Rendered at several sizes so
the launcher, window and notifications all get a crisp version.

Usage:  python3 make_logo.py [dest-dir]
"""
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

SIZES = [512, 256, 128, 64, 48]
FONT_BOLD = "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf"
FONT_MED  = "/usr/share/fonts/truetype/ubuntu/Ubuntu-M.ttf"

TOP    = (37, 99, 235)      # blue
BOTTOM = (109, 40, 217)     # violet
ACCENT = (56, 189, 248)     # cyan highlight


def _font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def render(size=512):
    S = size * 2                      # supersample, then downscale for smooth edges
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))

    # rounded-square body with a vertical gradient
    grad = Image.new("RGB", (1, S))
    for y in range(S):
        t = y / (S - 1)
        grad.putpixel((0, y), tuple(int(TOP[i] + (BOTTOM[i] - TOP[i]) * t) for i in range(3)))
    grad = grad.resize((S, S))

    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1],
                                           radius=int(S * 0.235), fill=255)
    img.paste(grad, (0, 0), mask)

    d = ImageDraw.Draw(img)

    # soft highlight arc across the top for depth
    glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([-S * 0.25, -S * 0.62, S * 1.25, S * 0.42],
                                 fill=(255, 255, 255, 46))
    glow = glow.filter(ImageFilter.GaussianBlur(S * 0.05))
    img.alpha_composite(Image.composite(glow, Image.new("RGBA", (S, S), (0, 0, 0, 0)), mask))

    # "LA" lettermark
    f = _font(FONT_BOLD, int(S * 0.40))
    text = "LA"
    bb = d.textbbox((0, 0), text, font=f)
    tx = (S - (bb[2] - bb[0])) // 2 - bb[0]
    ty = int(S * 0.245) - bb[1]
    d.text((tx + S * 0.012, ty + S * 0.012), text, font=f, fill=(0, 0, 0, 70))   # shadow
    d.text((tx, ty), text, font=f, fill=(255, 255, 255, 255))

    # accent underline + speech-bubble tail (the "assistant" cue)
    bar_w, bar_h = int(S * 0.30), int(S * 0.035)
    bx, by = (S - bar_w) // 2, int(S * 0.70)
    d.rounded_rectangle([bx, by, bx + bar_w, by + bar_h],
                        radius=bar_h // 2, fill=ACCENT + (255,))
    d.polygon([(S * 0.50 - S * 0.045, by + bar_h),
               (S * 0.50 + S * 0.045, by + bar_h),
               (S * 0.50 - S * 0.005, by + bar_h + S * 0.075)],
              fill=ACCENT + (255,))

    return img.resize((size, size), Image.LANCZOS)


def main():
    dest = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else \
        Path.home() / ".config" / "spiderman"
    dest.mkdir(parents=True, exist_ok=True)
    main_path = dest / "local-asst.png"
    for s in SIZES:
        img = render(s)
        img.save(dest / f"local-asst-{s}.png", "PNG")
        if s == 256:
            img.save(main_path, "PNG")
    print(f"  ✅ logo written to {main_path} (+{len(SIZES)} sizes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
