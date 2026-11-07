"""Entities, the engine, and the factory that builds them from scene data.

Same split as Overlap2D's runtime (which sits on Ashley's ECS):
  - components are dumb state (TransformComponent, TintComponent, ...);
  - EntityFactory walks the VO tree and asks a per-type component factory
    to attach the type-specific parts (LabelComponentFactory, ...);
  - systems.py holds all behaviour and runs over the entities each frame.
"""

import itertools

from . import scripts as script_registry
from .components import (DrawableComponent, MainItemComponent,
                         NodeComponent, ScriptComponent, TintComponent,
                         TransformComponent, WorldTransformComponent,
                         ZIndexComponent)
from .vo import CompositeVO, ImageVO, LabelVO, ShapeVO

# ---------------------------------------------------------------- entity ---


class Entity:
    _ids = itertools.count()

    def __init__(self):
        self.id = next(Entity._ids)
        self.components = {}

    def add(self, component):
        self.components[type(component)] = component
        return component

    def get(self, cls):
        return self.components.get(cls)


class Engine:
    def __init__(self):
        self.entities = []
        self.systems = []

    def add_entity(self, entity):
        self.entities.append(entity)

    def add_system(self, system):
        self.systems.append(system)

    def family(self, *component_types):
        for e in self.entities:
            if all(t in e.components for t in component_types):
                yield e

    def update(self, t):
        for system in self.systems:
            system.update(self, t)

# -------------------------------------------------------------- factories ---


def _drawable(entity, vo):
    entity.add(DrawableComponent(vo))


# One factory per item type, like Overlap2D's ComponentFactory subclasses.
# Composites get no drawable; their children are built by EntityFactory.
COMPONENT_FACTORIES = {
    LabelVO: _drawable,
    ShapeVO: _drawable,
    ImageVO: _drawable,
    CompositeVO: lambda entity, vo: None,
}


class EntityFactory:
    def __init__(self, engine):
        self.engine = engine
        self._order = itertools.count()

    def create(self, vo, parent=None, layer="content"):
        layer = vo.layer or layer
        e = Entity()
        e.add(MainItemComponent(vo.name, vo.TYPE))
        e.add(TransformComponent(vo.x, vo.y, vo.scale_x, vo.scale_y,
                                 vo.rotation, tuple(vo.origin)))
        e.add(TintComponent(vo.alpha))
        e.add(WorldTransformComponent())
        e.add(ZIndexComponent(layer, vo.z_index, next(self._order)))
        e.add(NodeComponent(parent=parent))
        if vo.scripts:
            e.add(ScriptComponent([script_registry.build(spec)
                                   for spec in vo.scripts]))
        COMPONENT_FACTORIES[type(vo)](e, vo)
        if parent is not None:
            parent.get(NodeComponent).children.append(e)
        self.engine.add_entity(e)
        if isinstance(vo, CompositeVO):
            for child in vo.items:
                self.create(child, parent=e, layer=layer)
        return e
