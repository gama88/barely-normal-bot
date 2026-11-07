"""Library of animated 2D illustrations, one per kind of story.

These are reusable composites, like Overlap2D's library items: each
builder returns a list of scene2d items drawn around (0, 0), roughly
900 x 640 px. post_scene.py drops the right one onto the stage, picked by
`pick_visual` from words in the headline, so a trade story shows a
football flying through the uprights and a box-office story shows a
clapperboard and a running film strip.
"""

import math
import re

from scene2d import CompositeVO, LabelVO, ShapeVO

WHITE = (245, 245, 242, 255)
DARK = (25, 22, 30, 255)
GOLD = (255, 196, 40, 255)
GOLD_DARK = (205, 140, 20, 255)
GRAY = (150, 150, 162, 255)


def _a(color, alpha):
    return tuple(color[:3]) + (alpha,)


def S(script, **params):
    return {"script": script, **params}


def R(name, x, y, w, h, fill=None, r=0, outline=None, ow=0, **kw):
    return ShapeVO(name=name, shape="rect", x=x, y=y, width=w, height=h,
                   radius=r, fill=fill, outline=outline, outline_width=ow, **kw)


def E(name, x, y, w, h, fill=None, outline=None, ow=0, **kw):
    return ShapeVO(name=name, shape="ellipse", x=x, y=y, width=w, height=h,
                   fill=fill, outline=outline, outline_width=ow, **kw)


def P(name, x, y, w, h, points, fill=None, outline=None, ow=0, **kw):
    return ShapeVO(name=name, shape="polygon", x=x, y=y, width=w, height=h,
                   points=points, fill=fill, outline=outline,
                   outline_width=ow, **kw)


def A(name, x, y, w, h, start, end, color, ow, **kw):
    return ShapeVO(name=name, shape="arc", x=x, y=y, width=w, height=h,
                   start_angle=start, end_angle=end, outline=color,
                   outline_width=ow, **kw)


def C(name, x, y, items, **kw):
    return CompositeVO(name=name, x=x, y=y, items=items, **kw)


def T(name, text, x, y, size, color, font, **kw):
    return LabelVO(name=name, text=text, x=x, y=y, size=size, color=color,
                   font=font, **kw)


def heart(name, x, y, size, color, **kw):
    return C(name, x, y, [
        E(f"{name}_l", -size * 0.25, -size * 0.12, size * 0.55, size * 0.55, fill=color),
        E(f"{name}_r", size * 0.25, -size * 0.12, size * 0.55, size * 0.55, fill=color),
        P(f"{name}_tip", 0, size * 0.12, size * 0.78, size * 0.78,
          [(0.5, 0), (1, 0.5), (0.5, 1), (0, 0.5)], fill=color),
    ], **kw)


def confetti(ctx, count=24):
    colors = (ctx.accent, ctx.accent2, GOLD, WHITE)
    return [R(f"confetti{i}", ctx.rng.uniform(-430, 430), -330,
              ctx.rng.uniform(10, 18), ctx.rng.uniform(18, 30),
              fill=colors[i % len(colors)], rotation=ctx.rng.uniform(0, 180),
              scripts=[S("fall_loop", distance=680,
                         period=ctx.rng.uniform(2.2, 3.4), phase=ctx.rng.random()),
                       S("spin", speed=ctx.rng.uniform(-220, 220))])
            for i in range(count)]


def sparkles(ctx, count=6, spread=(300, 220)):
    return [P(f"sparkle{i}", ctx.rng.uniform(-spread[0], spread[0]),
              ctx.rng.uniform(-spread[1], spread[1]), 34, 34,
              [(0.5, 0), (0.62, 0.38), (1, 0.5), (0.62, 0.62), (0.5, 1),
               (0.38, 0.62), (0, 0.5), (0.38, 0.38)], fill=WHITE, glow=8,
              scripts=[S("pump", low=0.0, high=1.0,
                         period=ctx.rng.uniform(0.9, 1.6), phase=ctx.rng.random())])
            for i in range(count)]

# ----------------------------------------------------------------- sports ---


def football(ctx):
    field = [R("field", 0, 150, 880, 330, fill=(30, 110, 55, 255), r=28,
               outline=_a(WHITE, 200), ow=5)]
    field += [R(f"yard{i}", -330 + i * 110, 150, 6, 300, fill=_a(WHITE, 110))
              for i in range(7)]
    goal = C("goalpost", 340, 40, [
        R("post", 0, 130, 14, 150, fill=GOLD),
        R("crossbar", 0, 55, 170, 14, fill=GOLD),
        R("upright_l", -78, -55, 12, 230, fill=GOLD),
        R("upright_r", 78, -55, 12, 230, fill=GOLD),
    ])
    ball = C("ball", -360, 200, [
        E("leather", 0, 0, 124, 72, fill=(150, 75, 30, 255),
          outline=(90, 40, 10, 255), ow=3),
        R("lace", 0, -4, 48, 7, fill=WHITE, r=3),
        *[R(f"stitch{i}", -15 + i * 10, -4, 4, 18, fill=WHITE) for i in range(4)],
    ], scripts=[S("arc_path", start=0.15, duration=1.5, x1=700, y1=-260,
                  height=300, period=2.6),
                S("spin", speed=-360)])
    return field + [goal, ball]


def basketball(ctx):
    seam = DARK
    return [
        R("floor", 0, 290, 900, 26, fill=(190, 130, 70, 255), r=6),
        R("pole", 390, 110, 22, 360, fill=GRAY),
        R("arm", 345, -80, 80, 10, fill=GRAY),
        R("backboard", 330, -160, 200, 150, fill=_a(WHITE, 235), r=10,
          outline=(40, 40, 50, 255), ow=4),
        R("target", 330, -135, 80, 60, outline=(220, 60, 40, 255), ow=5),
        P("net", 270, -25, 120, 90, [(0, 0), (1, 0), (0.8, 1), (0.2, 1)],
          outline=WHITE, ow=3, z_index=2),
        E("rim", 270, -80, 136, 26, outline=(240, 100, 20, 255), ow=8, z_index=3),
        C("ball", -380, 230, [
            E("skin", 0, 0, 100, 100, fill=(230, 110, 30, 255), outline=seam, ow=4),
            R("seam_v", 0, 0, 4, 100, fill=seam),
            R("seam_h", 0, 0, 100, 4, fill=seam),
            A("seam_l", -32, 0, 90, 100, -60, 60, seam, 4),
            A("seam_r", 32, 0, 90, 100, 120, 240, seam, 4),
        ], z_index=1,
          scripts=[S("arc_path", start=0.15, duration=1.3, x1=650, y1=-330,
                     height=330, period=2.6, drop=900),
                   S("spin", speed=300)]),
    ]


def soccer(ctx):
    net = [R(f"net_v{i}", -170 + i * 34, 0, 3, 260, fill=_a(WHITE, 90))
           for i in range(11)]
    net += [R(f"net_h{i}", 0, -128 + i * 32, 360, 3, fill=_a(WHITE, 90))
            for i in range(9)]
    return [
        R("grass", 0, 250, 900, 150, fill=(40, 130, 60, 255), r=20),
        C("goal", 230, 40, net + [R("frame", 0, 0, 380, 280, outline=WHITE,
                                    ow=12, r=4)]),
        C("ball", -380, 260, [
            E("ball", 0, 0, 90, 90, fill=WHITE, outline=DARK, ow=3),
            P("patch", 0, 0, 34, 34,
              [(0.5 + 0.5 * math.cos(math.radians(a)),
                0.5 + 0.5 * math.sin(math.radians(a)))
               for a in range(-90, 270, 72)], fill=DARK),
        ], scripts=[S("arc_path", start=0.15, duration=1.2, x1=610, y1=-230,
                      height=200, period=2.6),
                    S("spin", speed=320)]),
    ]


def trophy(ctx):
    cup = C("trophy", 0, 40, [
        A("handle_l", -125, -95, 100, 120, 90, 270, GOLD, 16),
        A("handle_r", 125, -95, 100, 120, -90, 90, GOLD, 16),
        P("cup", 0, -70, 270, 220,
          [(0, 0), (1, 0), (0.82, 0.7), (0.5, 1), (0.18, 0.7)], fill=GOLD,
          glow=16, glow_color=_a(GOLD, 120)),
        R("shine", -60, -100, 18, 110, fill=_a(WHITE, 120), r=9, rotation=8),
        R("stem", 0, 80, 44, 90, fill=GOLD_DARK),
        R("base", 0, 140, 210, 44, fill=GOLD_DARK, r=8),
        R("plate", 0, 190, 260, 56, fill=(70, 50, 30, 255), r=8),
    ], scripts=[S("slide_in", start=0.1, duration=0.8, dy=-450,
                  ease="bounce_out")])
    return confetti(ctx) + sparkles(ctx) + [cup]

# ------------------------------------------------------- entertainment ---


def music(ctx):
    items = [
        P("beam_l", -260, -330, 300, 640, [(0.45, 0), (0.55, 0), (1, 1), (0, 1)],
          fill=_a(ctx.accent, 55), origin=(0.5, 0),
          scripts=[S("wobble", amplitude=16, period=2.8)]),
        P("beam_r", 260, -330, 300, 640, [(0.45, 0), (0.55, 0), (1, 1), (0, 1)],
          fill=_a(ctx.accent2, 65), origin=(0.5, 0),
          scripts=[S("wobble", amplitude=16, period=2.8, phase=0.5)]),
    ]
    items += [R(f"eq{i}", -378 + i * 84, 262, 48, 200,
                fill=_a(ctx.accent if i % 2 else ctx.accent2, 210), r=6,
                origin=(0.5, 1),
                scripts=[S("pump", low=0.15, high=1.0, axis="y",
                           period=ctx.rng.uniform(0.45, 0.9), phase=ctx.rng.random())])
              for i in range(10)]
    items += [
        R("stage", 0, 290, 900, 54, fill=(40, 20, 60, 255), r=10,
          outline=ctx.accent2, ow=3),
        C("mic", 0, 30, [
            E("mic_base", 0, 240, 150, 26, fill=GRAY),
            R("mic_stand", 0, 125, 12, 230, fill=GRAY),
            R("mic_neck", 0, -20, 28, 60, fill=(80, 80, 90, 255)),
            E("mic_head", 0, -95, 96, 130, fill=(70, 70, 82, 255),
              outline=(190, 190, 200, 255), ow=5),
            *[R(f"grill{i}", 0, -125 + i * 28, 72, 4, fill=(190, 190, 200, 255))
              for i in range(3)],
        ], scripts=[S("bob", dy=6, period=1.2)]),
    ]
    for i in range(6):
        color = WHITE if i % 2 else ctx.accent
        items.append(C(f"note{i}", ctx.rng.choice((-1, 1)) * ctx.rng.uniform(150, 400),
                       150, [
            E("head", 0, 0, 38, 28, fill=color, rotation=20),
            R("stem", 15, -40, 6, 80, fill=color),
            R("flag", 28, -72, 28, 9, fill=color, rotation=-30),
        ], scripts=[S("rise_loop", distance=420, period=ctx.rng.uniform(2.2, 3.2),
                      phase=ctx.rng.random(), sway=20)]))
    return items


def movie(ctx):
    holes = []
    for i in range(20):
        for y in (-44, 44):
            holes.append(R(f"hole{i}_{y}", -570 + i * 60, y, 26, 18,
                           fill=_a(WHITE, 210), r=3))
    frames = [R(f"frame{i}", -540 + i * 180, 0, 150, 58,
                fill=_a(ctx.accent2 if i % 2 else ctx.accent, 110), r=4)
              for i in range(7)]
    strip = C("filmstrip", 0, -235, [R("film", 0, 0, 1200, 124, fill=(20, 20, 24, 255))]
              + holes + frames,
              scripts=[S("keys", prop="x", keys=[[0, 0], [1.2, -180]],
                         ease="linear", period=1.2)])
    stripes = [P(f"stripe{i}", 30 + i * 70, -22, 44, 44,
                 [(0.4, 0), (1, 0), (0.6, 1), (0, 1)], fill=DARK)
               for i in range(5)]
    clapper = C("clapper", -130, 120, [
        R("board", 0, 40, 340, 230, fill=(30, 30, 36, 255), r=12),
        R("band", 0, -55, 340, 40, fill=WHITE),
        *[P(f"band_stripe{i}", -135 + i * 70, -55, 44, 40,
            [(0.4, 0), (1, 0), (0.6, 1), (0, 1)], fill=DARK) for i in range(5)],
        T("scene", "SCENE 1", 0, 25, 40, WHITE, ctx.font),
        T("take", "TAKE 3", 0, 95, 34, _a(WHITE, 200), ctx.font),
        C("stick", -170, -75, [R("stick_bar", 170, -22, 340, 44, fill=WHITE, r=4)]
          + stripes,
          scripts=[S("keys", prop="rot",
                     keys=[[0, 28], [0.55, 28], [0.68, 0], [1.4, 0], [2.0, 28]],
                     period=2.6)]),
    ])
    popcorn = C("popcorn", 270, 150, [
        P("bucket", 0, 40, 180, 200, [(0, 0), (1, 0), (0.85, 1), (0.15, 1)],
          fill=(220, 40, 50, 255), z_index=2),
        *[R(f"bucket_stripe{i}", -45 + i * 45, 40, 20, 190, fill=WHITE,
            rotation=(1 - i) * 4, z_index=3) for i in range(3)],
        *[E(f"kernel{i}", -70 + (i % 5) * 35, -70 - (i // 5) * 26, 46, 40,
            fill=(255, 238, 190, 255), outline=(230, 200, 140, 255), ow=2)
          for i in range(9)],
        *[E(f"pop{i}", -40 + i * 40, -80, 34, 30, fill=(255, 238, 190, 255),
            scripts=[S("arc_path", start=0.3 + i * 0.4, duration=0.7,
                       x1=(i - 1) * 60, y1=-30, height=120, period=1.8)])
          for i in range(3)],
    ])
    return [strip, clapper, popcorn]


def tv(ctx):
    bars = [(245, 245, 245), (240, 220, 40), (40, 210, 220), (60, 200, 70),
            (220, 60, 200), (220, 50, 50), (50, 70, 220)]
    return [
        C("antenna", 0, -190, [
            R("ant_l", -55, -85, 8, 190, fill=GRAY, rotation=25),
            R("ant_r", 55, -85, 8, 190, fill=GRAY, rotation=-25),
            E("ant_base", 0, 0, 60, 34, fill=(60, 60, 70, 255)),
        ], scripts=[S("wobble", amplitude=5, period=1.8)]),
        C("tv", 0, 50, [
            R("leg_l", -190, 225, 22, 70, fill=(60, 40, 25, 255), rotation=14),
            R("leg_r", 190, 225, 22, 70, fill=(60, 40, 25, 255), rotation=-14),
            R("cabinet", 0, 0, 580, 410, fill=(110, 70, 45, 255), r=40,
              outline=(60, 40, 25, 255), ow=6),
            R("screen", -45, 0, 410, 320, fill=(20, 20, 25, 255), r=30),
            *[R(f"bar{i}", -45 - 171 + i * 57, 0, 57, 296, fill=c + (255,))
              for i, c in enumerate(bars)],
            R("static", -45, 0, 410, 320, fill=_a(WHITE, 70), r=30,
              scripts=[S("flicker", period=0.16, duty=0.35)]),
            E("knob1", 225, -90, 54, 54, fill=(200, 190, 170, 255)),
            E("knob2", 225, -10, 54, 54, fill=(200, 190, 170, 255)),
            *[R(f"speaker{i}", 225, 70 + i * 20, 70, 7, fill=(60, 40, 25, 255), r=3)
              for i in range(4)],
        ], scripts=[S("bob", dy=6, period=2.2)]),
    ]

# ------------------------------------------------------------- life/news ---


def love(ctx):
    red, pink = (235, 40, 80, 255), ctx.accent2
    items = [E("love_glow", 0, 0, 420, 330, fill=_a(pink, 22), glow=70,
               glow_color=_a(pink, 140),
               scripts=[S("pump", low=0.85, high=1.05, period=0.9)])]
    items += [heart(f"mini{i}", ctx.rng.uniform(-380, 380), 220, 46,
                    _a(pink if i % 2 else red, 230),
                    scripts=[S("rise_loop", distance=480,
                               period=ctx.rng.uniform(2.4, 3.4),
                               phase=ctx.rng.random(), sway=25)])
              for i in range(8)]
    items += [
        heart("heart_l", -105, 0, 230, red,
              scripts=[S("slide_in", start=0.1, duration=0.9, dx=-420),
                       S("pump", low=0.92, high=1.04, period=0.9)]),
        heart("heart_r", 105, 0, 230, pink,
              scripts=[S("slide_in", start=0.1, duration=0.9, dx=420),
                       S("pump", low=0.92, high=1.04, period=0.9, phase=0.5)]),
    ]
    return items


def money(ctx):
    green = (60, 200, 110, 255)
    heights = (120, 170, 150, 240, 320)
    items = [R("axis", -120, 262, 520, 8, fill=_a(WHITE, 180))]
    items += [R(f"bar{i}", -320 + i * 100, 258, 70, h, fill=green, r=6,
                origin=(0.5, 1),
                scripts=[S("keys", prop="sy", keys=[[0, 0.02], [0.7, 1.0]],
                           ease="back_out", start=0.1 + i * 0.12)])
              for i, h in enumerate(heights)]
    items.append(P("arrow", -60, -170, 150, 170,
                   [(0.5, 0), (1, 0.45), (0.68, 0.45), (0.68, 1), (0.32, 1),
                    (0.32, 0.45), (0, 0.45)], fill=ctx.accent, glow=14,
                   rotation=-30,
                   scripts=[S("slide_in", start=0.7, duration=0.6, dy=120),
                            S("bob", dy=10, period=1.6)]))
    items += [E(f"stack{i}", 300, 240 - i * 26, 140, 44, fill=GOLD,
                outline=GOLD_DARK, ow=5) for i in range(5)]
    for i in range(5):
        items.append(C(f"coin{i}", 300 + ctx.rng.uniform(-90, 90), -330, [
            E("coin", 0, 0, 96, 96, fill=GOLD, outline=GOLD_DARK, ow=7),
            T("dollar", "$", 0, 0, 56, GOLD_DARK, ctx.font),
        ], scripts=[S("fall_loop", distance=470, period=1.8,
                      phase=i / 5),
                    S("spin", speed=ctx.rng.uniform(-90, 90))]))
    return items


def tech(ctx):
    blue = (70, 120, 255, 255)
    items = [ShapeVO(name=f"ping{i}", shape="ring", width=420, height=420,
                     outline=_a(ctx.accent, 200), outline_width=8,
                     scripts=[S("expand_loop", period=2.0, phase=i / 2,
                                start_scale=0.5, end_scale=1.7)])
             for i in range(2)]
    phone = [
        R("phone", 0, 0, 300, 570, fill=(25, 25, 30, 255), r=46,
          outline=(130, 130, 145, 255), ow=6),
        R("display", 0, 0, 262, 510, fill=(40, 40, 58, 255), r=32),
        R("notch", 0, -236, 84, 16, fill=(10, 10, 12, 255), r=8),
    ]
    for i in range(4):
        color = ctx.accent2 if i % 2 else blue
        phone.append(C(f"bubble{i}", 0, -165 + i * 100, [
            R("bubble", 0, 0, 226, 76, fill=color, r=22),
            R("line1", -30, -12, 140, 11, fill=_a(WHITE, 230), r=5),
            R("line2", -55, 14, 90, 11, fill=_a(WHITE, 170), r=5),
        ], scripts=[S("pop_in", start=0.4 + i * 0.5, duration=0.3)]))
    items.append(C("handset", 0, 20, phone, scripts=[S("bob", dy=8, period=2.4)]))
    items += [heart(f"like{i}", 200 + ctx.rng.uniform(-20, 40), 200, 52,
                    _a((235, 40, 80), 240),
                    scripts=[S("rise_loop", distance=420, period=2.4,
                               phase=i / 4, sway=18)])
              for i in range(4)]
    return items


def weather(ctx):
    cloud = (200, 205, 218, 255)
    items = [R(f"drop{i}", ctx.rng.uniform(-200, 200), -40, 7, 42,
               fill=(120, 170, 255, 230), r=3, rotation=10,
               scripts=[S("fall_loop", distance=360, period=0.9,
                          phase=ctx.rng.random())])
             for i in range(20)]
    items.append(P("bolt", 30, 120, 120, 230,
                   [(0.55, 0), (0.15, 0.55), (0.45, 0.55), (0.3, 1), (0.9, 0.38),
                    (0.55, 0.38), (0.75, 0)], fill=GOLD, glow=18,
                   scripts=[S("flicker", period=1.3, duty=0.12, low=0.0)]))
    items.append(C("cloud", 0, -150, [
        E("puff_l", -125, 25, 230, 170, fill=cloud),
        E("puff_m", 0, -35, 270, 230, fill=cloud),
        E("puff_r", 135, 25, 230, 180, fill=cloud),
        R("puff_base", 0, 75, 470, 110, fill=cloud, r=55),
    ], scripts=[S("bob", dx=14, dy=0, period=3)]))
    return items


def politics(ctx):
    navy = (40, 60, 140, 255)
    ballot = C("ballot", 0, -250, [
        R("paper", 0, 0, 150, 190, fill=WHITE, r=8),
        P("check", 0, 10, 90, 70, [(0, 0.55), (0.18, 0.38), (0.4, 0.62),
                                   (0.82, 0), (1, 0.18), (0.4, 1)],
          fill=(40, 170, 80, 255)),
    ], z_index=1,
        scripts=[S("keys", prop="y", keys=[[0, 0], [0.7, 0], [1.4, 250]],
                   period=2.4),
                 S("keys", prop="alpha", keys=[[0, 0], [0.25, 1], [2.4, 1]],
                   period=2.4)])
    box = C("box", 0, 140, [
        R("front", 0, 0, 400, 300, fill=navy, r=14, outline=WHITE, ow=5),
        R("slot", 0, -150, 190, 18, fill=DARK, r=9),
        T("vote", "VOTE", 0, 30, 92, WHITE, ctx.font),
    ], z_index=2)
    return sparkles(ctx, 5, (420, 280)) + [ballot, box]


def news(ctx):
    waves = [A(f"wave{i}", 210, -10, 220, 260, -45, 45, ctx.accent, 12,
               scripts=[S("expand_loop", period=1.5, phase=i / 3,
                          start_scale=0.4, end_scale=1.5)])
             for i in range(3)]
    horn = C("megaphone", -80, -10, [
        R("handle", -55, 85, 34, 90, fill=(60, 60, 70, 255), r=8, rotation=12),
        R("back", -95, 0, 70, 100, fill=(230, 230, 236, 255), r=12),
        P("cone", 60, 0, 270, 250, [(0, 0.34), (1, 0), (1, 1), (0, 0.66)],
          fill=ctx.accent2),
        E("bell", 195, 0, 40, 250, fill=_a(ctx.accent2, 255),
          outline=_a(WHITE, 200), ow=5),
    ], scripts=[S("wobble", amplitude=4, period=0.5)])
    ticker_text = "  BREAKING NEWS  •" * 8
    ticker = C("ticker", 0, 255, [
        R("band", 0, 0, 1200, 84, fill=ctx.accent),
        C("scroll", 0, 0, [T("ticker_text", ticker_text, 0, 0, 40, DARK, ctx.font)],
          scripts=[S("keys", prop="x", keys=[[0, 0], [3.0, -ctx.ticker_step]],
                     ease="linear", period=3.0)]),
    ])
    return waves + [horn, ticker]

# --------------------------------------------------------------- picking ---


def _words(*names):
    return re.compile(r"\b(" + "|".join(names) + r")\b", re.I)


# First match wins, so specific beats general (an NBA contract is
# basketball, not money; the Grammys are awards, not music).
VISUALS = [
    ("football", football, _words(
        "nfl", "football", "quarterback", "qb", "touchdowns?", "super bowl",
        "receiver", "field goal", "chiefs", "eagles", "cowboys", "49ers",
        "packers", "patriots", "bills", "ravens", "steelers", "jets",
        "giants", "bears", "lions", "vikings", "rams", "chargers", "raiders",
        "broncos", "dolphins", "bengals", "browns", "texans", "colts",
        "jaguars", "titans", "commanders", "saints", "falcons", "panthers",
        "buccaneers", "bucs", "seahawks")),
    ("basketball", basketball, _words(
        "nba", "wnba", "basketball", "lakers", "celtics", "warriors", "knicks",
        "bulls", "nets", "bucks", "suns", "mavericks", "mavs", "nuggets",
        "clippers", "76ers", "sixers", "spurs", "rockets", "thunder",
        "cavaliers", "cavs", "pistons", "pacers", "raptors", "pelicans",
        "grizzlies", "timberwolves", "blazers", "hornets", "wizards", "lebron",
        "dunk", "march madness")),
    ("soccer", soccer, _words(
        "soccer", "mls", "fifa", "premier league", "la liga", "champions league",
        "world cup", "messi", "ronaldo", "uefa", "arsenal", "chelsea",
        "liverpool", "manchester", "barcelona", "real madrid", "inter miami")),
    ("trophy", trophy, _words(
        "awards?", "oscars?", "emmys?", "grammys?", "golden globes?", "tony",
        "wins best", "nominated", "nominations?", "honored", "hall of fame",
        "vmas", "amas", "champions?", "championship", "mvp",
        "world series", "stanley cup", "medal", "olympics?")),
    ("love", love, _words(
        "married", "marry", "marries", "wedding", "engaged", "engagement",
        "dating", "divorce", "divorcing", "split", "splits", "breakup",
        "romance", "couple", "boyfriend", "girlfriend", "husband", "wife",
        "pregnant", "baby")),
    ("music", music, _words(
        "album", "song", "single", "tour", "concert", "rapper", "singer",
        "band", "music", "billboard", "setlist", "festival", "coachella",
        "spotify", "dj", "ep", "halftime show")),
    ("movie", movie, _words(
        "movie", "film", "box office", "trailer", "sequel", "director",
        "cinema", "theaters?", "premiere", "marvel", "pixar", "remake",
        "franchise", "blockbuster", "casting", "cast")),
    ("tv", tv, _words(
        "tv", "series", "season", "episode", "show", "sitcom", "finale",
        "renewed", "canceled", "cancelled", "netflix", "hulu", "hbo",
        "streaming", "reality", "bachelor", "snl", "spinoff", "network",
        "late-night", "talk show")),
    ("money", money, _words(
        "million", "billion", "deal", "contract", "stocks?", "sales", "prices?",
        "earnings", "revenue", "salary", "net worth", "sells", "sold",
        "acquires?", "acquisition", "bankrupt", "bankruptcy", "\\$[0-9]+")),
    ("tech", tech, _words(
        "app", "ai", "iphone", "apple", "google", "tiktok", "instagram",
        "youtube", "phone", "tech", "video game", "xbox", "playstation",
        "nintendo", "viral", "social media", "streamer", "online")),
    ("weather", weather, _words(
        "storms?", "snowstorm", "rainstorm", "hurricane", "snow", "rain", "weather", "tornado",
        "heat wave", "flood", "blizzard", "forecast")),
    ("politics", politics, _words(
        "election", "vote", "voters", "congress", "senate", "president",
        "governor", "mayor", "white house", "campaign", "ballot", "supreme court")),
]
BUILDERS = {name: build for name, build, _ in VISUALS}
BUILDERS["news"] = news


def pick_visual(*texts, feed=None):
    text = " ".join(t for t in texts if t)
    for name, _, pattern in VISUALS:
        if pattern.search(text):
            return name
    return "trophy" if feed == "sports" else "news"
