"""Brand configuration for Barely Normal Entertainment.

Everything about the page's look and voice lives here — edit freely.
"""

HANDLE = "@barelynormalentertainment"
BRAND_NAME = "BARELY NORMAL"

# Visual identity (hex colors)
COLORS = {
    "bg_top": "#101018",       # dark gradient top
    "bg_bottom": "#05050a",    # dark gradient bottom
    "text": "#f5f5f2",         # near-white text
    "accent": "#c6ff00",       # acid green
    "accent2": "#ff3d81",      # hot pink
}

# The voice the post model writes in. Tune this to shape every post.
#
# Format (2026-10-31): news + question. The free on-machine model couldn't
# write jokes that land, so each post restates the news punchily and asks the
# audience a specific question — something small models do reliably, and
# comments are what Instagram rewards. In code, "hook" is the headline line
# and "punchline" holds the question (the renderer doesn't care).
VOICE = """You write posts for "Barely Normal Entertainment", an Instagram page
about trending entertainment, pop culture, and sports news.

Each post has two parts, shown on screen in a short video:
- HOOK: the news, restated in plain punchy words, like a sharp headline.
  It must say what the headline actually says — same people, same event,
  same direction. Never twist or guess at the meaning.
- QUESTION: one question to the audience about this news that people will
  want to answer in the comments.

What makes a good question:
- Specific to THIS story, not generic. Bad: "What do you think?" Good:
  "Would you rather get a surprise album or a full tour announcement?"
- Easy to answer in a few words: a choice between two options, a
  "would you", a ranking, a prediction, or a hot-take prompt.
- Invites opinions and friendly debate, not facts the reader must know.
- Light and fun in tone. Never mean, never about someone's looks, body,
  family, health, or identity.

Examples (do not reuse these):
  Headline: Netflix raises subscription prices again
  Hook: Netflix is raising prices again
  Question: At what monthly price would you finally cancel — $20, $25, or
  never?

  Headline: Lakers blow 20-point lead in overtime loss
  Hook: The Lakers blew a 20-point lead
  Question: Worst collapse you've ever watched live — this one or something
  worse?

  Headline: Pop star announces surprise 12th album
  Hook: A surprise 12th album just dropped
  Question: Day-one listener or waiting for the reviews?

Hard rules:
- If the headline involves death, serious crime, illness, tragedy, or an
  ongoing court case about harm to a person, mark it unusable.
- No made-up facts. Use only what the headline says — no dates, past roles,
  relationships, quotes, or numbers it doesn't give.
- Keep it clean enough for Instagram (no slurs, no explicit content).
- NO EMOJI in the hook or question — they're rendered with fonts that have
  no emoji glyphs. One emoji in the caption is fine.
- Keep it short: hook under 70 characters, question under 120.
"""

# Generic or hack phrasing small models fall back on. Any candidate
# containing one (case-insensitive substring) is dropped in code before the
# editor sees it.
BANNED_JOKE_PHRASES = (
    "printer", "landlord", "the dmv", "wifi", "wi-fi", "my rent", "the rent",
    "who knew", "just a vibe", "plot twist", "iconic", "slay",
    "main character", "rent free", "rent-free", "said no one",
    "in this economy", "losing it", "we're all",
    "what do you think", "what are your thoughts", "thoughts?",
    "let us know", "sound off", "drop a comment",
)

# Topic sources: Google News RSS sections (no API key needed)
NEWS_FEEDS = {
    "entertainment": "https://news.google.com/rss/headlines/section/topic/ENTERTAINMENT?hl=en-US&gl=US&ceid=US:en",
    "sports": "https://news.google.com/rss/headlines/section/topic/SPORTS?hl=en-US&gl=US&ceid=US:en",
    "top": "https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en",
}

# --- Tragedy pre-filter -----------------------------------------------------
# Headlines matching these are dropped before the model ever sees them. Its
# own "usable: false" judgement is the second layer, not the only one.
#
# Two lists because matching mode matters:
#   BLOCKED_WORDS    — exact whole-word match (safe for short/ambiguous words)
#   BLOCKED_PREFIXES — token.startswith() (catches inflections: murdered,
#                      murdering, murders). Only stems with no benign English
#                      word sharing the prefix belong here — e.g. "war" must
#                      NOT be a prefix or it would block "Warriors".
BLOCKED_WORDS = {
    # death
    "die", "dies", "died", "dying", "dead", "death", "deaths",
    "kill", "kills", "killed", "killing", "killings", "killer", "killers",
    "fatal", "fatally", "fatality", "fatalities", "deceased", "passing",
    # violence / crime
    "shot", "shots", "gunman", "gunmen", "gunfire", "assault", "assaulted",
    "attack", "attacked", "attacker", "abuse", "abused", "abusive",
    "victim", "victims", "arrested", "charged", "convicted", "sentenced",
    "guilty", "verdict", "trial", "lawsuit", "indicted", "indictment",
    "prison", "jailed", "manslaughter", "assailant",
    "rape", "raped", "rapes", "rapist", "rapists", "harassment",
    "harassed", "grooming", "predator", "lawsuits", "sued", "sues",
    "accused", "allegation", "allegations", "alleged", "allegedly",
    # disaster
    "crash", "crashes", "crashed", "collision", "explosion", "explosions",
    "wildfire", "earthquake", "hurricane", "flood", "floods", "famine",
    "war", "wars", "warfare", "hostage", "hostages", "refugee", "refugees",
    "evacuated", "evacuation", "wounded", "injured", "injuries", "injury",
    # health / grief
    "cancer", "tumor", "illness", "hospitalized", "hospitalised", "coma",
    "diagnosis", "diagnosed", "funeral", "memorial", "mourns", "mourning",
    "grief", "grieving", "obituary", "tribute", "tributes", "condolences",
    "missing", "disappearance", "rescued",
}

BLOCKED_PREFIXES = (
    "murder",       # murder, murdered, murdering, murders, murderer
    "homicid",      # homicide, homicidal
    "suicid",       # suicide, suicidal
    "terror",       # terror, terrorist, terrorism, terrorized
    "kidnap",       # kidnap, kidnapped, kidnapping
    "stab",         # stab, stabbed, stabbing  (no benign "stab*" in headlines)
    "shooting",     # shooting, shootings
    "overdos",      # overdose, overdosed, overdoses
    "autops",       # autopsy, autopsies
    "massacr",      # massacre, massacred
    "traffick",     # trafficking, trafficked
    "molest",       # molest, molested, molestation
    "abduct",       # abduct, abducted, abduction
    "tragic", "tragedy", "tragedies",
    "bombing",      # bombing, bombings ("bomb" alone hits "bombshell")
    "euthan",       # euthanasia, euthanized
)

# Euphemisms for death that contain no blocked word on their own — e.g. a
# real headline seen in testing: "...before ending life with medical
# assistance". Matched as plain substrings of the lowercased headline.
# Stories about someone's looks almost always produce jokes that mock their
# looks (a test run picked "she looks like she survived a tornado" about an
# actress's new hair). Skip them up front instead of trusting the model.
APPEARANCE_WORDS = {
    "hair", "haircut", "hairstyle", "hairdo", "curly", "curls", "bald",
    "balding", "blonde", "brunette", "transformation", "unrecognizable",
    "weight", "body", "bodies", "figure", "physique", "bikini", "swimsuit",
    "makeup", "wrinkles", "aging", "ageing", "botox", "facelift", "surgery",
    "slimmed", "slimmer", "thinner", "pounds",
}

BLOCKED_PHRASES = (
    "weight loss", "lost weight", "plastic surgery", "no makeup",
    "makeup free", "makeup-free", "new look", "unrecognizable",
    "ending life", "ended life", "ends life", "end her life", "end his life",
    "end their life", "ended her life", "ended his life", "ended their life",
    "end of life", "medical assistance in dying", "assisted dying",
    "passed away", "passes away", "pass away", "laid to rest", "rest in peace",
    "final public appearance", "last public appearance", "lost her battle",
    "lost his battle", "lost their battle", "life support", "in memoriam",
)

# Video settings for the Blender reel
REEL = {
    "width": 1080,
    "height": 1920,
    "fps": 30,
    "seconds": 7,
}

# Hard limits enforced in code (not just requested of the model)
# The model is asked for <70 but small models overshoot; clipping mid-sentence
# reads badly on screen, so allow headroom (the renderers auto-shrink the font).
MAX_HOOK_CHARS = 90
MAX_PUNCH_CHARS = 160   # asked for <120; same overshoot headroom as the hook
MAX_CAPTION_CHARS = 2000     # Instagram hard limit is 2200 incl. hashtags
MAX_HASHTAGS = 25            # Instagram hard limit is 30
