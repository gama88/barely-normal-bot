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

# The comedic voice Claude writes in. Tune this to shape every post.
VOICE = """You write short-form comedy for "Barely Normal Entertainment", an
Instagram page about trending entertainment, pop culture, and sports news.

Voice: deadpan, a little absurd, extremely online but not cringe. Sharp
observations, unexpected angles. Think group-chat-funny, not late-night-
monologue funny. At most one emoji, and only if it genuinely lands.

Hard rules:
- Never punch down. Joke about situations, fame, and absurdity — not about
  someone's body, family, health, or identity.
- If the headline involves death, serious crime, illness, tragedy, or an
  ongoing court case about harm to a person, it is NOT joke material —
  mark it unusable instead of forcing a joke.
- No made-up facts. The joke must work with only what the headline says.
- Keep it clean enough for Instagram (no slurs, no explicit content).
"""

# Subreddit-style topic sources: Google News RSS sections (no API key needed)
NEWS_FEEDS = {
    "entertainment": "https://news.google.com/rss/headlines/section/topic/ENTERTAINMENT?hl=en-US&gl=US&ceid=US:en",
    "sports": "https://news.google.com/rss/headlines/section/topic/SPORTS?hl=en-US&gl=US&ceid=US:en",
    "top": "https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en",
}

# Headlines containing these words are skipped before Claude ever sees them.
BLOCKED_WORDS = {
    "dies", "died", "dead", "death", "killed", "kills", "murder", "shooting",
    "shot", "suicide", "assault", "abuse", "victim", "autopsy", "overdose",
    "crash", "funeral", "war", "hostage", "terror",
}

# Video settings for the Blender reel
REEL = {
    "width": 1080,
    "height": 1920,
    "fps": 30,
    "seconds": 7,
}
