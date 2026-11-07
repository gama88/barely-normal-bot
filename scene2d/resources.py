"""Resource manager: images and fonts, loaded once and shared.

Overlap2D's ResourceManager loads atlases and fonts from the project; here
images are procedural (described in SceneVO.resources, so the scene JSON
stays self-contained) and generated on first use.
"""

from PIL import Image, ImageDraw, ImageFilter, ImageFont


def _gradient(width, height, top, bottom):
    mask = Image.linear_gradient("L").resize((width, height))  # 0 top -> 255 bottom
    return Image.composite(Image.new("RGBA", (width, height), tuple(bottom)),
                           Image.new("RGBA", (width, height), tuple(top)), mask)


def _glow(diameter, color, blur):
    """Soft coloured disc: the building block for blobs and spotlights."""
    pad = int(blur * 2.5)
    size = diameter + 2 * pad
    alpha = Image.new("L", (size, size), 0)
    ImageDraw.Draw(alpha).ellipse((pad, pad, pad + diameter, pad + diameter),
                                  fill=int(255 * (color[3] / 255 if len(color) > 3 else 1)))
    alpha = alpha.filter(ImageFilter.GaussianBlur(blur))
    img = Image.new("RGBA", (size, size), tuple(color[:3]) + (0,))
    img.putalpha(alpha)
    return img


def _grid(width, height, spacing, color, line, fade_top=0.15):
    """Line grid, brightest at the bottom and fading out towards the top."""
    img = Image.new("RGBA", (width, height), tuple(color[:3]) + (0,))
    lines = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(lines)
    for x in range(0, width + spacing, spacing):
        draw.rectangle((x - line // 2, 0, x + (line - 1) // 2, height), fill=255)
    for y in range(0, height + spacing, spacing):
        draw.rectangle((0, y - line // 2, width, y + (line - 1) // 2), fill=255)
    lines = lines.filter(ImageFilter.GaussianBlur(line * 0.6))
    fade = Image.linear_gradient("L").resize((width, height))
    fade = fade.point(lambda v: int(color[3] * max(fade_top, v / 255)))
    alpha = Image.new("L", (width, height), 0)
    alpha.paste(fade, mask=lines)
    img.putalpha(alpha)
    return img


GENERATORS = {
    "gradient": lambda spec: _gradient(spec["width"], spec["height"],
                                       spec["top"], spec["bottom"]),
    "glow": lambda spec: _glow(spec["diameter"], spec["color"], spec["blur"]),
    "grid": lambda spec: _grid(spec["width"], spec["height"], spec["spacing"],
                               spec["color"], spec["line"],
                               spec.get("fade_top", 0.15)),
}


class ResourceManager:
    def __init__(self, specs):
        self.specs = specs
        self._images = {}
        self._fonts = {}

    def image(self, name):
        if name not in self._images:
            spec = self.specs[name]
            self._images[name] = GENERATORS[spec["kind"]](spec)
        return self._images[name]

    def font(self, path, size):
        key = (path, int(size))
        if key not in self._fonts:
            self._fonts[key] = load_font(path, size)
        return self._fonts[key]


def load_font(path, size):
    if path:
        try:
            return ImageFont.truetype(path, int(size))
        except OSError:
            pass
    try:
        return ImageFont.load_default(int(size))      # Pillow >= 10.1
    except TypeError:
        return ImageFont.load_default()
