"""Components: plain state attached to entities, no behaviour.

Overlap2D's components/ package, trimmed to what a 2D post needs.
"""

from dataclasses import dataclass, field


@dataclass
class MainItemComponent:
    name: str
    item_type: str


@dataclass
class TransformComponent:
    """Base values from the VO, plus the live values scripts write each frame."""
    base_x: float
    base_y: float
    base_sx: float
    base_sy: float
    base_rot: float
    origin: tuple
    x: float = 0.0
    y: float = 0.0
    sx: float = 1.0
    sy: float = 1.0
    rot: float = 0.0

    def reset(self):
        self.x, self.y = self.base_x, self.base_y
        self.sx, self.sy = self.base_sx, self.base_sy
        self.rot = self.base_rot


@dataclass
class TintComponent:
    base_alpha: float
    alpha: float = 1.0


@dataclass
class WorldTransformComponent:
    """Transform after the parent chain is applied (CompositeSystem)."""
    x: float = 0.0
    y: float = 0.0
    sx: float = 1.0
    sy: float = 1.0
    rot: float = 0.0
    alpha: float = 1.0


@dataclass
class ZIndexComponent:
    layer: str
    z: int
    order: int                       # creation order breaks ties


@dataclass
class NodeComponent:
    parent: object = None
    children: list = field(default_factory=list)


@dataclass
class ScriptComponent:
    scripts: list


@dataclass
class DrawableComponent:
    """What to draw. `sprite` is the rendered RGBA image, built once."""
    vo: object
    sprite: object = None
