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


def _bounce_out(p):
    n, d = 7.5625, 2.75
    if p < 1 / d:
        return n * p * p
    if p < 2 / d:
        p -= 1.5 / d
        return n * p * p + 0.75
    if p < 2.5 / d:
        p -= 2.25 / d
        return n * p * p + 0.9375
    p -= 2.625 / d
    return n * p * p + 0.984375


EASINGS = {
    "linear": lambda p: p,
    "back_out": _back_out,
    "cubic_out": lambda p: 1 - (1 - p) ** 3,
    "expo_out": lambda p: 1.0 if p >= 1 else 1 - 2 ** (-10 * p),
    "sine_in_out": lambda p: 0.5 - 0.5 * math.cos(math.pi * p),
    "bounce_out": _bounce_out,
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
def wobble(tr, tint, t, start=0.0, amplitude=8.0, period=1.3, phase=0.0):
    if t > start:
        tr.rot += amplitude * math.sin(2 * math.pi * ((t - start) / period + phase))


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


# Looping motion for the illustrations (visuals.py). `phase` is a fraction
# of the period, so copies of one item can run out of step.


def _loop(t, period, phase=0.0, start=0.0):
    return ((max(0.0, t - start) / period) + phase) % 1.0


ADDITIVE = {"x", "y", "rot"}


@script("keys")
def keys(tr, tint, t, prop, keys, ease="sine_in_out", period=0.0, start=0.0):
    """Keyframes [[time, value], ...]. x/y/rot add; sx/sy/scale/alpha multiply."""
    local = max(0.0, t - start)
    if period:
        local %= period
    value = keys[-1][1]
    if local <= keys[0][0]:
        value = keys[0][1]
    else:
        for (t0, v0), (t1, v1) in zip(keys, keys[1:]):
            if t0 <= local <= t1:
                p = EASINGS[ease]((local - t0) / (t1 - t0)) if t1 > t0 else 1.0
                value = v0 + (v1 - v0) * p
                break
    if prop in ADDITIVE:
        setattr(tr, prop, getattr(tr, prop) + value)
    elif prop == "alpha":
        tint.alpha *= value
    elif prop == "scale":
        tr.sx *= value
        tr.sy *= value
    else:
        setattr(tr, prop, getattr(tr, prop) * value)


@script("arc_path")
def arc_path(tr, tint, t, start, duration, x1, y1, height, period=0.0,
             drop=0.0):
    """Thrown-object flight from the base position to base + (x1, y1),
    peaking `height` px up; then optionally falls (`drop` px/s^2).
    With a period it repeats, fading out just before each restart."""
    local = t - start
    if period:
        local = local % period if local >= 0 else local
    if local < 0:
        tint.alpha = 0.0
        return
    p = min(1.0, local / duration)
    tr.x += x1 * p
    tr.y += y1 * p - 4 * height * p * (1 - p)
    if local > duration and drop:
        tr.y += 0.5 * drop * (local - duration) ** 2
    tint.alpha *= min(1.0, local / 0.08)
    if period:
        tint.alpha *= min(1.0, max(0.0, (period - local) / 0.3))


@script("rise_loop")
def rise_loop(tr, tint, t, distance=300.0, period=2.0, phase=0.0, sway=0.0):
    q = _loop(t, period, phase)
    tr.y -= distance * q
    tr.x += sway * math.sin(2 * math.pi * q * 2)
    tint.alpha *= math.sin(math.pi * q)


@script("fall_loop")
def fall_loop(tr, tint, t, distance=600.0, period=2.0, phase=0.0):
    q = _loop(t, period, phase)
    tr.y += distance * q
    tint.alpha *= min(1.0, q * 8, (1 - q) * 8)


@script("pump")
def pump(tr, tint, t, low=0.8, high=1.0, period=1.0, phase=0.0, axis="both"):
    s = low + (high - low) * (0.5 - 0.5 * math.cos(2 * math.pi * _loop(t, period, phase)))
    if axis in ("both", "x"):
        tr.sx *= s
    if axis in ("both", "y"):
        tr.sy *= s


@script("flicker")
def flicker(tr, tint, t, period=0.2, duty=0.5, low=0.0, phase=0.0):
    if _loop(t, period, phase) > duty:
        tint.alpha *= low


@script("expand_loop")
def expand_loop(tr, tint, t, period=1.6, start_scale=0.4, end_scale=1.6,
                phase=0.0):
    q = _loop(t, period, phase)
    s = start_scale + (end_scale - start_scale) * q
    tr.sx *= s
    tr.sy *= s
    tint.alpha *= 1 - q
