"""scene2d: a tiny data-driven 2D scene engine for the bot's reels.

Architecture follows Overlap2D (github.com/gama88/overlap2d) and its libGDX
runtime, scaled down to Python + Pillow:

    vo.py          scene description as data (SceneVO, LabelVO, ...)
    engine.py      Entity / Engine, and EntityFactory: VO tree -> entities
    components.py  plain state (Transform, Tint, ZIndex, Node, ...)
    scripts.py     behaviour attached to items by name (pop_in, bob, ...)
    systems.py     Script -> Composite -> Render, run every frame
    resources.py   procedural images and fonts, generated once

    scene = SceneVO(...)              # or scene_from_dict(json.load(f))
    render_video(scene, "out.mp4")    # or render_frame(scene, t) for a still
"""

import subprocess

from .engine import Engine, EntityFactory
from .resources import ResourceManager
from .systems import CompositeSystem, RenderSystem, ScriptSystem
from .vo import (CompositeVO, ImageVO, LabelVO, SceneVO, ShapeVO,
                 scene_from_dict, scene_to_dict)

__all__ = ["CompositeVO", "ImageVO", "LabelVO", "SceneVO", "ShapeVO",
           "SceneLoader", "render_frame", "render_video", "scene_from_dict",
           "scene_to_dict"]


class SceneLoader:
    """Builds a live engine from a SceneVO (Overlap2D's SceneLoader)."""

    def __init__(self, scene):
        self.scene = scene
        self.resources = ResourceManager(scene.resources)
        self.engine = Engine()
        EntityFactory(self.engine).create(scene.root)
        self.renderer = RenderSystem(scene, self.resources)
        for system in (ScriptSystem(), CompositeSystem(), self.renderer):
            self.engine.add_system(system)

    def frame_at(self, t):
        self.engine.update(t)
        return self.renderer.frame


def render_frame(scene, t):
    return SceneLoader(scene).frame_at(t)


def render_video(scene, out_path, timeout=900):
    """Encode the scene as H.264 + a silent AAC track (Instagram wants audio)."""
    loader = SceneLoader(scene)
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{scene.width}x{scene.height}", "-r", str(scene.fps), "-i", "-",
           "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
           "-map", "0:v", "-map", "1:a",
           "-c:v", "libx264", "-preset", "medium", "-crf", "20",
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
           "-movflags", "+faststart", str(out_path)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for i in range(round(scene.fps * scene.seconds)):
            frame = loader.frame_at(i / scene.fps)
            proc.stdin.write(frame.convert("RGB").tobytes())
        proc.stdin.close()
        err = proc.stderr.read()
        if proc.wait(timeout=timeout) != 0:
            raise RuntimeError(f"ffmpeg failed: {err.decode(errors='replace')[-500:]}")
    except BaseException:
        proc.kill()
        raise
    return out_path
