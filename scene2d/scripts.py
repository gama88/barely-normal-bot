"""Item scripts: the behaviour attached to items by name.

Overlap2D attaches IScript objects (init/act/dispose) to items. Here a
script is a pure function of time: ScriptSystem resets every transform to
its base each frame and then each script nudges it. That keeps frames
independent, so any single frame can be rendered for a preview.

Scale and alpha are multiplied, position and rotation are added, so
several scripts stack (e.g. slide_in + bob).
"""

import math

from .components import TintComponent, TransformComponent

# ---------------------------------------------------------------- easing ---


def _back_out(p, s=1.70158):
    p -= 1
    return 1 + (s + 1) * p ** 3 + s * p ** 2


EASINGS = {
    "linear": lambda p: p,
    "back_out": _back_out,
    "cubic_out": lambda p: 1 - (1 - p) ** 3,
    "expo_out": lambda p: 1.0 if p >= 1 else 1 - 2 ** (-10 * p),
    "sine_in_out": lambda p: 0.5 - 0.5 * math.cos(math.pi * p),
}


def _progress(t, start, duration):
    if duration <= 0:
        return 1.0 if t >= start else 0.0
    return min(1.0, max(0.0, (t - start) / duration))


def _appear(p):
    """Alpha for an entrance: invisible before it starts, solid quickly."""
    return min(1.0, p * 4)

# -------------------------------------------------------------- registry ---


SCRIPTS = {}


def script(name):
    def register(fn):
        SCRIPTS[name] = fn
        return fn
    return register


class BoundScript:
    def __init__(self, fn, params):
        self.fn, self.params = fn, params

    def act(self, entity, t):
        self.fn(entity.get(TransformComponent), entity.get(TintComponent),
                t, **self.params)


def build(spec):
    spec = dict(spec)
    name = spec.pop("script")
    if name not in SCRIPTS:
        raise ValueError(f"unknown script {name!r}")
    return BoundScript(SCRIPTS[name], spec)

# --------------------------------------------------------------- scripts ---


@script("pop_in")
def pop_in(tr, tint, t, start, duration=0.35):
    p = _progress(t, start, duration)
    s = max(0.001, _back_out(p)) if p > 0 else 0.001
    tr.sx *= s
    tr.sy *= s
    tint.alpha *= _appear(p)


@script("slide_in")
def slide_in(tr, tint, t, start, duration=0.4, dx=0.0, dy=0.0,
             ease="back_out"):
    p = _progress(t, start, duration)
    e = EASINGS[ease](p)
    tr.x += dx * (1 - e)
    tr.y += dy * (1 - e)
    tint.alpha *= _appear(p)


@script("fade_in")
def fade_in(tr, tint, t, start, duration=0.3):
    tint.alpha *= _progress(t, start, duration)


@script("grow_x")
def grow_x(tr, tint, t, start, duration=0.3, ease="expo_out"):
    p = _progress(t, start, duration)
    tr.sx *= max(0.001, EASINGS[ease](p))
    tint.alpha *= 1.0 if p > 0 else 0.0


@script("progress")
def progress(tr, tint, t, start=0.0, end=1.0):
    tr.sx *= max(0.001, _progress(t, start, end - start))


@script("pulse")
def pulse(tr, tint, t, at, duration=0.3, amount=0.08):
    for beat in at:
        q = _progress(t, beat, duration)
        if 0 < q < 1:
            s = 1 + amount * math.sin(math.pi * q)
            tr.sx *= s
            tr.sy *= s


@script("wobble")
def wobble(tr, tint, t, start=0.0, amplitude=8.0, period=1.3):
    if t > start:
        tr.rot += amplitude * math.sin(2 * math.pi * (t - start) / period)


@script("bob")
def bob(tr, tint, t, dx=0.0, dy=10.0, period=3.0, phase=0.0):
    w = math.sin(2 * math.pi * (t / period + phase))
    tr.x += dx * w
    tr.y += dy * w


@script("drift")
def drift(tr, tint, t, vx=0.0, vy=0.0):
    tr.x += vx * t
    tr.y += vy * t


@script("spin")
def spin(tr, tint, t, speed=20.0):
    tr.rot += speed * t


@script("breathe")
def breathe(tr, tint, t, low=0.6, high=1.0, period=2.0):
    tint.alpha *= low + (high - low) * (0.5 - 0.5 * math.cos(2 * math.pi * t / period))
