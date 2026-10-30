"""Blender scene script — renders a vertical branded reel for one post.

Runs INSIDE Blender's Python, headless:
    blender -b --factory-startup -P blender_scene.py -- /path/to/config.json

The config JSON carries the text, colors, and output path (written by bot.py).
The whole scene is built procedurally so no .blend file needs to live in git.

Framing note (this bit is easy to get wrong):
Blender's `ortho_scale` sizes the axis chosen by `sensor_fit`. With the default
'AUTO' and a PORTRAIT render (1080x1920), AUTO resolves to VERTICAL, so
ortho_scale would become the frame HEIGHT and the frame would be only
0.5625 * ortho_scale wide. We force sensor_fit='HORIZONTAL' so ortho_scale is
the WIDTH, which is what every coordinate below is designed against:
    width  = ortho_scale                      = 10.0
    height = ortho_scale * (1920/1080)        = 17.78
    so x in [-5.0, +5.0], z in [-8.89, +8.89]
Instagram overlays its UI over roughly the bottom 20% and top 10% of a Reel,
so all content is kept inside z in [-5.3, +7.1].
"""

import json
import math
import os
import random
import sys

import bpy

# Approximate glyph advance as a fraction of font size, used to predict
# wrapping so text can be auto-shrunk to fit its vertical budget.
ADVANCE_UPPER = 0.70
ADVANCE_MIXED = 0.55
MIN_TEXT_SIZE = 0.28


def hex_to_rgba(hex_color, alpha=1.0):
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    # sRGB -> linear. Only correct if the view transform is 'Standard',
    # which main() sets below (Blender 4.x defaults to AgX, which would
    # desaturate the brand palette).
    lin = [c ** 2.2 for c in (r, g, b)]
    return (*lin, alpha)


def load_config():
    argv = sys.argv
    cfg_path = argv[argv.index("--") + 1]
    with open(cfg_path, "r", encoding="utf-8") as f:
        return json.load(f)


def pick_font(candidates):
    for path in candidates:
        if os.path.exists(path):
            try:
                return bpy.data.fonts.load(path)
            except Exception:
                continue
    return None  # Blender's built-in font


def fit_size(text, base_size, box_width, budget_height, upper):
    """Shrink font size until the wrapped block fits its vertical budget.

    Blender text boxes wrap but never scale glyphs, so without this a long
    hook silently grows downward through the punchline below it.
    """
    if not text:
        return base_size
    advance = ADVANCE_UPPER if upper else ADVANCE_MIXED
    size = base_size
    for _ in range(12):
        chars_per_line = max(1, int(box_width / (size * advance)))
        lines = max(1, math.ceil(len(text) / chars_per_line))
        height = lines * size          # space_line defaults to 1.0
        if height <= budget_height or size <= MIN_TEXT_SIZE:
            break
        size = max(MIN_TEXT_SIZE, size * math.sqrt(budget_height / height))
    return size


def make_emission_material(name, rgba, strength):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        if "Base Color" in bsdf.inputs:
            bsdf.inputs["Base Color"].default_value = rgba
        if "Emission Color" in bsdf.inputs:
            bsdf.inputs["Emission Color"].default_value = rgba
        if "Emission Strength" in bsdf.inputs:
            bsdf.inputs["Emission Strength"].default_value = strength
    return mat


def add_text(name, body, size, z, width, font, material,
             extrude=0.05, upper=False):
    curve = bpy.data.curves.new(name, type="FONT")
    curve.body = body.upper() if upper else body
    curve.size = size
    curve.extrude = extrude
    curve.bevel_depth = extrude * 0.15
    curve.align_x = "CENTER"
    curve.align_y = "TOP"
    if font:
        curve.font = font
    tb = curve.text_boxes[0]
    tb.width = width
    tb.x = -width / 2
    curve.materials.append(material)
    obj = bpy.data.objects.new(name, curve)
    obj.location = (0, 0, z)
    # Font curves are built lying flat in the XY plane. The camera looks
    # along +Y, so without this the text is seen edge-on and renders as thin
    # horizontal bars. Rotating +90 deg about X stands it up in the XZ plane,
    # facing the camera, with text flowing downward in -Z.
    obj.rotation_euler = (math.pi / 2, 0, 0)
    bpy.context.collection.objects.link(obj)
    return obj


def scale_in(obj, start_frame, end_frame):
    obj.scale = (0.001, 0.001, 0.001)
    obj.keyframe_insert("scale", frame=start_frame)
    obj.scale = (1.0, 1.0, 1.0)
    obj.keyframe_insert("scale", frame=end_frame)


def main():
    cfg = load_config()
    random.seed(cfg.get("seed", 7))

    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene

    # --- render engine (names drift across Blender versions) ---
    for engine in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "BLENDER_WORKBENCH"):
        try:
            scene.render.engine = engine
            break
        except TypeError:
            continue
    try:
        # CI runners have no GPU, so EEVEE runs on Mesa's software rasterizer
        # and cost scales with samples. 16 took ~45 min for 210 frames; flat
        # emissive text on a dark background looks the same at 4.
        scene.eevee.taa_render_samples = 4
    except Exception:
        pass

    # Blender 4.x defaults to the AgX view transform, which desaturates the
    # neon brand colors into near-white. 'Standard' is the true inverse of
    # the sRGB->linear conversion in hex_to_rgba, so hex values land exactly.
    try:
        scene.view_settings.view_transform = "Standard"
        scene.view_settings.look = "None"
    except Exception as exc:
        print(f"view transform not set: {exc}")

    fps = cfg["fps"]
    total = fps * cfg["seconds"]
    scene.render.resolution_x = cfg["width"]
    scene.render.resolution_y = cfg["height"]
    scene.render.fps = fps
    scene.frame_start = 1
    scene.frame_end = total

    colors = cfg["colors"]
    text_rgba = hex_to_rgba(colors["text"])
    accent_rgba = hex_to_rgba(colors["accent"])
    accent2_rgba = hex_to_rgba(colors["accent2"])

    # --- world ---
    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = hex_to_rgba(colors["bg_bottom"])
    scene.world = world

    # --- camera: orthographic for deterministic framing ---
    cam_data = bpy.data.cameras.new("Cam")
    cam_data.type = "ORTHO"
    # MUST be HORIZONTAL — see the framing note at the top of this file.
    cam_data.sensor_fit = "HORIZONTAL"
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (0, -10, 0)
    cam.rotation_euler = (math.pi / 2, 0, 0)
    bpy.context.collection.objects.link(cam)
    scene.camera = cam
    cam_data.ortho_scale = 10.7          # frame width at start
    cam_data.keyframe_insert("ortho_scale", frame=1)
    cam_data.ortho_scale = 10.0          # slow zoom-in over the whole clip
    cam_data.keyframe_insert("ortho_scale", frame=total)

    # --- lights ---
    key = bpy.data.lights.new("Key", type="AREA")
    key.energy = 900
    key.size = 12
    key_obj = bpy.data.objects.new("Key", key)
    key_obj.location = (0, -6, 4)
    key_obj.rotation_euler = (math.pi / 2.4, 0, 0)
    bpy.context.collection.objects.link(key_obj)

    rim = bpy.data.lights.new("Rim", type="POINT")
    rim.energy = 400
    rim.color = accent_rgba[:3]
    rim_obj = bpy.data.objects.new("Rim", rim)
    rim_obj.location = (3, 1, -2)
    bpy.context.collection.objects.link(rim_obj)

    # --- materials ---
    font = pick_font(cfg.get("font_candidates", []))
    text_mat = make_emission_material("Text", text_rgba, 0.35)
    accent_mat = make_emission_material("Accent", accent_rgba, 4.0)
    accent2_mat = make_emission_material("Accent2", accent2_rgba, 4.0)

    # --- text ---
    # Safe zone is z in [-5.3, +7.1]. Hook is top-anchored at 5.5 and may grow
    # down to 0.5 (budget 5.0); punchline top-anchored at -0.8, budget 3.0.
    hook_w, punch_w = 8.4, 8.0
    hook_size = fit_size(cfg["hook"], 0.90, hook_w, 5.0, upper=True)
    punch_size = fit_size(cfg["punchline"], 0.50, punch_w, 3.0, upper=False)

    hook = add_text("Hook", cfg["hook"], size=hook_size, z=5.5, width=hook_w,
                    font=font, material=text_mat, extrude=0.07, upper=True)
    punch = add_text("Punch", cfg["punchline"], size=punch_size, z=-0.8,
                     width=punch_w, font=font, material=text_mat, extrude=0.03)
    add_text("Handle", cfg["handle"], size=0.38, z=-4.6, width=9.5,
             font=font, material=accent_mat, extrude=0.01)

    scale_in(hook, 1, int(fps * 0.55))
    scale_in(punch, int(fps * 1.1), int(fps * 1.7))

    # --- floating emissive shapes behind the text ---
    for i in range(9):
        kind = random.choice(("ico", "cube", "torus"))
        # Keep the centre column clear: text boxes are up to 8.4 units wide
        # (x in [-4.2, 4.2]), so shapes live out at the frame edges instead of
        # glowing through the copy.
        x = random.choice((-1, 1)) * random.uniform(3.6, 5.2)
        z = random.uniform(-8, 8)
        y = random.uniform(3.5, 6.5)     # well behind the text plane
        s = random.uniform(0.15, 0.5)
        if kind == "ico":
            bpy.ops.mesh.primitive_ico_sphere_add(radius=s, location=(x, y, z))
        elif kind == "cube":
            bpy.ops.mesh.primitive_cube_add(size=s * 1.6, location=(x, y, z))
        else:
            bpy.ops.mesh.primitive_torus_add(
                major_radius=s, minor_radius=s * 0.3, location=(x, y, z))
        shape = bpy.context.active_object
        shape.data.materials.append(accent_mat if i % 2 else accent2_mat)
        shape.rotation_euler = (0, 0, 0)
        shape.keyframe_insert("rotation_euler", frame=1)
        shape.rotation_euler = (random.uniform(1, 3), random.uniform(1, 3), 0)
        shape.keyframe_insert("rotation_euler", frame=total)
        shape.location = (x, y, z)
        shape.keyframe_insert("location", frame=1)
        shape.location = (x, y, z + random.uniform(-0.8, 0.8))
        shape.keyframe_insert("location", frame=total)
        if shape.animation_data and shape.animation_data.action:
            for fc in shape.animation_data.action.fcurves:
                for kp in fc.keyframe_points:
                    kp.interpolation = "LINEAR"

    # --- bloom via compositor (best effort; API drifts across versions) ---
    # On failure we MUST switch compositing back off: a half-built node tree
    # with no Composite output renders 100% black frames while still
    # "succeeding", which the caller cannot detect.
    try:
        scene.use_nodes = True
        tree = scene.node_tree
        tree.nodes.clear()
        rl = tree.nodes.new("CompositorNodeRLayers")
        glare = tree.nodes.new("CompositorNodeGlare")
        for gtype in ("BLOOM", "FOG_GLOW"):
            try:
                glare.glare_type = gtype
                break
            except TypeError:
                continue
        comp = tree.nodes.new("CompositorNodeComposite")
        tree.links.new(rl.outputs["Image"], glare.inputs["Image"])
        tree.links.new(glare.outputs["Image"], comp.inputs["Image"])
    except Exception as exc:
        print(f"compositor bloom skipped: {exc}")
        scene.use_nodes = False        # roll back, else frames render black

    # --- output ---
    # Render under a run-unique prefix so a stale mp4 left in the directory
    # can never be mistaken for this render's output.
    out_dir = cfg["out_dir"]
    prefix = f"render_{cfg.get('seed', 0)}_"
    scene.render.image_settings.file_format = "FFMPEG"
    scene.render.ffmpeg.format = "MPEG4"
    scene.render.ffmpeg.codec = "H264"
    try:
        scene.render.ffmpeg.constant_rate_factor = "HIGH"
    except Exception:
        pass
    scene.render.filepath = os.path.join(out_dir, prefix)

    bpy.ops.render.render(animation=True)

    # Blender appends the frame range to the filename; match on our prefix and
    # sort so selection is deterministic (os.listdir order is arbitrary).
    produced = sorted(
        f for f in os.listdir(out_dir)
        if f.startswith(prefix) and f.endswith(".mp4")
    )
    if not produced:
        raise RuntimeError(f"Blender render produced no mp4 matching {prefix!r}")
    os.replace(os.path.join(out_dir, produced[0]),
               os.path.join(out_dir, "reel_final.mp4"))
    print("RENDER_OK")


if __name__ == "__main__":
    main()
