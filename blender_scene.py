"""Blender scene script — renders a vertical branded reel for one post.

Runs INSIDE Blender's Python, headless:
    blender -b --factory-startup -P blender_scene.py -- /path/to/config.json

The config JSON carries the text, colors, and output path (written by bot.py).
The whole scene is built procedurally so no .blend file needs to live in git.

Design: orthographic camera (framing is deterministic — no lens surprises),
extruded 3D text that scales in, emissive floating shapes drifting behind it,
slow zoom, bloom via the compositor when available.
"""

import json
import math
import os
import random
import sys

import bpy


def hex_to_rgba(hex_color, alpha=1.0):
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    # rough sRGB -> linear so colors don't wash out in render
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
        scene.eevee.taa_render_samples = 16
    except Exception:
        pass

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
    # Visible area: ortho_scale wide, ortho_scale * (h/w) tall.
    cam_data = bpy.data.cameras.new("Cam")
    cam_data.type = "ORTHO"
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (0, -10, 0)
    cam.rotation_euler = (math.pi / 2, 0, 0)
    bpy.context.collection.objects.link(cam)
    scene.camera = cam
    cam_data.ortho_scale = 10.7
    cam_data.keyframe_insert("ortho_scale", frame=1)
    cam_data.ortho_scale = 10.0          # slow zoom-in over the whole clip
    cam_data.keyframe_insert("ortho_scale", frame=total)
    # visible height at end: 10.0 * (1920/1080) ≈ 17.8 world units

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

    # --- text (visible height ~17.8, so z range ~[-8.9, +8.9]) ---
    hook = add_text("Hook", cfg["hook"], size=0.95, z=4.6, width=8.8,
                    font=font, material=text_mat, extrude=0.07, upper=True)
    punch = add_text("Punch", cfg["punchline"], size=0.52, z=-0.6, width=8.2,
                     font=font, material=text_mat, extrude=0.03)
    add_text("Handle", cfg["handle"], size=0.30, z=-7.7, width=9.0,
             font=font, material=accent_mat, extrude=0.01)

    scale_in(hook, 1, int(fps * 0.55))
    scale_in(punch, int(fps * 1.1), int(fps * 1.7))

    # --- floating emissive shapes behind the text ---
    for i in range(9):
        kind = random.choice(("ico", "cube", "torus"))
        x = random.uniform(-4.5, 4.5)
        z = random.uniform(-8, 8)
        y = random.uniform(2.5, 5.0)     # behind the text plane
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
        # slow tumble + drift
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

    # --- output ---
    out_dir = cfg["out_dir"]
    scene.render.image_settings.file_format = "FFMPEG"
    scene.render.ffmpeg.format = "MPEG4"
    scene.render.ffmpeg.codec = "H264"
    try:
        scene.render.ffmpeg.constant_rate_factor = "HIGH"
    except Exception:
        pass
    scene.render.filepath = os.path.join(out_dir, "reel")

    bpy.ops.render.render(animation=True)

    # Blender appends frame ranges to the filename; normalize it.
    produced = [f for f in os.listdir(out_dir) if f.endswith(".mp4")]
    if not produced:
        raise RuntimeError("Blender render produced no mp4")
    os.replace(os.path.join(out_dir, produced[0]),
               os.path.join(out_dir, "reel_final.mp4"))
    print("RENDER_OK")


if __name__ == "__main__":
    main()
