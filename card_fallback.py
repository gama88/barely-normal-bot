"""Pillow fallback: renders a static branded card (1080x1350, 4:5 portrait).

Used when Blender isn't available or the reel render fails, so the daily
post never silently dies.
"""

from PIL import Image, ImageDraw, ImageFont

import brand

W, H = 1080, 1350

FONT_CANDIDATES_BOLD = [
    r"C:\Windows\Fonts\arialbd.ttf",
    r"C:\Windows\Fonts\impact.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]
FONT_CANDIDATES_REG = [
    r"C:\Windows\Fonts\arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def _hex(c):
    h = c.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _font(candidates, size):
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def _wrap(draw, text, font, max_width):
    words, lines, line = text.split(), [], ""
    for w in words:
        trial = f"{line} {w}".strip()
        if draw.textlength(trial, font=font) <= max_width:
            line = trial
        else:
            if line:
                lines.append(line)
            line = w
    if line:
        lines.append(line)
    return lines


def _draw_block(draw, text, font, fill, y, max_width, line_gap=1.15):
    lines = _wrap(draw, text, font, max_width)
    line_h = int(font.size * line_gap)
    for ln in lines:
        w = draw.textlength(ln, font=font)
        draw.text(((W - w) / 2, y), ln, font=font, fill=fill)
        y += line_h
    return y


def make_card(hook, punchline, out_path):
    top = _hex(brand.COLORS["bg_top"])
    bottom = _hex(brand.COLORS["bg_bottom"])
    text_c = _hex(brand.COLORS["text"])
    accent = _hex(brand.COLORS["accent"])

    img = Image.new("RGB", (W, H))
    for y in range(H):  # vertical gradient
        t = y / H
        row = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        img.paste(Image.new("RGB", (W, 1), row), (0, y))

    draw = ImageDraw.Draw(img)
    hook_font = _font(FONT_CANDIDATES_BOLD, 78)
    punch_font = _font(FONT_CANDIDATES_REG, 46)
    handle_font = _font(FONT_CANDIDATES_BOLD, 34)

    # accent bar top-left, brand mark
    draw.rectangle([70, 90, 220, 104], fill=accent)
    draw.text((70, 124), brand.BRAND_NAME, font=handle_font, fill=accent)

    y = _draw_block(draw, hook.upper(), hook_font, text_c, 340, W - 160)
    draw.rectangle([(W - 120) / 2, y + 40, (W + 120) / 2, y + 46], fill=accent)
    _draw_block(draw, punchline, punch_font, text_c, y + 110, W - 200)

    w = draw.textlength(brand.HANDLE, font=handle_font)
    draw.text(((W - w) / 2, H - 110), brand.HANDLE, font=handle_font, fill=accent)

    img.save(out_path, "JPEG", quality=92)
    return out_path
