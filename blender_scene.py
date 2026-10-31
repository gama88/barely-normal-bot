"""Blender scene script — renders a vertical branded reel for one post.

Runs INSIDE Blender's Python, headless:
    blender -b --factory-startup -P blender_scene.py -- /path/to/config.json

The config JSON carries the text, colors, and output path (written by bot.py).
The whole scene is built procedurally so no .blend file needs to live in git.
If the config has "preview_frames": [n, ...], those frames are rendered as
PNGs instead of the video (for checking a layout in seconds, not minutes).

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

Layout, top to bottom: category chip, headline (one text object per line so
lines can pop in one after another), accent underline, question card with a
big "?", then a fixed footer: "answer in the comments" pill, handle, and a
progress bar. Everything sits on an animated background in one of STYLES.
"""

import json
import math
import os
import random
import sys

import bpy

STYLES = ("aurora", "grid", "spotlight")
FEED_LABELS = {"entertainment": "ENTERTAINMENT", "sports": "SPORTS",
               "top": "TODAY'S NEWS"}

LINE_HEIGHT = 1.12        # line pitch as a multiple of font size
MIN_TEXT_SIZE = 0.28

# Vertical regions (see framing note). The headline + card stack is centred
# in [STACK_BOTTOM, STACK_TOP]; chip above it, footer below it.
CHIP_Z = 6.62
STACK_TOP = 5.95
STACK_BOTTOM = -3.6
PILL_Z = -4.15
HANDLE_Z = -4.72
BAR_Z = -5.15

HOOK_WIDTH, HOOK_BUDGET = 8.4, 4.0
CARD_WIDTH, CARD_PAD = 8.8, 0.45
QUESTION_WIDTH, QUESTION_BUDGET = 7.2, 2.9


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


# ------------------------------------------------------------ text fit ---

_width_cache = {}


def measure(text, font):
    """Real rendered width of `text` at size 1.0, in scene units."""
    if text not in _width_cache:
        curve = bpy.data.curves.new("_measure", type="FONT")
        curve.body = text
        curve.size = 1.0
        if font:
            curve.font = font
        obj = bpy.data.objects.new("_measure", curve)
        bpy.context.collection.objects.link(obj)
        bpy.context.view_layer.update()
        _width_cache[text] = obj.dimensions.x
        bpy.data.objects.remove(obj)
        bpy.data.curves.remove(curve)
    return _width_cache[text]


def wrap(words, font, max_units):
    """Greedy word wrap against measured widths (max_units at size 1.0)."""
    lines, current = [], []
    for word in words:
        trial = " ".join(current + [word])
        if current and measure(trial, font) > max_units:
            lines.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        lines.append(" ".join(current))
    return lines


def fit_lines(text, font, base_size, max_width, budget):
    """Largest size <= base_size whose wrapped block fits width and height.

    Blender never scales glyphs to fit, so without this a long headline
    grows straight through whatever sits below it.
    """
    words = text.split()
    size = base_size
    while True:
        lines = wrap(words, font, max_width / size)
        widest = max(measure(line, font) for line in lines) * size
        height = block_height(len(lines), size)
        if (height <= budget and widest <= max_width) or size <= MIN_TEXT_SIZE:
            return balance(words, font, lines, max_width / size), size
        size = max(MIN_TEXT_SIZE, size * 0.94)


def balance(words, font, lines, max_units):
    """Narrow the wrap width while the line count holds, so lines come out
    even instead of a full line followed by a lone word."""
    width = max_units
    while len(lines) > 1:
        trial = wrap(words, font, width * 0.95)
        if len(trial) != len(lines):
            break
        lines, width = trial, width * 0.95
    return lines


def block_height(n_lines, size):
    return (n_lines - 1) * size * LINE_HEIGHT + size


# ------------------------------------------------------------ builders ---


def flat_material(name, rgba, strength=1.0):
    """Unlit color: emission only, so the hex lands exactly on screen."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    nodes.clear()
    emit = nodes.new("ShaderNodeEmission")
    emit.inputs["Color"].default_value = rgba
    emit.inputs["Strength"].default_value = strength
    out = nodes.new("ShaderNodeOutputMaterial")
    mat.node_tree.links.new(emit.outputs[0], out.inputs["Surface"])
    return mat


def glow_material(name, rgba, strength):
    """Lit + emissive (gives extruded text and shapes a little depth)."""
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


def add_line(name, body, size, font, material, location, extrude=0.04,
             align_x="CENTER"):
    curve = bpy.data.curves.new(name, type="FONT")
    curve.body = body
    curve.size = size
    curve.extrude = extrude
    curve.bevel_depth = extrude * 0.15
    curve.align_x = align_x
    curve.align_y = "TOP"
    if font:
        curve.font = font
    curve.materials.append(material)
    obj = bpy.data.objects.new(name, curve)
    obj.location = location
    # Font curves are built lying flat in the XY plane. The camera looks
    # along +Y, so without this the text is seen edge-on and renders as thin
    # horizontal bars. Rotating +90 deg about X stands it up in the XZ plane,
    # facing the camera, with text flowing downward in -Z.
    obj.rotation_euler = (math.pi / 2, 0, 0)
    bpy.context.collection.objects.link(obj)
    return obj


def add_centered_line(name, body, size, font, material, z_center, y=0.0,
                      extrude=0.02):
    """Single text line vertically centred on z_center (for pills/chips)."""
    # Cap height is ~0.72 of the font size for bold sans fonts.
    return add_line(name, body, size, font, material,
                    (0, y, z_center + size * 0.36 + size * 0.14),
                    extrude=extrude)


def add_rect(name, width, height, radius, material, location,
             anchor="CENTER", segments=6):
    """Rounded rectangle in the XZ plane, facing the camera.

    anchor="LEFT" puts the origin on the left edge so scaling X grows it
    rightward (used by the progress bar and the underline sweep).
    """
    radius = min(radius, width / 2, height / 2)
    x0 = 0.0 if anchor == "LEFT" else -width / 2
    corners = (  # centre of each corner arc, and its start angle
        (x0 + width - radius, height / 2 - radius, 0.0),
        (x0 + radius, height / 2 - radius, math.pi / 2),
        (x0 + radius, -height / 2 + radius, math.pi),
        (x0 + width - radius, -height / 2 + radius, 3 * math.pi / 2),
    )
    verts = []
    for cx, cz, start in corners:
        for i in range(segments + 1):
            a = start + (math.pi / 2) * i / segments
            verts.append((cx + radius * math.cos(a), 0.0,
                          cz + radius * math.sin(a)))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], [list(range(len(verts)))])
    mesh.materials.append(material)
    obj = bpy.data.objects.new(name, mesh)
    obj.location = location
    bpy.context.collection.objects.link(obj)
    return obj


# ----------------------------------------------------------- animation ---


def animate(target, path, keys, interpolation="BEZIER", easing="AUTO",
            owner=None):
    """Keyframe `target.path` at each (frame, value) and set the easing.

    `owner` is the ID holding the animation (defaults to target); needed for
    node sockets, whose curves live on the material/world node tree.
    """
    owner = owner or target
    for frame, value in keys:
        setattr(target, path, value)
        target.keyframe_insert(path, frame=frame)
    action = owner.animation_data.action if owner.animation_data else None
    if action is None:
        return
    frames = {k[0] for k in keys}
    for fc in action.fcurves:
        if not fc.data_path.endswith(path):
            continue
        for kp in fc.keyframe_points:
            if int(round(kp.co.x)) in frames:
                kp.interpolation = interpolation
                kp.easing = easing


def pop_in(obj, start, length=9, overshoot=True):
    """Scale up from nothing with a little springy overshoot."""
    animate(obj, "scale", [(start, (0.001, 0.001, 0.001)),
                           (start + length, (1.0, 1.0, 1.0))],
            interpolation="BACK" if overshoot else "BEZIER",
            easing="EASE_OUT")


def slide_in(obj, start, length, offset):
    """Move from location + offset to the current location."""
    home = tuple(obj.location)
    begin = tuple(h + o for h, o in zip(home, offset))
    animate(obj, "location", [(start, begin), (start + length, home)],
            interpolation="BACK", easing="EASE_OUT")


def hide_until(obj, frame):
    """Keep obj at zero scale before `frame` (it then pops/slides in)."""
    animate(obj, "scale", [(1, (0.001, 0.001, 0.001)),
                           (frame, (0.001, 0.001, 0.001))],
            interpolation="CONSTANT")


# ---------------------------------------------------------- background ---


def build_background(style, colors, total):
    """Big emissive plane behind everything with an animated shader."""
    bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 10, 0))
    plane = bpy.context.active_object
    plane.name = "Background"
    plane.scale = (13, 22, 1)
    # Bake the scale in so Object texture coordinates are in scene units
    # (otherwise they span only -0.5..0.5 and every pattern is one blur).
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    plane.rotation_euler = (math.pi / 2, 0, 0)

    mat = bpy.data.materials.new("Background")
    mat.use_nodes = True
    tree = mat.node_tree
    nodes, links = tree.nodes, tree.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    coord = nodes.new("ShaderNodeTexCoord")

    # Base: vertical gradient bg_bottom -> bg_top (local Y is world Z here).
    sep = nodes.new("ShaderNodeSeparateXYZ")
    links.new(coord.outputs["Generated"], sep.inputs[0])
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = hex_to_rgba(colors["bg_bottom"])
    ramp.color_ramp.elements[1].color = hex_to_rgba(colors["bg_top"])
    links.new(sep.outputs["Y"], ramp.inputs["Fac"])
    base = nodes.new("ShaderNodeEmission")
    links.new(ramp.outputs["Color"], base.inputs["Color"])

    def emission(rgba, strength_socket):
        e = nodes.new("ShaderNodeEmission")
        e.inputs["Color"].default_value = rgba
        links.new(strength_socket, e.inputs["Strength"])
        return e

    def scaled(socket, factor):
        m = nodes.new("ShaderNodeMath")
        m.operation = "MULTIPLY"
        links.new(socket, m.inputs[0])
        m.inputs[1].default_value = factor
        return m

    def add(a, b):
        s = nodes.new("ShaderNodeAddShader")
        links.new(a.outputs[0], s.inputs[0])
        links.new(b.outputs[0], s.inputs[1])
        return s

    def soft_ramp(socket, lo, hi):
        r = nodes.new("ShaderNodeValToRGB")
        r.color_ramp.elements[0].position = lo
        r.color_ramp.elements[1].position = hi
        links.new(socket, r.inputs["Fac"])
        return r

    def drifting_noise(scale, w_end):
        noise = nodes.new("ShaderNodeTexNoise")
        noise.noise_dimensions = "4D"
        noise.inputs["Scale"].default_value = scale
        noise.inputs["Detail"].default_value = 0.0   # one octave: cheap on CPU
        links.new(coord.outputs["Object"], noise.inputs["Vector"])
        animate(noise.inputs["W"], "default_value", [(1, 0.0), (total, w_end)],
                interpolation="LINEAR", owner=tree)
        return noise

    accent = hex_to_rgba(colors["accent"])
    accent2 = hex_to_rgba(colors["accent2"])

    if style == "aurora":
        # Two slow, morphing colour clouds.
        n1 = soft_ramp(drifting_noise(0.07, 0.6).outputs["Fac"], 0.42, 0.85)
        n2 = soft_ramp(drifting_noise(0.05, -0.5).outputs["Fac"], 0.45, 0.9)
        glow = add(emission(accent, scaled(n1.outputs["Color"], 0.07).outputs[0]),
                   emission(accent2, scaled(n2.outputs["Color"], 0.16).outputs[0]))
        shader = add(base, glow)
    elif style == "grid":
        # Neon grid scrolling upward, brightest at the bottom.
        mapping = nodes.new("ShaderNodeMapping")
        links.new(coord.outputs["Object"], mapping.inputs["Vector"])
        loc = mapping.inputs["Location"]
        animate(loc, "default_value", [(1, (0, 0, 0)), (total, (0, 0.14, 0))],
                interpolation="LINEAR", owner=tree)
        line_fac = []
        for direction in ("X", "Y"):
            wave = nodes.new("ShaderNodeTexWave")
            wave.wave_type = "BANDS"
            wave.bands_direction = direction
            wave.inputs["Scale"].default_value = 0.26 if direction == "X" else 0.26
            wave.inputs["Distortion"].default_value = 0.0
            links.new(mapping.outputs["Vector"], wave.inputs["Vector"])
            line_fac.append(soft_ramp(wave.outputs["Fac"], 0.96, 1.0))
        both = nodes.new("ShaderNodeMath")
        both.operation = "MAXIMUM"
        links.new(line_fac[0].outputs["Color"], both.inputs[0])
        links.new(line_fac[1].outputs["Color"], both.inputs[1])
        fade = soft_ramp(sep.outputs["Y"], 0.0, 0.75)    # bright low, dark high
        fade.color_ramp.elements[0].color = (1, 1, 1, 1)
        fade.color_ramp.elements[1].color = (0.0, 0.0, 0.0, 1)
        lines = nodes.new("ShaderNodeMath")
        lines.operation = "MULTIPLY"
        links.new(both.outputs[0], lines.inputs[0])
        links.new(fade.outputs["Color"], lines.inputs[1])
        haze = soft_ramp(drifting_noise(0.06, 0.5).outputs["Fac"], 0.5, 0.9)
        glow = add(emission(accent2, scaled(lines.outputs[0], 0.30).outputs[0]),
                   emission(accent2, scaled(haze.outputs["Color"], 0.06).outputs[0]))
        shader = add(base, glow)
    else:  # spotlight
        # Pulsing radial glow behind the headline, haze at the bottom.
        mapping = nodes.new("ShaderNodeMapping")
        mapping.inputs["Scale"].default_value = (0.17, 0.17, 0.17)
        mapping.inputs["Location"].default_value = (0, -0.5, 0)
        links.new(coord.outputs["Object"], mapping.inputs["Vector"])
        grad = nodes.new("ShaderNodeTexGradient")
        grad.gradient_type = "SPHERICAL"
        links.new(mapping.outputs["Vector"], grad.inputs["Vector"])
        soft = soft_ramp(grad.outputs["Fac"], 0.0, 1.0)
        soft.color_ramp.interpolation = "EASE"
        pulse = scaled(soft.outputs["Color"], 0.18)
        beat = pulse.inputs[1]
        keys = [(f, 0.18 if i % 2 else 0.30)
                for i, f in enumerate(range(1, total + 1, 30))]
        animate(beat, "default_value", keys, interpolation="SINE",
                easing="EASE_IN_OUT", owner=tree)
        haze = soft_ramp(drifting_noise(0.06, 0.5).outputs["Fac"], 0.5, 0.9)
        glow = add(emission(accent2, pulse.outputs[0]),
                   emission(accent, scaled(haze.outputs["Color"], 0.04).outputs[0]))
        shader = add(base, glow)

    links.new(shader.outputs[0], out.inputs["Surface"])
    plane.data.materials.append(mat)
    return plane


def build_shapes(materials, total, count=6):
    """Slow floating emissive shapes at the frame edges, behind everything."""
    for i in range(count):
        kind = random.choice(("ico", "cube", "torus"))
        # Keep the centre column clear: the copy spans x in [-4.4, 4.4], so
        # shapes sit at the frame edge (x = ±5.0) and partly past it.
        x = random.choice((-1, 1)) * random.uniform(4.6, 5.6)
        z = random.uniform(-8, 8)
        y = random.uniform(3.5, 6.5)
        s = random.uniform(0.15, 0.45)
        if kind == "ico":
            bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=s,
                                                  location=(x, y, z))
        elif kind == "cube":
            bpy.ops.mesh.primitive_cube_add(size=s * 1.6, location=(x, y, z))
        else:
            bpy.ops.mesh.primitive_torus_add(
                major_radius=s, minor_radius=s * 0.3, major_segments=24,
                minor_segments=8, location=(x, y, z))
        shape = bpy.context.active_object
        shape.data.materials.append(materials[i % len(materials)])
        animate(shape, "rotation_euler",
                [(1, (0, 0, 0)),
                 (total, (random.uniform(1, 3), random.uniform(1, 3), 0))],
                interpolation="LINEAR")
        animate(shape, "location",
                [(1, (x, y, z)), (total, (x, y, z + random.uniform(-0.8, 0.8)))],
                interpolation="LINEAR")


# ---------------------------------------------------------------- main ---


def setup_render(scene, cfg):
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
    scene.render.resolution_x = cfg["width"]
    scene.render.resolution_y = cfg["height"]
    scene.render.fps = cfg["fps"]
    scene.frame_start = 1
    scene.frame_end = cfg["fps"] * cfg["seconds"]


def setup_bloom(scene):
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
        scene.use_nodes = False


def main():
    cfg = load_config()
    random.seed(cfg.get("seed", 7))
    style = cfg.get("style") or random.choice(STYLES)
    print(f"scene style: {style}")

    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    setup_render(scene, cfg)
    fps = cfg["fps"]
    total = scene.frame_end

    colors = cfg["colors"]
    text_rgba = hex_to_rgba(colors["text"])
    accent_rgba = hex_to_rgba(colors["accent"])
    accent2_rgba = hex_to_rgba(colors["accent2"])
    dark_rgba = hex_to_rgba(colors["bg_bottom"])

    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = dark_rgba
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
    animate(cam_data, "ortho_scale", [(1, 10.6), (total, 10.0)],
            interpolation="LINEAR")       # slow push-in over the whole clip

    # --- lights (only the lit text/shapes use them) ---
    key = bpy.data.lights.new("Key", type="AREA")
    key.energy = 900
    key.size = 12
    # Shadow maps are the most expensive thing EEVEE does on a software
    # rasterizer, and nothing here sits in anything's shadow.
    key.use_shadow = False
    key_obj = bpy.data.objects.new("Key", key)
    key_obj.location = (0, -6, 4)
    key_obj.rotation_euler = (math.pi / 2.4, 0, 0)
    bpy.context.collection.objects.link(key_obj)
    rim = bpy.data.lights.new("Rim", type="POINT")
    rim.energy = 400
    rim.color = accent_rgba[:3]
    rim.use_shadow = False
    rim_obj = bpy.data.objects.new("Rim", rim)
    rim_obj.location = (3, 1, -2)
    bpy.context.collection.objects.link(rim_obj)

    # --- materials ---
    font = pick_font(cfg.get("font_candidates", []))
    text_mat = glow_material("Text", text_rgba, 0.35)
    glow_accent = glow_material("GlowAccent", accent_rgba, 4.0)
    glow_accent2 = glow_material("GlowAccent2", accent2_rgba, 4.0)
    flat_accent = flat_material("FlatAccent", accent_rgba)
    flat_accent2 = flat_material("FlatAccent2", accent2_rgba)
    flat_dark = flat_material("FlatDark", dark_rgba)
    card_mat = flat_material("Card", hex_to_rgba(colors["bg_top"]), 1.6)
    track_mat = flat_material("Track", (*text_rgba[:3], 1.0), 0.12)

    build_background(style, colors, total)
    build_shapes([glow_accent, glow_accent2], total)

    # --- layout: fit text, then centre the headline + card stack ---
    hook_lines, hook_size = fit_lines(cfg["hook"].upper(), font, 1.15,
                                      HOOK_WIDTH, HOOK_BUDGET)
    q_lines, q_size = fit_lines(cfg["punchline"], font, 0.72,
                                QUESTION_WIDTH, QUESTION_BUDGET)
    hook_h = block_height(len(hook_lines), hook_size)
    q_h = block_height(len(q_lines), q_size)
    card_h = q_h + 2 * CARD_PAD
    gap_bar, bar_h, gap_card = 0.28, 0.12, 0.62
    stack_h = hook_h + gap_bar + bar_h + gap_card + card_h
    slack = max(0.0, (STACK_TOP - STACK_BOTTOM) - stack_h)
    top = STACK_TOP - slack * 0.4         # sit a little above true centre

    # --- category chip ---
    label = FEED_LABELS.get(cfg.get("feed"), "TRENDING")
    chip_size = 0.32
    chip_w = measure(label, font) * chip_size + 0.7
    chip = add_rect("Chip", chip_w, 0.62, 0.31, flat_accent, (0, 0.3, CHIP_Z))
    chip_text = add_centered_line("ChipText", label, chip_size, font,
                                  flat_dark, CHIP_Z, y=0.1)
    for obj in (chip, chip_text):
        slide_in(obj, 1, 12, (-9, 0, 0))

    # --- headline, one line at a time ---
    f = 4
    for i, line in enumerate(hook_lines):
        z = top - i * hook_size * LINE_HEIGHT
        obj = add_line(f"Hook{i}", line, hook_size, font, text_mat,
                       (0, 0, z), extrude=0.07)
        hide_until(obj, f)
        pop_in(obj, f, 9)
        slide_in(obj, f, 9, (0, 0, -0.35))
        f += 5

    # --- underline sweep ---
    bar_z = top - hook_h - gap_bar - bar_h / 2
    under = add_rect("Underline", 2.4, bar_h, bar_h / 2, flat_accent,
                     (-1.2, 0.1, bar_z), anchor="LEFT")
    animate(under, "scale", [(f, (0.001, 1, 1)), (f + 8, (1, 1, 1))],
            interpolation="EXPO", easing="EASE_OUT")

    # --- question card ---
    card_top = bar_z - bar_h / 2 - gap_card
    card_z = card_top - card_h / 2
    card_start = max(f + 6, int(fps * 1.6))
    border = add_rect("CardBorder", CARD_WIDTH + 0.12, card_h + 0.12, 0.42,
                      flat_accent2, (0, 0.6, card_z))
    card = add_rect("Card", CARD_WIDTH, card_h, 0.36, card_mat,
                    (0, 0.5, card_z))
    for obj in (border, card):
        hide_until(obj, card_start)
        pop_in(obj, card_start, 10)
        slide_in(obj, card_start, 10, (0, 0, -1.2))

    qf = card_start + 7
    for i, line in enumerate(q_lines):
        z = card_top - CARD_PAD - i * q_size * LINE_HEIGHT
        obj = add_line(f"Question{i}", line, q_size, font, text_mat,
                       (0, 0, z), extrude=0.03)
        hide_until(obj, qf)
        pop_in(obj, qf, 8)
        qf += 3

    # Big tilted "?" hanging off the card's top-right corner.
    qmark = add_line("QMark", "?", 1.9, font, glow_accent,
                     (CARD_WIDTH / 2 - 0.55, -0.2, card_top + 0.85),
                     extrude=0.12)
    hide_until(qmark, qf)
    pop_in(qmark, qf, 12)
    wobble = [(qf, (math.pi / 2, 0.0, 0))]
    for i, frame in enumerate(range(qf + 12, total + 1, 20)):
        wobble.append((frame, (math.pi / 2, 0.22 if i % 2 else 0.05, 0)))
    animate(qmark, "rotation_euler", wobble, interpolation="SINE",
            easing="EASE_IN_OUT")

    # --- footer ---
    pill_start = max(qf + 10, int(fps * 3.0))
    pill_label = "ANSWER IN THE COMMENTS"
    pill_size = 0.27
    pill_w = measure(pill_label, font) * pill_size + 0.8
    pill = add_rect("Pill", pill_w, 0.6, 0.3, flat_accent2, (0, 0.3, PILL_Z))
    pill_text = add_centered_line("PillText", pill_label, pill_size, font,
                                  flat_dark, PILL_Z, y=0.1)
    for obj in (pill, pill_text):
        hide_until(obj, pill_start)
        pop_in(obj, pill_start, 10)
        # Two gentle "notice me" pulses later on.
        for beat in (int(fps * 4.6), int(fps * 6.0)):
            if beat + 8 < total:
                animate(obj, "scale", [(beat, (1, 1, 1)),
                                       (beat + 4, (1.08, 1.08, 1.08)),
                                       (beat + 8, (1, 1, 1))])

    add_line("Handle", cfg["handle"], 0.32, font, flat_accent,
             (0, 0, HANDLE_Z + 0.16), extrude=0.0)

    bar_w = 8.0
    add_rect("Track", bar_w, 0.07, 0.035, track_mat, (-bar_w / 2, 0.2, BAR_Z),
             anchor="LEFT")
    progress = add_rect("Progress", bar_w, 0.07, 0.035, flat_accent,
                        (-bar_w / 2, 0.1, BAR_Z), anchor="LEFT")
    animate(progress, "scale", [(1, (0.001, 1, 1)), (total, (1, 1, 1))],
            interpolation="LINEAR")

    setup_bloom(scene)

    out_dir = cfg["out_dir"]
    previews = cfg.get("preview_frames")
    if previews:
        scene.render.image_settings.file_format = "PNG"
        for frame in previews:
            scene.frame_set(frame)
            scene.render.filepath = os.path.join(
                out_dir, f"preview_{style}_{frame:03d}.png")
            bpy.ops.render.render(write_still=True)
        print("RENDER_OK")
        return

    # Render under a run-unique prefix so a stale mp4 left in the directory
    # can never be mistaken for this render's output.
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
