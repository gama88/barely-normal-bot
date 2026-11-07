"""Systems: all per-frame behaviour, run in order by the Engine.

  ScriptSystem    -> reset transforms to base, run item scripts
  CompositeSystem -> push parent transforms down the tree
  RenderSystem    -> draw by layer then z-index, one drawable logic per
                     item type (Overlap2D's DrawableLogicMapper)
"""

import math

from PIL import Image, ImageDraw, ImageFilter

from .components import (DrawableComponent, NodeComponent, ScriptComponent,
                         TintComponent, TransformComponent,
                         WorldTransformComponent, ZIndexComponent)

SUPERSAMPLE = 3          # Pillow shapes have no anti-aliasing; draw big, shrink


class ScriptSystem:
    def update(self, engine, t):
        for e in engine.family(TransformComponent, TintComponent):
            e.get(TransformComponent).reset()
            tint = e.get(TintComponent)
            tint.alpha = tint.base_alpha
            scripts = e.get(ScriptComponent)
            if scripts:
                for s in scripts.scripts:
                    s.act(e, t)


class CompositeSystem:
    def update(self, engine, t):
        for e in engine.entities:
            if e.get(NodeComponent).parent is None:
                self._apply(e, None)

    def _apply(self, e, parent_world):
        tr, tint = e.get(TransformComponent), e.get(TintComponent)
        world = e.get(WorldTransformComponent)
        if parent_world is None:
            world.x, world.y = tr.x, tr.y
            world.sx, world.sy, world.rot = tr.sx, tr.sy, tr.rot
            world.alpha = tint.alpha
        else:
            # Child offset is scaled, then rotated, by the parent.
            ox, oy = tr.x * parent_world.sx, tr.y * parent_world.sy
            a = math.radians(-parent_world.rot)   # y-down: CCW is negative
            world.x = parent_world.x + ox * math.cos(a) - oy * math.sin(a)
            world.y = parent_world.y + ox * math.sin(a) + oy * math.cos(a)
            world.sx = tr.sx * parent_world.sx
            world.sy = tr.sy * parent_world.sy
            world.rot = tr.rot + parent_world.rot
            world.alpha = tint.alpha * parent_world.alpha
        for child in e.get(NodeComponent).children:
            self._apply(child, world)

# -------------------------------------------------------- drawable logic ---


def _with_glow(sprite, radius, color):
    """Put a blurred, coloured copy of the sprite's shape underneath it."""
    if radius <= 0 or color is None:
        return sprite
    alpha = sprite.getchannel("A").filter(ImageFilter.GaussianBlur(radius))
    strength = color[3] / 255 if len(color) > 3 else 0.6
    alpha = alpha.point(lambda v: int(min(255, v * strength * 1.6)))
    glow = Image.new("RGBA", sprite.size, tuple(color[:3]) + (0,))
    glow.putalpha(alpha)
    glow.alpha_composite(sprite)
    return glow


def draw_label(vo, resources):
    font = resources.font(vo.font, vo.size)
    pad = int(vo.glow * 2.5) + 4
    width = math.ceil(font.getlength(vo.text)) + 2 * pad
    height = math.ceil(vo.size * 1.3) + 2 * pad
    # Centre the sprite on the capital letters (not the em box), so a line
    # placed at y sits visually centred on y.
    cap = -font.getbbox("H", anchor="ls")[1]
    sprite = Image.new("RGBA", (width, height), tuple(vo.color[:3]) + (0,))
    ImageDraw.Draw(sprite).text((pad, height / 2 + cap / 2), vo.text,
                                font=font, fill=tuple(vo.color), anchor="ls")
    return _with_glow(sprite, vo.glow, vo.glow_color)


def draw_shape(vo, resources):
    k = SUPERSAMPLE
    pad = int(vo.glow * 2.5) + 2
    w, h = max(1, round(vo.width)), max(1, round(vo.height))
    big = Image.new("RGBA", ((w + 2 * pad) * k, (h + 2 * pad) * k), (0, 0, 0, 0))
    draw = ImageDraw.Draw(big)
    box = (pad * k, pad * k, (pad + w) * k - 1, (pad + h) * k - 1)
    fill = tuple(vo.fill) if vo.fill else None
    outline = tuple(vo.outline) if vo.outline else None
    line = round(vo.outline_width * k)
    if vo.shape == "rect":
        draw.rounded_rectangle(box, radius=vo.radius * k, fill=fill,
                               outline=outline, width=line)
    elif vo.shape == "ellipse":
        draw.ellipse(box, fill=fill, outline=outline, width=line)
    elif vo.shape == "ring":
        draw.ellipse(box, outline=outline or fill, width=line or k * 8)
    elif vo.shape == "diamond":
        x0, y0, x1, y1 = box
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        draw.polygon([(cx, y0), (x1, cy), (cx, y1), (x0, cy)], fill=fill,
                     outline=outline)
    elif vo.shape == "polygon":
        x0, y0, x1, y1 = box
        pts = [(x0 + px * (x1 - x0), y0 + py * (y1 - y0)) for px, py in vo.points]
        draw.polygon(pts, fill=fill, outline=outline, width=line or 1)
    elif vo.shape == "arc":
        draw.arc(box, vo.start_angle, vo.end_angle, fill=outline or fill,
                 width=line or k * 8)
    else:
        raise ValueError(f"unknown shape {vo.shape!r}")
    sprite = big.resize((w + 2 * pad, h + 2 * pad), Image.LANCZOS)
    glow_color = vo.glow_color or vo.fill or vo.outline
    return _with_glow(sprite, vo.glow, glow_color and tuple(glow_color))


def draw_image(vo, resources):
    return resources.image(vo.image)


DRAWABLE_LOGIC = {"label": draw_label, "shape": draw_shape, "image": draw_image}

# --------------------------------------------------------------- render ---


def _alpha_lut(alpha):
    return [int(v * alpha) for v in range(256)]


def paste_clipped(frame, img, x, y):
    """alpha_composite that tolerates sprites hanging off the frame."""
    fw, fh = frame.size
    w, h = img.size
    left, top = max(0, -x), max(0, -y)
    right, bottom = min(w, fw - x), min(h, fh - y)
    if right <= left or bottom <= top:
        return
    if (left, top, right, bottom) != (0, 0, w, h):
        img = img.crop((left, top, right, bottom))
    frame.alpha_composite(img, dest=(x + left, y + top))


class RenderSystem:
    def __init__(self, scene, resources):
        self.scene = scene
        self.resources = resources
        self.frame = None
        self._ordered = None

    def update(self, engine, t):
        if self._ordered is None:
            layers = {name: i for i, name in enumerate(self.scene.layers)}

            def key(e):
                z = e.get(ZIndexComponent)
                return (layers.get(z.layer, len(layers)), z.z, z.order)
            self._ordered = sorted(engine.family(DrawableComponent), key=key)

        frame = Image.new("RGBA", (self.scene.width, self.scene.height),
                          tuple(self.scene.background))
        for e in self._ordered:
            self._draw(frame, e)
        self.frame = frame

    def _draw(self, frame, e):
        world = e.get(WorldTransformComponent)
        if world.alpha <= 0.004:
            return
        drawable = e.get(DrawableComponent)
        if drawable.sprite is None:
            drawable.sprite = DRAWABLE_LOGIC[drawable.vo.TYPE](drawable.vo,
                                                               self.resources)
        img = drawable.sprite
        w, h = img.size
        sw, sh = round(w * abs(world.sx)), round(h * abs(world.sy))
        if sw < 1 or sh < 1:
            return
        if (sw, sh) != (w, h):
            img = img.resize((sw, sh), Image.BILINEAR)
        # Offset from the sprite's centre to its origin, before rotation.
        ox, oy = e.get(TransformComponent).origin
        dx, dy = (ox - 0.5) * sw, (oy - 0.5) * sh
        if abs(world.rot) > 0.05:
            img = img.rotate(world.rot, resample=Image.BICUBIC, expand=True)
            a = math.radians(-world.rot)
            dx, dy = (dx * math.cos(a) - dy * math.sin(a),
                      dx * math.sin(a) + dy * math.cos(a))
        if world.alpha < 0.996:
            img = img.copy()
            img.putalpha(img.getchannel("A").point(_alpha_lut(world.alpha)))
        cx, cy = world.x - dx, world.y - dy
        paste_clipped(frame, img, round(cx - img.width / 2),
                      round(cy - img.height / 2))
