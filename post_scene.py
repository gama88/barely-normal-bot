"""Builds the 2D scene for one post: the bot's "scene editor".

Overlap2D separates the editor (which writes a scene file) from the runtime
(which plays it). Same here: this module only produces a SceneVO, pure data
that is also saved as scene.json next to the video, and scene2d plays it.

Layout (1080x1920, y down). Instagram covers roughly the top 10% and the
bottom 20% of a Reel with its UI, so everything sits in y 200..1530:
    category chip
    headline (one label per line, so lines pop in one after another)
    underline sweep
    question card with a big "?"
    footer: "answer in the comments" pill, handle, progress bar
on one of STYLES of animated background.
"""

import random

from scene2d import CompositeVO, ImageVO, LabelVO, SceneVO, ShapeVO
from scene2d.resources import load_font

STYLES = ("aurora", "grid", "spotlight")
FEED_LABELS = {"entertainment": "ENTERTAINMENT", "sports": "SPORTS",
               "top": "TODAY'S NEWS"}

W, H = 1080, 1920
CX = W / 2
LINE_HEIGHT = 1.12
MIN_TEXT_SIZE = 30

CHIP_Y = 245
STACK_TOP, STACK_BOTTOM = 317, 1349     # headline + card are centred in here
PILL_Y, HANDLE_Y, BAR_Y = 1408, 1470, 1516

HOOK_WIDTH, HOOK_BUDGET, HOOK_BASE = 900, 432, 120
CARD_WIDTH, CARD_PAD = 950, 50
QUESTION_WIDTH, QUESTION_BUDGET, QUESTION_BASE = 780, 313, 78


def rgba(hex_color, alpha=255):
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) + (alpha,)

# ---------------------------------------------------------------- text fit ---


def wrap(words, font, max_width):
    lines, current = [], []
    for word in words:
        trial = " ".join(current + [word])
        if current and font.getlength(trial) > max_width:
            lines.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        lines.append(" ".join(current))
    return lines


def balance(words, font, lines, max_width):
    """Narrow the wrap while the line count holds, so lines come out even
    instead of a full line followed by a lone word."""
    width = max_width
    while len(lines) > 1:
        trial = wrap(words, font, width * 0.95)
        if len(trial) != len(lines):
            break
        lines, width = trial, width * 0.95
    return lines


def block_height(n_lines, size):
    return (n_lines - 1) * size * LINE_HEIGHT + size


def fit_lines(text, font_path, base_size, max_width, budget):
    """Largest size <= base_size whose wrapped block fits width and height."""
    words = text.split()
    size = base_size
    while True:
        font = load_font(font_path, size)
        lines = wrap(words, font, max_width)
        widest = max(font.getlength(line) for line in lines)
        if ((block_height(len(lines), size) <= budget and widest <= max_width)
                or size <= MIN_TEXT_SIZE):
            return balance(words, font, lines, max_width), size
        size = max(MIN_TEXT_SIZE, int(size * 0.94))

# ------------------------------------------------------------- background ---


def background(style, colors, seconds, rng):
    """Returns (resources, items) for the background layer."""
    accent, accent2 = rgba(colors["accent"]), rgba(colors["accent2"])
    resources = {"gradient": {"kind": "gradient", "width": W, "height": H,
                              "top": rgba(colors["bg_top"]),
                              "bottom": rgba(colors["bg_bottom"])}}
    items = [ImageVO(name="gradient", image="gradient", x=CX, y=H / 2,
                     z_index=-100)]

    if style == "aurora":
        # Big soft colour clouds drifting slowly across the frame.
        for i, (color, alpha) in enumerate(((accent2, 120), (accent, 60),
                                            (accent2, 90))):
            name = f"cloud{i}"
            resources[name] = {"kind": "glow", "diameter": 900,
                               "color": color[:3] + (alpha,), "blur": 150}
            items.append(ImageVO(
                name=name, image=name, x=rng.uniform(100, W - 100),
                y=rng.uniform(250, H - 250), z_index=-90 + i,
                scripts=[{"script": "drift", "vx": rng.uniform(-25, 25),
                          "vy": rng.uniform(-20, 20)},
                         {"script": "bob", "dx": 60, "dy": 80,
                          "period": rng.uniform(5, 8), "phase": rng.random()}]))
    elif style == "grid":
        # Neon grid scrolling upward, brightest at the bottom.
        spacing = 120
        resources["grid"] = {"kind": "grid", "width": W + spacing,
                             "height": H + spacing, "spacing": spacing,
                             "color": accent2[:3] + (110,), "line": 4}
        items.append(ImageVO(
            name="grid", image="grid", x=CX, y=H / 2 + spacing / 2, z_index=-90,
            scripts=[{"script": "drift", "vy": -spacing / seconds}]))
        resources["horizon"] = {"kind": "glow", "diameter": 1200,
                                "color": accent2[:3] + (70,), "blur": 160}
        items.append(ImageVO(name="horizon", image="horizon", x=CX, y=H - 150,
                             z_index=-80))
    else:
        # Pulsing spotlight behind the headline.
        resources["spot"] = {"kind": "glow", "diameter": 1000,
                             "color": accent2[:3] + (120,), "blur": 170}
        items.append(ImageVO(
            name="spot", image="spot", x=CX, y=640, z_index=-90,
            scripts=[{"script": "breathe", "low": 0.55, "high": 1.0,
                      "period": 2.0}]))
        resources["floor"] = {"kind": "glow", "diameter": 900,
                              "color": accent[:3] + (40,), "blur": 160}
        items.append(ImageVO(name="floor", image="floor", x=CX, y=H - 100,
                             z_index=-80))

    # Small neon shapes floating at the frame edges, clear of the copy.
    for i in range(6):
        side = -1 if i % 2 else 1
        size = rng.uniform(34, 80)
        kind = rng.choice(("rect", "ring", "diamond"))
        color = accent if rng.random() < 0.5 else accent2
        items.append(ShapeVO(
            name=f"float{i}", shape=kind, width=size, height=size,
            radius=size * 0.18, fill=None if kind == "ring" else color,
            outline=color if kind == "ring" else None,
            outline_width=size * 0.16, glow=14,
            x=CX + side * rng.uniform(500, 570),
            y=rng.uniform(150, H - 150), rotation=rng.uniform(0, 90),
            z_index=-50,
            scripts=[{"script": "spin", "speed": rng.uniform(-30, 30)},
                     {"script": "bob", "dy": rng.uniform(20, 45),
                      "period": rng.uniform(3, 6), "phase": rng.random()}]))
    return resources, items

# ------------------------------------------------------------------ scene ---


def build_scene(post, *, colors, font, handle, fps=30, seconds=7, feed=None,
                style=None, seed=0):
    rng = random.Random(seed)
    style = style or rng.choice(STYLES)
    text = rgba(colors["text"])
    accent, accent2 = rgba(colors["accent"]), rgba(colors["accent2"])
    dark = rgba(colors["bg_bottom"])

    resources, bg_items = background(style, colors, seconds, rng)

    # --- fit text, then centre the headline + card stack ---
    hook_lines, hook_size = fit_lines(post["hook"].upper(), font, HOOK_BASE,
                                      HOOK_WIDTH, HOOK_BUDGET)
    q_lines, q_size = fit_lines(post["punchline"], font, QUESTION_BASE,
                                QUESTION_WIDTH, QUESTION_BUDGET)
    hook_h = block_height(len(hook_lines), hook_size)
    card_h = block_height(len(q_lines), q_size) + 2 * CARD_PAD
    gap_bar, bar_h, gap_card = 30, 13, 67
    stack_h = hook_h + gap_bar + bar_h + gap_card + card_h
    slack = max(0, (STACK_BOTTOM - STACK_TOP) - stack_h)
    top = STACK_TOP + slack * 0.4            # a little above true centre

    content = []

    # --- category chip ---
    label = FEED_LABELS.get(feed, "TRENDING")
    chip_font = 34
    chip_w = load_font(font, chip_font).getlength(label) + 76
    content.append(CompositeVO(
        name="chip", x=CX, y=CHIP_Y,
        scripts=[{"script": "slide_in", "start": 0.0, "duration": 0.4,
                  "dx": -900}],
        items=[ShapeVO(name="chip_bg", width=chip_w, height=66, radius=33,
                       fill=accent),
               LabelVO(name="chip_text", text=label, font=font,
                       size=chip_font, color=dark)]))

    # --- headline, one line at a time ---
    t = 0.13
    for i, line in enumerate(hook_lines):
        y = top + i * hook_size * LINE_HEIGHT + hook_size / 2
        content.append(LabelVO(
            name=f"hook{i}", text=line, font=font, size=hook_size, color=text,
            glow=10, glow_color=text[:3] + (90,), x=CX, y=y,
            scripts=[{"script": "pop_in", "start": t, "duration": 0.33},
                     {"script": "slide_in", "start": t, "duration": 0.33,
                      "dy": 38}]))
        t += 0.17

    # --- underline sweep ---
    bar_y = top + hook_h + gap_bar + bar_h / 2
    content.append(ShapeVO(
        name="underline", width=260, height=bar_h, radius=bar_h / 2,
        fill=accent, glow=8, x=CX - 130, y=bar_y, origin=(0, 0.5),
        scripts=[{"script": "grow_x", "start": t, "duration": 0.3}]))

    # --- question card (a composite: everything inside moves with it) ---
    card_top = bar_y + bar_h / 2 + gap_card
    card_start = max(t + 0.2, 1.6)
    q_start = card_start + 0.23
    card_items = [
        ShapeVO(name="card_bg", width=CARD_WIDTH, height=card_h, radius=40,
                fill=rgba(colors["bg_top"], 235), outline=accent2,
                outline_width=6, glow=18, glow_color=accent2[:3] + (120,)),
    ]
    for i, line in enumerate(q_lines):
        card_items.append(LabelVO(
            name=f"question{i}", text=line, font=font, size=q_size, color=text,
            x=0, y=-card_h / 2 + CARD_PAD + i * q_size * LINE_HEIGHT + q_size / 2,
            scripts=[{"script": "pop_in", "start": q_start + i * 0.1,
                      "duration": 0.27}]))
    q_end = q_start + len(q_lines) * 0.1
    card_items.append(LabelVO(
        name="qmark", text="?", font=font, size=210, color=accent, glow=16,
        glow_color=accent[:3] + (150,), x=CARD_WIDTH / 2 - 65,
        y=-card_h / 2 - 15, rotation=-12, z_index=5,
        scripts=[{"script": "pop_in", "start": q_end, "duration": 0.4},
                 {"script": "wobble", "start": q_end + 0.4, "amplitude": 9,
                  "period": 1.4}]))
    content.append(CompositeVO(
        name="card", x=CX, y=card_top + card_h / 2, items=card_items,
        scripts=[{"script": "pop_in", "start": card_start, "duration": 0.33},
                 {"script": "slide_in", "start": card_start,
                  "duration": 0.33, "dy": 130}]))

    # --- footer ---
    pill_start = max(q_end + 0.33, 3.0)
    pill_label = "ANSWER IN THE COMMENTS"
    pill_font = 29
    pill_w = load_font(font, pill_font).getlength(pill_label) + 86
    beats = [b for b in (4.6, 6.0) if b + 0.3 < seconds]
    ui = [
        CompositeVO(
            name="pill", x=CX, y=PILL_Y,
            scripts=[{"script": "pop_in", "start": pill_start,
                      "duration": 0.33},
                     {"script": "pulse", "at": beats, "amount": 0.08}],
            items=[ShapeVO(name="pill_bg", width=pill_w, height=64, radius=32,
                           fill=accent2, glow=12),
                   LabelVO(name="pill_text", text=pill_label, font=font,
                           size=pill_font, color=dark)]),
        LabelVO(name="handle", text=handle, font=font, size=34, color=accent,
                x=CX, y=HANDLE_Y),
        ShapeVO(name="track", width=860, height=8, radius=4,
                fill=text[:3] + (60,), x=CX, y=BAR_Y),
        ShapeVO(name="progress", width=860, height=8, radius=4, fill=accent,
                x=CX - 430, y=BAR_Y, origin=(0, 0.5), z_index=1,
                scripts=[{"script": "progress", "start": 0,
                          "end": seconds}]),
    ]

    root = CompositeVO(name="root", items=[
        CompositeVO(name="background", layer="background", items=bg_items),
        CompositeVO(name="content", layer="content", items=content),
        CompositeVO(name="ui", layer="ui", items=ui),
    ])
    return SceneVO(width=W, height=H, fps=fps, seconds=seconds,
                   background=rgba(colors["bg_bottom"]), resources=resources,
                   root=root)
