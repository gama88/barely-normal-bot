"""Builds the 2D scene for one post: the bot's "scene editor".

Overlap2D separates the editor (which writes a scene file) from the runtime
(which plays it). Same here: this module only produces a SceneVO, pure data
that is also saved as scene.json next to the video, and scene2d plays it.

The post is told by a picture: an animated illustration of what the story
is about (visuals.py picks it from the headline) fills the stage, with the
headline and the question underneath. Layout (1080x1920, y down);
Instagram covers roughly the top 10% and the bottom 20% of a Reel with its
UI, so everything sits in y 200..1530:
    category chip            y 245
    stage (illustration)     y 300..940
    headline                 y 980..1150
    question card            below the headline, ends by 1370
    footer                   "answer in the comments", handle, progress bar
"""

import random
from types import SimpleNamespace

import visuals
from scene2d import CompositeVO, ImageVO, LabelVO, SceneVO, ShapeVO
from scene2d.resources import load_font

FEED_LABELS = {"entertainment": "ENTERTAINMENT", "sports": "SPORTS",
               "top": "TODAY'S NEWS"}

W, H = 1080, 1920
CX = W / 2
LINE_HEIGHT = 1.12
MIN_TEXT_SIZE = 30

CHIP_Y = 245
STAGE_Y = 625
HOOK_TOP, HOOK_WIDTH, HOOK_BUDGET, HOOK_BASE = 985, 940, 165, 74
CARD_GAP, CARD_WIDTH, CARD_PAD = 28, 960, 30
QUESTION_WIDTH, QUESTION_BUDGET, QUESTION_BASE = 780, 130, 54
ANSWER_Y, HANDLE_Y, BAR_Y = 1408, 1462, 1508


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

# ------------------------------------------------------------------ scene ---


def build_up(items, span=0.7):
    """Make the illustration assemble itself: each piece pops in at its own
    spot, one after another. A wrapper composite sits where the piece was and
    owns the pop, so the piece's own scripts (flights, spins) run untouched."""
    wrapped = []
    for i, item in enumerate(items):
        x, y = item.x, item.y
        item.x = item.y = 0
        wrapped.append(CompositeVO(
            name=f"{item.name}_in", x=x, y=y, z_index=item.z_index,
            items=[item],
            scripts=[{"script": "pop_in", "start": span * i / max(1, len(items)),
                      "duration": 0.35}]))
    return wrapped



def build_scene(post, *, colors, font, handle, fps=30, seconds=7, feed=None,
                title="", visual=None, seed=0):
    rng = random.Random(seed)
    text = rgba(colors["text"])
    accent, accent2 = rgba(colors["accent"]), rgba(colors["accent2"])
    dark = rgba(colors["bg_bottom"])

    visual = visual or visuals.pick_visual(title, post["hook"],
                                           post["punchline"], feed=feed)
    ticker = "  BREAKING NEWS  •"
    ctx = SimpleNamespace(font=font, accent=accent, accent2=accent2, rng=rng,
                          ticker_step=load_font(font, 40).getlength(ticker))

    # --- background: gradient + a soft glow behind the stage ---
    resources = {
        "gradient": {"kind": "gradient", "width": W, "height": H,
                     "top": rgba(colors["bg_top"]),
                     "bottom": rgba(colors["bg_bottom"])},
        "stage_glow": {"kind": "glow", "diameter": 900,
                       "color": accent2[:3] + (70,), "blur": 160},
    }
    background = [
        ImageVO(name="gradient", image="gradient", x=CX, y=H / 2, z_index=-100),
        ImageVO(name="stage_glow", image="stage_glow", x=CX, y=STAGE_Y,
                z_index=-90,
                scripts=[{"script": "breathe", "low": 0.7, "high": 1.0,
                          "period": 3.0}]),
    ]

    # --- the illustration: what the story is about ---
    stage = CompositeVO(name=f"stage_{visual}", x=CX, y=STAGE_Y,
                        items=build_up(visuals.BUILDERS[visual](ctx)),
                        scripts=[{"script": "fade_in", "start": 0.0,
                                  "duration": 0.25}])

    # --- category chip ---
    label = FEED_LABELS.get(feed, "TRENDING")
    chip_font = 34
    chip = CompositeVO(
        name="chip", x=CX, y=CHIP_Y,
        scripts=[{"script": "slide_in", "start": 0.0, "duration": 0.4,
                  "dx": -900}],
        items=[ShapeVO(name="chip_bg", width=load_font(font, chip_font)
                       .getlength(label) + 76, height=66, radius=33,
                       fill=accent),
               LabelVO(name="chip_text", text=label, font=font,
                       size=chip_font, color=dark)])

    # --- headline, one line at a time ---
    hook_lines, hook_size = fit_lines(post["hook"].upper(), font, HOOK_BASE,
                                      HOOK_WIDTH, HOOK_BUDGET)
    words = []
    t = 0.35
    for i, line in enumerate(hook_lines):
        words.append(LabelVO(
            name=f"hook{i}", text=line, font=font, size=hook_size, color=text,
            glow=8, glow_color=text[:3] + (80,), x=CX,
            y=HOOK_TOP + i * hook_size * LINE_HEIGHT + hook_size / 2,
            scripts=[{"script": "pop_in", "start": t, "duration": 0.33},
                     {"script": "slide_in", "start": t, "duration": 0.33,
                      "dy": 30}]))
        t += 0.17

    # --- question card ---
    q_lines, q_size = fit_lines(post["punchline"], font, QUESTION_BASE,
                                QUESTION_WIDTH, QUESTION_BUDGET)
    card_h = block_height(len(q_lines), q_size) + 2 * CARD_PAD
    card_top = (HOOK_TOP + block_height(len(hook_lines), hook_size)
                + CARD_GAP)
    card_start = max(t + 0.3, 1.8)
    card_items = [ShapeVO(name="card_bg", width=CARD_WIDTH, height=card_h,
                          radius=34, fill=rgba(colors["bg_top"], 235),
                          outline=accent2, outline_width=5, glow=14,
                          glow_color=accent2[:3] + (110,))]
    for i, line in enumerate(q_lines):
        card_items.append(LabelVO(
            name=f"question{i}", text=line, font=font, size=q_size, color=text,
            x=0, y=-card_h / 2 + CARD_PAD + i * q_size * LINE_HEIGHT + q_size / 2))
    q_end = card_start + 0.4
    card_items.append(LabelVO(
        name="qmark", text="?", font=font, size=100, color=accent, glow=12,
        glow_color=accent[:3] + (150,), x=CARD_WIDTH / 2 - 52, y=0,
        rotation=-12, z_index=5,
        scripts=[{"script": "pop_in", "start": q_end, "duration": 0.4},
                 {"script": "wobble", "start": q_end + 0.4, "amplitude": 9,
                  "period": 1.4}]))
    card = CompositeVO(
        name="card", x=CX, y=card_top + card_h / 2, items=card_items,
        scripts=[{"script": "pop_in", "start": card_start, "duration": 0.33},
                 {"script": "slide_in", "start": card_start,
                  "duration": 0.33, "dy": 90}])

    # --- footer ---
    beats = [b for b in (4.6, 6.0) if b + 0.3 < seconds]
    ui = [
        LabelVO(name="answer", text="ANSWER IN THE COMMENTS", font=font,
                size=30, color=accent2, glow=8, glow_color=accent2[:3] + (120,),
                x=CX, y=ANSWER_Y,
                scripts=[{"script": "pop_in", "start": max(q_end + 0.4, 3.0),
                          "duration": 0.33},
                         {"script": "pulse", "at": beats, "amount": 0.1}]),
        LabelVO(name="handle", text=handle, font=font, size=32, color=accent,
                x=CX, y=HANDLE_Y),
        ShapeVO(name="track", width=860, height=8, radius=4,
                fill=text[:3] + (60,), x=CX, y=BAR_Y),
        ShapeVO(name="progress", width=860, height=8, radius=4, fill=accent,
                x=CX - 430, y=BAR_Y, origin=(0, 0.5), z_index=1,
                scripts=[{"script": "progress", "start": 0,
                          "end": seconds}]),
    ]

    root = CompositeVO(name="root", items=[
        CompositeVO(name="background", layer="background", items=background),
        CompositeVO(name="content", layer="content",
                    items=[stage, chip] + words + [card]),
        CompositeVO(name="ui", layer="ui", items=ui),
    ])
    return SceneVO(width=W, height=H, fps=fps, seconds=seconds,
                   background=dark, resources=resources, root=root)
