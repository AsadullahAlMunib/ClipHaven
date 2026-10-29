#!/usr/bin/env python3
"""Generate pixel-faithful Windows .ico and Android PNG icons from logo.svg."""
from pathlib import Path
import math
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SVG_FILE = ROOT / "logo.svg"


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _bg_gradient_color(t: float) -> tuple[int, int, int]:
    """Match logo.svg #bgGrad: 0% #ff5555 -> 50% #a855f7 -> 100% #3b82f6."""
    t = max(0.0, min(1.0, t))
    if t <= 0.5:
        u = t * 2.0
        return (
            int(_lerp(255, 168, u)),
            int(_lerp(85, 85, u)),
            int(_lerp(85, 247, u)),
        )
    u = (t - 0.5) * 2.0
    return (
        int(_lerp(168, 59, u)),
        int(_lerp(85, 130, u)),
        int(_lerp(247, 246, u)),
    )


def _draw_capsule(draw: ImageDraw.ImageDraw, p1: tuple[float, float], p2: tuple[float, float], r: float, fill):
    """Draw a thick line segment between p1 and p2 with round end-caps of radius r."""
    x1, y1 = p1
    x2, y2 = p2
    dx, dy = x2 - x1, y2 - y1
    dist = math.hypot(dx, dy)
    if dist > 0:
        nx, ny = -dy / dist * r, dx / dist * r
        poly = [(x1 + nx, y1 + ny), (x2 + nx, y2 + ny), (x2 - nx, y2 - ny), (x1 - nx, y1 - ny)]
        draw.polygon(poly, fill=fill)
    draw.ellipse([x1 - r, y1 - r, x1 + r, y1 + r], fill=fill)
    draw.ellipse([x2 - r, y2 - r, x2 + r, y2 + r], fill=fill)


def render_logo_master(size: int = 1024) -> Image.Image:
    """Render logo.svg at high resolution (1024x1024) and return an RGBA Image."""
    scale = size / 128.0
    s = lambda v: v * scale

    # 1. Base gradient layer (clipped to rounded rect)
    grad_small = Image.new("RGBA", (256, 256))
    g_px = grad_small.load()
    for y in range(256):
        for x in range(256):
            t = (x + y) / (2.0 * 255.0)
            r, g, b = _bg_gradient_color(t)
            g_px[x, y] = (r, g, b, 255)
    grad_img = grad_small.resize((size, size), Image.Resampling.BICUBIC)

    mask = Image.new("L", (size, size), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle([s(6), s(6), s(122), s(122)], radius=s(30), fill=255)

    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.paste(grad_img, (0, 0), mask)

    # 2. Inner translucent white stroke: rect x=8 y=8 w=112 h=112 rx=28 stroke-width=2 opacity=0.22
    overlay = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    odraw.rounded_rectangle(
        [s(8), s(8), s(120), s(120)],
        radius=s(28),
        outline=(255, 255, 255, int(255 * 0.22)),
        width=max(1, int(round(s(2)))),
    )

    # 3. Clapperboard top accents (fill=#fff, opacity=0.22)
    clap_color = (255, 255, 255, int(255 * 0.22))
    odraw.polygon([(s(36), s(26)), (s(50), s(26)), (s(44), s(36)), (s(30), s(36))], fill=clap_color)
    odraw.polygon([(s(62), s(26)), (s(76), s(26)), (s(70), s(36)), (s(56), s(36))], fill=clap_color)
    clap3 = Image.new("L", (size, size), 0)
    c3_draw = ImageDraw.Draw(clap3)
    c3_draw.polygon([(s(88), s(26)), (s(100), s(26)), (s(106), s(32)), (s(106), s(36)), (s(82), s(36))], fill=255)
    c3_draw.pieslice([s(94), s(26), s(106), s(38)], start=270, end=360, fill=255)
    c3_layer = Image.new("RGBA", (size, size), clap_color)
    overlay.paste(c3_layer, (0, 0), clap3)

    # 4. Play Triangle Merged with Download Arrow (fill=#fff, opacity=0.28)
    play_layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    pdraw = ImageDraw.Draw(play_layer)
    play_color = (255, 255, 255, int(255 * 0.28))
    p1 = (s(48.2), s(37.5))
    p2 = (s(74.6), s(53.3))
    p3 = (s(48.2), s(69.1))
    pr = s(4.2)
    _draw_capsule(pdraw, p1, p2, pr, play_color)
    _draw_capsule(pdraw, p2, p3, pr, play_color)
    _draw_capsule(pdraw, p3, p1, pr, play_color)
    pdraw.polygon([p1, p2, p3], fill=play_color)

    canvas = Image.alpha_composite(canvas, overlay)
    canvas = Image.alpha_composite(canvas, play_layer)

    # 5. Bold Download Arrow with glowGrad (#ffffff -> #e0eaff)
    arrow_mask = Image.new("L", (size, size), 0)
    adraw = ImageDraw.Draw(arrow_mask)
    ar = s(6.0)
    _draw_capsule(adraw, (s(64), s(40)), (s(64), s(86)), ar, 255)
    _draw_capsule(adraw, (s(42), s(64)), (s(64), s(86)), ar, 255)
    _draw_capsule(adraw, (s(86), s(64)), (s(64), s(86)), ar, 255)

    arrow_grad = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ag_draw = ImageDraw.Draw(arrow_grad)
    for y in range(int(s(30)), int(s(95))):
        t = max(0.0, min(1.0, (y - s(34)) / max(1.0, s(58))))
        r = int(_lerp(255, 224, t))
        g = int(_lerp(255, 234, t))
        b = 255
        a = int(_lerp(250, 235, t))
        ag_draw.line([(0, y), (size, y)], fill=(r, g, b, a))

    arrow_layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    arrow_layer.paste(arrow_grad, (0, 0), arrow_mask)
    canvas = Image.alpha_composite(canvas, arrow_layer)

    # 6. Tray / Haven Base Line (fill=#ffffff)
    tray_layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    tdraw = ImageDraw.Draw(tray_layer)
    _draw_capsule(tdraw, (s(42), s(98)), (s(86), s(98)), s(6.0), (255, 255, 255, 255))
    canvas = Image.alpha_composite(canvas, tray_layer)

    return canvas


def generate_all(ico_out: Path | None = None, png_out: Path | None = None):
    master = render_logo_master(1024)
    icon_256 = master.resize((256, 256), Image.Resampling.LANCZOS)

    target_ico = ico_out or (ROOT / "logo.ico")
    icon_256.save(
        target_ico,
        format="ICO",
        sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)],
    )
    if png_out:
        png_out.parent.mkdir(parents=True, exist_ok=True)
        icon_256.save(png_out, format="PNG")

    # Populate Android mipmap icons if android/ directory exists
    android_res = ROOT / "android" / "app" / "src" / "main" / "res"
    if android_res.parent.exists():
        mipmaps = {
            "mipmap-mdpi": 48,
            "mipmap-hdpi": 72,
            "mipmap-xhdpi": 96,
            "mipmap-xxhdpi": 144,
            "mipmap-xxxhdpi": 192,
        }
        for folder, px in mipmaps.items():
            d = android_res / folder
            d.mkdir(parents=True, exist_ok=True)
            resized = master.resize((px, px), Image.Resampling.LANCZOS)
            resized.save(d / "ic_launcher.png", format="PNG")
            resized.save(d / "ic_launcher_round.png", format="PNG")

    return target_ico


if __name__ == "__main__":
    out_ico = generate_all(ico_out=ROOT / "logo.ico")
    print(f"Generated {out_ico}")
