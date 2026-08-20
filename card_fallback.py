"""Pillow fallback: renders a static branded card (1080x1350, 4:5 portrait).

Used when Blender isn't available or the reel render fails, so the daily
post never silently dies.
"""

from PIL import Image, ImageDraw, ImageFont

import brand

W, H = 1080, 1350
MARGIN = 80
HOOK_TOP = 340
HANDLE_Y = H - 110
CONTENT_BOTTOM = HANDLE_Y - 40      # text must not reach the handle

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


def _split_long_word(draw, word, font, max_width):
    """Break a single word that is wider than the line box."""
    parts, cur = [], ""
    for ch in word:
        if draw.textlength(cur + ch, font=font) <= max_width or not cur:
            cur += ch
        else:
            parts.append(cur)
            cur = ch
    if cur:
        parts.append(cur)
    return parts


def _wrap(draw, text, font, max_width):
    lines, line = [], ""
    for word in text.split():
        # A word wider than the box would otherwise be drawn at negative x
        # and clipped off both edges of the canvas.
        pieces = ([word] if draw.textlength(word, font=font) <= max_width
                  else _split_long_word(draw, word, font, max_width))
        for piece in pieces:
            trial = f"{line} {piece}".strip()
            if draw.textlength(trial, font=font) <= max_width:
                line = trial
            else:
                if line:
                    lines.append(line)
                line = piece
    if line:
        lines.append(line)
    return lines


def _block_height(lines, font, line_gap=1.15):
    return len(lines) * int(font.size * line_gap)


def _draw_lines(draw, lines, font, fill, y, line_gap=1.15):
    line_h = int(font.size * line_gap)
    for ln in lines:
        w = draw.textlength(ln, font=font)
        draw.text(((W - w) / 2, y), ln, font=font, fill=fill)
        y += line_h
    return y


def _layout(draw, hook, punchline):
    """Pick the largest font sizes at which both blocks fit above the handle."""
    hook_size, punch_size = 78, 46
    for _ in range(20):
        hook_font = _font(FONT_CANDIDATES_BOLD, hook_size)
        punch_font = _font(FONT_CANDIDATES_REG, punch_size)
        hook_lines = _wrap(draw, hook, hook_font, W - 2 * MARGIN)
        punch_lines = _wrap(draw, punchline, punch_font, W - 2 * MARGIN - 40)
        bottom = (HOOK_TOP + _block_height(hook_lines, hook_font)
                  + 110 + _block_height(punch_lines, punch_font))
        if bottom <= CONTENT_BOTTOM or hook_size <= 34:
            return hook_font, hook_lines, punch_font, punch_lines
        hook_size = int(hook_size * 0.9)
        punch_size = max(24, int(punch_size * 0.9))
    return hook_font, hook_lines, punch_font, punch_lines


def make_card(hook, punchline, out_path):
    top = _hex(brand.COLORS["bg_top"])
    bottom_c = _hex(brand.COLORS["bg_bottom"])
    text_c = _hex(brand.COLORS["text"])
    accent = _hex(brand.COLORS["accent"])

    img = Image.new("RGB", (W, H))
    for y in range(H):  # vertical gradient
        t = y / H
        row = tuple(int(top[i] + (bottom_c[i] - top[i]) * t) for i in range(3))
        img.paste(Image.new("RGB", (W, 1), row), (0, y))

    draw = ImageDraw.Draw(img)
    handle_font = _font(FONT_CANDIDATES_BOLD, 34)
    hook_font, hook_lines, punch_font, punch_lines = _layout(
        draw, hook.upper(), punchline)

    # accent bar top-left, brand mark
    draw.rectangle([70, 90, 220, 104], fill=accent)
    draw.text((70, 124), brand.BRAND_NAME, font=handle_font, fill=accent)

    y = _draw_lines(draw, hook_lines, hook_font, text_c, HOOK_TOP)
    draw.rectangle([(W - 120) / 2, y + 40, (W + 120) / 2, y + 46], fill=accent)
    _draw_lines(draw, punch_lines, punch_font, text_c, y + 110)

    w = draw.textlength(brand.HANDLE, font=handle_font)
    draw.text(((W - w) / 2, HANDLE_Y), brand.HANDLE, font=handle_font,
              fill=accent)

    img.save(out_path, "JPEG", quality=92)
    return out_path
