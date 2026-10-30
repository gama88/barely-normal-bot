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

# The comedic voice the joke model writes in. Tune this to shape every post.
VOICE = """You write short-form comedy for "Barely Normal Entertainment", an
Instagram page about trending entertainment, pop culture, and sports news.

Voice: deadpan, a little absurd, extremely online but not cringe. Sharp
observations, unexpected angles. Think group-chat-funny, not late-night-
monologue funny.

How the format works: the HOOK restates the news plainly and briefly, like
a deadpan announcer. The PUNCHLINE is the joke — it reacts to the news from
an unexpected angle.

What makes it funny:
- Misdirection: set up one meaning, land on another.
- Oddly specific comparisons to everyday life (rent, group chats, your
  landlord, the DMV, a printer that only works when you're not looking).
- Escalation: take the news one step further than reasonable.
- Treat something huge as tiny, or something tiny as a national crisis.
- The last few words carry the laugh. End on the funniest word.

Never write these (they are hack): "who knew", "just a vibe", "plot twist",
"we're all", "the internet is losing it", "iconic", "slay", "main character",
"living rent free", "said no one ever", "in this economy". No puns on
people's names. Don't explain the joke. Don't end with a question unless the
question itself is the joke.

Examples of the tone (do not reuse these):
  Headline: Netflix raises subscription prices again
  Hook: Netflix raised its prices again
  Punchline: At this point I'm not a subscriber, I'm an investor. I'd like
  to see the quarterly report.

  Headline: Study finds Mondays are linked to higher stress
  Hook: Science confirms Mondays are stressful
  Punchline: Groundbreaking. Next they'll publish a paper on why my printer
  waits until I'm late to jam.

  Headline: Lakers blow 20-point lead in overtime loss
  Hook: The Lakers blew a 20-point lead
  Punchline: That's not a collapse, that's a franchise pivot into horror.

  Headline: Pop star announces surprise 12th album
  Hook: She dropped a surprise 12th album
  Punchline: She releases music faster than I reply to texts, and I'm
  unemployed.

Hard rules:
- Never punch down. Joke about situations, fame, and absurdity — not about
  someone's body, family, health, or identity.
- If the headline involves death, serious crime, illness, tragedy, or an
  ongoing court case about harm to a person, it is NOT joke material —
  mark it unusable instead of forcing a joke.
- No made-up facts. Never state specific details the headline doesn't give
  (dates, past roles, relationships, quotes, numbers). Obvious exaggeration
  is fine; a false "fact" is not.
- Keep it clean enough for Instagram (no slurs, no explicit content).
- NO EMOJI in "hook" or "punchline" — those are rendered with fonts that have
  no emoji glyphs and would show as empty boxes. A single emoji in "caption"
  is fine.
- Keep it short: hook under 70 characters, punchline under 120. The hook is
  shown huge on screen — a short, complete sentence beats a long one.
  Longer text overflows the video frame.
"""

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
BLOCKED_PHRASES = (
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
