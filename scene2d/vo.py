"""Scene value objects: the data half of the engine.

Mirrors Overlap2D's `data/` package (MainItemVO, LabelVO, CompositeItemVO,
SceneVO): a scene is plain data that round-trips through JSON, and nothing
in here knows how to draw. engine.EntityFactory turns it into entities.

Coordinates are pixels with y pointing DOWN (Pillow's convention, unlike
Overlap2D/libGDX's y-up). (x, y) is where the item's origin sits in its
parent's space; `origin` is a fraction of the item's own size, so
(0.5, 0.5) is the centre and (0, 0.5) the middle of the left edge.
"""

from dataclasses import dataclass, field, fields


@dataclass
class ItemVO:
    TYPE = "item"

    name: str = ""
    x: float = 0.0
    y: float = 0.0
    scale_x: float = 1.0
    scale_y: float = 1.0
    rotation: float = 0.0            # degrees, counter-clockwise
    alpha: float = 1.0
    origin: tuple = (0.5, 0.5)
    z_index: int = 0
    layer: str = ""                  # "" = inherit the parent's layer
    # Behaviour, attached by name like Overlap2D's commonScripts:
    # [{"script": "pop_in", "start": 0.2, "duration": 0.35}, ...]
    scripts: list = field(default_factory=list)


@dataclass
class LabelVO(ItemVO):
    TYPE = "label"

    text: str = ""
    font: str = ""                   # path to a .ttf; "" = Pillow's default
    size: int = 48
    color: tuple = (255, 255, 255, 255)
    glow: float = 0.0                # blur radius in px; 0 = none
    glow_color: tuple = (255, 255, 255, 110)


@dataclass
class ShapeVO(ItemVO):
    TYPE = "shape"

    shape: str = "rect"              # rect | ellipse | ring | diamond | polygon | arc
    width: float = 100.0
    height: float = 100.0
    radius: float = 0.0              # corner radius (rect)
    fill: tuple = None
    outline: tuple = None
    outline_width: float = 0.0
    glow: float = 0.0
    glow_color: tuple = None         # defaults to fill/outline colour
    points: list = None              # polygon: [(x, y), ...] as fractions of the box
    start_angle: float = 0.0         # arc: degrees clockwise from 3 o'clock
    end_angle: float = 360.0


@dataclass
class ImageVO(ItemVO):
    TYPE = "image"

    image: str = ""                  # name of an entry in SceneVO.resources


@dataclass
class CompositeVO(ItemVO):
    TYPE = "composite"

    items: list = field(default_factory=list)


@dataclass
class SceneVO:
    width: int = 1080
    height: int = 1920
    fps: int = 30
    seconds: float = 7.0
    background: tuple = (0, 0, 0, 255)
    layers: list = field(default_factory=lambda: ["background", "content", "ui"])
    # Procedural images, generated once at load: {name: {"kind": ..., ...}}
    resources: dict = field(default_factory=dict)
    root: CompositeVO = field(default_factory=CompositeVO)


ITEM_TYPES = {cls.TYPE: cls for cls in (LabelVO, ShapeVO, ImageVO, CompositeVO)}


# ------------------------------------------------------------------ JSON ---


def item_to_dict(vo):
    data = {"type": vo.TYPE}
    for f in fields(vo):
        value = getattr(vo, f.name)
        if f.name == "items":
            value = [item_to_dict(child) for child in value]
        data[f.name] = value
    return data


def item_from_dict(data):
    data = dict(data)
    cls = ITEM_TYPES[data.pop("type")]
    if "items" in data:
        data["items"] = [item_from_dict(child) for child in data["items"]]
    # JSON turns tuples into lists; Pillow wants tuples for colours.
    for key, value in data.items():
        if key == "points" and value is not None:
            data[key] = [tuple(pt) for pt in value]
        elif isinstance(value, list) and key not in ("items", "scripts"):
            data[key] = tuple(value)
    return cls(**data)


def scene_to_dict(scene):
    data = {f.name: getattr(scene, f.name) for f in fields(scene)}
    data["root"] = item_to_dict(scene.root)
    return data


def scene_from_dict(data):
    data = dict(data)
    data["root"] = item_from_dict(data["root"])
    data["background"] = tuple(data["background"])
    return SceneVO(**data)
