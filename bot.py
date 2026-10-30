"""Barely Normal Entertainment — daily original-content Instagram bot.

Pipeline (runs once per day on GitHub Actions), in two phases:

  prepare:
    1. Pull trending headlines from Google News RSS (no API key needed)
    2. An open-source LLM running on the CI machine writes an original
       joke/take in the brand voice (brand.py)
    3. Blender renders a branded vertical reel (blender_scene.py);
       falls back to a Pillow static card if Blender is unavailable/fails
    4. Media goes into site/ and the post is saved to pending.json

  (the workflow deploys site/ to GitHub Pages — Instagram's API only
   accepts media from a public URL)

  publish:
    5. Published to Instagram via the official Graph API (Instagram Login)
    6. Topic recorded in posted.json / history.json so it's never reused

Usage:
    python bot.py --dry-run             # write + render locally, post nothing
    python bot.py --prepare             # phase 1 (CI)
    python bot.py --publish <base_url>  # phase 2 (CI), base_url = Pages URL
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

import brand
import card_fallback
import insights

POSTED_FILE = Path(__file__).parent / "posted.json"
PENDING_FILE = Path(__file__).parent / "pending.json"
SITE_DIR = Path(__file__).parent / "site"
URL_WAIT_SECONDS = 300
GRAPH = "https://graph.instagram.com/v21.0"
USER_AGENT = "Mozilla/5.0 (barely-normal-bot/2.0)"
MAX_TOPICS_TO_TRY = 3
BLENDER_TIMEOUT_SECONDS = 3000
FFMPEG_TIMEOUT_SECONDS = 300
CONTAINER_POLL_SECONDS = 600
MAX_CONSECUTIVE_POLL_ERRORS = 3

REQUIRED_ENV = ("IG_ACCESS_TOKEN", "IG_USER_ID")

# Jokes are written by an open-source model (Qwen3-4B-Instruct, Apache-2.0)
# running on the GitHub Actions machine itself via llama.cpp's llama-server,
# which the workflow starts before the bot runs. No API, key, account, or
# cost — nothing external that can be retired or start charging.
LLM_URL = os.environ.get("LLM_URL",
                         "http://127.0.0.1:8080/v1/chat/completions")
LLM_ATTEMPTS = 2
LLM_TIMEOUT_SECONDS = 300    # CPU inference: generous, it's a ~4B model

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",   # GitHub Actions
    r"C:\Windows\Fonts\arialbd.ttf",                          # local Windows
    r"C:\Windows\Fonts\impact.ttf",
]

# Fonts used for rendering have no emoji glyphs — emoji would draw as empty
# boxes, so they are stripped from any text that gets rasterized.
EMOJI_RE = re.compile(
    "["
    "\U0001F000-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U00002B00-\U00002BFF"
    "\U0000FE00-\U0000FE0F"
    "\U0001F1E6-\U0001F1FF"
    "]+"
)


class PublishedError(RuntimeError):
    """Raised after Instagram has (or may have) accepted a publish.

    Signals that the run must stop rather than try another topic — retrying
    would put a second post on the account the same day.
    """


# --------------------------------------------------------------- helpers ---


def load_env_file():
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def require_env():
    """Fail fast before spending a model call and a multi-minute render."""
    missing = [k for k in REQUIRED_ENV if not os.environ.get(k)]
    if missing:
        print(f"error: missing required environment variables: "
              f"{', '.join(missing)}")
        sys.exit(1)


def check_token():
    """Verify the Instagram token works before doing any expensive work."""
    token = os.environ["IG_ACCESS_TOKEN"]
    try:
        resp = requests.get(f"{GRAPH}/me",
                            params={"fields": "user_id,username",
                                    "access_token": token},
                            timeout=30)
    except requests.RequestException as exc:
        print(f"warning: couldn't reach Instagram to check token: {exc}")
        return
    if resp.ok:
        print(f"token ok for @{resp.json().get('username', '?')}")
        return
    error = resp.json().get("error", {}) if resp.content else {}
    if error.get("code") == 190:
        print("error: Instagram access token is expired or invalid. Generate a "
              "new one in the Meta app dashboard (Use cases -> Customize -> "
              "API setup with Instagram login -> Generate token) and update "
              "the IG_ACCESS_TOKEN secret.")
    else:
        print(f"error: token check failed: {resp.status_code} {error}")
    sys.exit(1)


def refresh_token():
    """Extend the long-lived token's 60-day expiry. Never fails the run.

    Refreshing extends the expiry from today, so a daily run keeps the token
    alive indefinitely — as long as Instagram keeps returning the same token
    string. If it ever returns a different one, the secret must be updated.
    """
    token = os.environ["IG_ACCESS_TOKEN"]
    try:
        resp = requests.get("https://graph.instagram.com/refresh_access_token",
                            params={"grant_type": "ig_refresh_token",
                                    "access_token": token},
                            timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        # Expected for tokens under 24h old; harmless otherwise.
        print(f"note: token refresh skipped ({exc})")
        return
    days = int(data.get("expires_in", 0)) // 86400
    if data.get("access_token") and data["access_token"] != token:
        print(f"WARNING: Instagram issued a NEW token on refresh. The current "
              f"secret still works for now, but update IG_ACCESS_TOKEN within "
              f"{days} days or posting will stop.")
    else:
        print(f"token refreshed, valid for {days} more days")


def load_posted():
    if POSTED_FILE.exists():
        try:
            return set(json.loads(POSTED_FILE.read_text()))
        except json.JSONDecodeError:
            print("warning: posted.json unreadable, treating as empty")
    return set()


def save_posted(posted):
    POSTED_FILE.write_text(json.dumps(sorted(posted), indent=2))


def headline_key(title):
    normalized = re.sub(r"[^a-z0-9 ]", "", title.lower()).strip()
    return hashlib.sha1(normalized.encode()).hexdigest()[:16]


def clean_text(text, limit):
    """Strip emoji, collapse whitespace, and hard-clamp to `limit` chars."""
    text = EMOJI_RE.sub("", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > limit:
        clipped = text[:limit].rsplit(" ", 1)[0]
        text = (clipped or text[:limit]).rstrip(",;:. ") + "…"
    return text


# -------------------------------------------------------------- trending ---


def fetch_headlines():
    """Return [{'title', 'feed'}] across the configured news feeds."""
    headlines = []
    for feed_name, url in brand.NEWS_FEEDS.items():
        try:
            resp = requests.get(url, headers={"User-Agent": USER_AGENT},
                                timeout=30)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
        except (requests.RequestException, ET.ParseError) as exc:
            print(f"warning: feed '{feed_name}' failed: {exc}")
            continue
        for item in root.findall(".//item")[:15]:
            title = (item.findtext("title") or "").strip()
            if not title:
                continue
            # Google News titles end with " - Outlet Name"; drop the outlet
            title = title.rsplit(" - ", 1)[0].strip()
            headlines.append({"title": title, "feed": feed_name})
    return headlines


def is_blocked(title):
    """True if the headline looks like tragedy/crime and must not be a joke."""
    # Apostrophes are stripped rather than kept in the token, so possessives
    # ("victim's") normalize to the base word and still match.
    lowered = title.lower().replace("'", "").replace("\u2019", "")
    normalized = " ".join(re.findall(r"[a-z]+", lowered))
    if any(phrase in normalized for phrase in brand.BLOCKED_PHRASES):
        return True
    tokens = normalized.split()
    for tok in tokens:
        if tok in brand.BLOCKED_WORDS:
            return True
        if tok.startswith(brand.BLOCKED_PREFIXES):
            return True
    return False


def pick_topics(headlines, posted):
    """Filter blocked/used headlines, dedupe, best first."""
    seen, picked = set(), []
    for h in headlines:
        key = headline_key(h["title"])
        if key in posted or key in seen:
            continue
        if is_blocked(h["title"]):
            continue
        seen.add(key)
        picked.append({**h, "key": key})
    return picked


# ------------------------------------------------------------ joke writer ---

# A small model's average joke is weak but its best-of-several is much
# better, so one call writes several distinct jokes and a second call acts as
# a strict editor that picks one (or rejects them all).
JOKE_CANDIDATES = 5
DEFAULT_HASHTAGS = ["memes", "funny", "entertainment", "popculture", "trending"]

WRITER_FORMAT = f"""
Write {JOKE_CANDIDATES} different jokes about the headline. Each one must use
a DIFFERENT angle or technique — not five versions of the same joke.

Reply with ONLY a JSON object, no other text:
{{"usable": true, "jokes": [{{"hook": "...", "punchline": "..."}}, ...]}}
- hook: under 70 characters, no emoji
- punchline: under 120 characters, no emoji
If the headline is not joke material per the rules, reply exactly:
{{"usable": false, "jokes": []}}
"""

EDITOR_SYSTEM = """You are the head writer of a comedy Instagram page. You are
ruthless: most jokes are not good enough, and posting a weak or risky joke is
worse than posting nothing.

Pick the single funniest joke. Reject (never pick) any joke that:
- states a specific fact the headline doesn't give (dates, past roles,
  relationships, quotes, numbers) — exaggeration is fine, false facts aren't
- is mean about someone's body, family, health, or identity
- explains itself, or uses a hack phrase ("who knew", "just a vibe",
  "plot twist", "iconic", "main character", "in this economy")
- doesn't actually have a punchline
If none of them is genuinely funny AND safe, choose 0.

Then write a 1-2 sentence Instagram caption that continues the bit without
repeating the punchline (one emoji allowed), and 5-8 single-word hashtags
without the # symbol.

Reply with ONLY a JSON object, no other text:
{"best": <joke number, or 0>, "caption": "...", "hashtags": ["..."]}"""


def call_model(messages, temperature=0.9, max_tokens=400):
    """Ask the local llama-server for a completion. Returns the reply text.

    llama-server speaks the OpenAI chat format; `response_format` json_object
    makes it constrain sampling to valid JSON. Thinking is switched off: it
    costs minutes on a CPU and doesn't help a two-line joke.
    """
    last_error = None
    for attempt in range(1, LLM_ATTEMPTS + 1):
        try:
            resp = requests.post(
                LLM_URL,
                headers={"Content-Type": "application/json"},
                json={"messages": messages,
                      "response_format": {"type": "json_object"},
                      "temperature": temperature, "top_p": 0.95,
                      "max_tokens": max_tokens,
                      "chat_template_kwargs": {"enable_thinking": False}},
                timeout=LLM_TIMEOUT_SECONDS,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except (requests.RequestException, KeyError, IndexError,
                ValueError) as exc:
            print(f"warning: model call {attempt} failed: {exc}")
            last_error = exc
    raise RuntimeError(f"joke model unavailable: {last_error}")


def load_json_object(text):
    """Parse a JSON object from a model reply, tolerating fences/prose."""
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return data if isinstance(data, dict) else None


def as_bool(value):
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return value is True


def parse_candidates(text):
    """Writer reply -> (usable, [{'hook', 'punchline'}, ...])."""
    data = load_json_object(text)
    if data is None:
        print("writer reply had no valid JSON")
        return False, []
    if not as_bool(data.get("usable")):
        return False, []
    jokes = []
    for item in data.get("jokes") or []:
        if not isinstance(item, dict):
            continue
        # Enforce limits in code — models don't reliably count characters.
        hook = clean_text(str(item.get("hook") or ""), brand.MAX_HOOK_CHARS)
        punch = clean_text(str(item.get("punchline") or ""),
                           brand.MAX_PUNCH_CHARS)
        if not (hook and punch):
            continue
        text = f"{hook} {punch}".lower().replace("’", "'")
        hack = next((p for p in brand.BANNED_JOKE_PHRASES if p in text), None)
        if hack:
            print(f"  dropped a candidate for using {hack!r}")
            continue
        jokes.append({"hook": hook, "punchline": punch})
    return True, jokes


def parse_pick(text, count):
    """Editor reply -> (index or None for "reject all", caption, hashtags).

    Raises ValueError if the reply is unusable, so the caller can fall back.
    """
    data = load_json_object(text)
    if data is None:
        raise ValueError("editor reply had no valid JSON")
    try:
        best = int(data.get("best"))
    except (TypeError, ValueError):
        raise ValueError(f"editor gave no valid pick: {data.get('best')!r}")
    if best == 0:
        return None, "", []
    if not 1 <= best <= count:
        raise ValueError(f"editor pick {best} out of range 1-{count}")
    hashtags = data.get("hashtags")
    if isinstance(hashtags, str):
        hashtags = hashtags.replace(",", " ").split()
    if not isinstance(hashtags, list):
        hashtags = []
    return best - 1, str(data.get("caption") or ""), [str(t) for t in hashtags]


def write_post(headline, verbose=False):
    """Get the joke. Returns dict, or None if the headline is unusable."""
    news = (f"Headline: \"{headline['title']}\" "
            f"(category: {headline['feed']})")

    usable, jokes = parse_candidates(call_model(
        [{"role": "system", "content": brand.VOICE + "\n" + WRITER_FORMAT},
         {"role": "user", "content": news}],
        # 5 jokes + JSON overhead; at 700 the 9B model's longer jokes were
        # cut off mid-JSON and the whole batch was lost.
        temperature=1.0, max_tokens=1200))
    if not usable or not jokes:
        print(f"writer declined or failed on headline: {headline['title']!r}")
        return None
    if verbose:
        for n, j in enumerate(jokes, 1):
            print(f"  {n}. {j['hook']} / {j['punchline']}")

    numbered = "\n".join(f"{n}. HOOK: {j['hook']}\n   PUNCHLINE: {j['punchline']}"
                         for n, j in enumerate(jokes, 1))
    try:
        index, caption, hashtags = parse_pick(call_model(
            [{"role": "system", "content": EDITOR_SYSTEM},
             {"role": "user", "content": f"{news}\n\nJokes:\n{numbered}"}],
            temperature=0.2, max_tokens=300), len(jokes))
    except (ValueError, RuntimeError) as exc:
        # A broken editor shouldn't sink an otherwise good batch.
        print(f"warning: editor failed ({exc}); using the first joke")
        index, caption, hashtags = 0, "", []

    if index is None:
        print(f"editor rejected every joke for: {headline['title']!r}")
        return None
    chosen = jokes[index]
    if verbose:
        print(f"  -> editor picked #{index + 1}")
    return {
        "usable": True,
        "hook": chosen["hook"],
        "punchline": chosen["punchline"],
        "caption": caption or chosen["punchline"],
        "hashtags": hashtags or list(DEFAULT_HASHTAGS),
    }


def canned_post(headline):
    """Stand-in for --dry-run when no model server is running."""
    return {
        "usable": True,
        "hook": clean_text(headline["title"], brand.MAX_HOOK_CHARS),
        "punchline": "Dry-run placeholder. The real joke comes from the model.",
        "caption": "Dry-run caption. Nothing was posted.",
        "hashtags": ["memes", "entertainment", "trending"],
    }


# ---------------------------------------------------------------- render ---


def find_blender():
    override = os.environ.get("BLENDER_PATH")
    if override:
        # A stale BLENDER_PATH must not raise FileNotFoundError later; treat
        # a bad override as "no blender" so the card fallback still works.
        if os.path.exists(override):
            return override
        print(f"warning: BLENDER_PATH does not exist: {override}")
        return None
    return shutil.which("blender")


def render_reel(post, work_dir):
    """Render the Blender reel + add a silent audio track. None on failure."""
    blender = find_blender()
    if not blender:
        print("blender not found — falling back to static card")
        return None
    cfg = {
        "hook": post["hook"],
        "punchline": post["punchline"],
        "handle": brand.HANDLE,
        "colors": brand.COLORS,
        "font_candidates": FONT_CANDIDATES,
        "out_dir": str(work_dir),
        "seed": int(time.time()) % 100000,
        **brand.REEL,
    }
    cfg_path = work_dir / "scene_config.json"
    cfg_path.write_text(json.dumps(cfg))
    script = Path(__file__).parent / "blender_scene.py"
    try:
        result = subprocess.run(
            [blender, "-b", "--factory-startup", "-P", str(script),
             "--", str(cfg_path)],
            capture_output=True, text=True, timeout=BLENDER_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"blender render failed to run ({exc}) — falling back to card")
        return None
    if result.returncode != 0 or "RENDER_OK" not in result.stdout:
        print("blender render failed — falling back to static card")
        print(result.stdout[-2000:])
        print(result.stderr[-2000:])
        return None

    raw = work_dir / "reel_final.mp4"
    if not raw.exists():
        print("blender reported success but produced no file — using card")
        return None

    final = work_dir / "reel_audio.mp4"
    # Instagram is happier with an audio stream present; add silence.
    try:
        mux = subprocess.run(
            ["ffmpeg", "-y", "-i", str(raw),
             "-f", "lavfi",
             "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
             "-c:v", "copy", "-c:a", "aac", "-shortest", str(final)],
            capture_output=True, text=True, timeout=FFMPEG_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"warning: silent-audio mux unavailable ({exc}), using video as-is")
        return raw
    if mux.returncode != 0:
        print("warning: silent-audio mux failed, using video as-is")
        return raw
    return final


def render_card(post, work_dir):
    out = work_dir / "card.jpg"
    card_fallback.make_card(post["hook"], post["punchline"], str(out))
    return out


# ------------------------------------------------------------- instagram ---


def wait_for_public_url(url, kind):
    """Block until GitHub Pages is actually serving the file.

    deploy-pages returns before the CDN has the new site everywhere; handing
    Instagram the URL too early gets the container rejected.
    """
    expected = "video/" if kind == "video" else "image/"
    deadline = time.time() + URL_WAIT_SECONDS
    while time.time() < deadline:
        try:
            resp = requests.head(url, timeout=30, allow_redirects=True)
            ctype = resp.headers.get("Content-Type", "")
            if resp.status_code == 200 and ctype.startswith(expected):
                print(f"media live at {url} ({ctype})")
                return
            print(f"waiting for media: HTTP {resp.status_code} {ctype}")
        except requests.RequestException as exc:
            print(f"waiting for media: {exc}")
        time.sleep(10)
    raise RuntimeError(f"media never became available at {url}")


def build_caption(post):
    tags = []
    for raw in post.get("hashtags", []):
        # "pop culture" would post as #pop plus loose words — collapse it.
        tag = re.sub(r"[^0-9A-Za-z_]", "", str(raw).lstrip("#"))
        if tag:
            tags.append(f"#{tag}")
        if len(tags) >= brand.MAX_HASHTAGS:
            break
    caption = clean_text(post["caption"], brand.MAX_CAPTION_CHARS)
    full = f"{caption}\n\n{' '.join(tags)}".strip()
    return full[:2200]


def post_to_instagram(kind, media_url, caption, before_publish=None):
    """Create the media container, wait for it, then publish.

    `before_publish` runs immediately before the irreversible publish call so
    the caller can persist state first.
    """
    token = os.environ["IG_ACCESS_TOKEN"]
    ig_user_id = os.environ["IG_USER_ID"]

    if kind == "video":
        params = {"media_type": "REELS", "video_url": media_url,
                  "caption": caption, "access_token": token}
    else:
        params = {"image_url": media_url, "caption": caption,
                  "access_token": token}

    resp = requests.post(f"{GRAPH}/{ig_user_id}/media", data=params, timeout=60)
    resp.raise_for_status()
    container_id = resp.json()["id"]

    deadline = time.time() + CONTAINER_POLL_SECONDS
    errors = 0
    while time.time() < deadline:
        try:
            status = requests.get(
                f"{GRAPH}/{container_id}",
                params={"fields": "status_code", "access_token": token},
                timeout=30,
            )
            status.raise_for_status()
            errors = 0
        except requests.RequestException as exc:
            # A transient 5xx shouldn't discard a container that is still
            # processing normally.
            errors += 1
            if errors > MAX_CONSECUTIVE_POLL_ERRORS:
                raise
            print(f"warning: status poll failed ({exc}), retrying")
            time.sleep(10)
            continue
        code = status.json().get("status_code")
        if code == "FINISHED":
            break
        if code == "ERROR":
            raise RuntimeError("Instagram media container reported ERROR")
        time.sleep(10)
    else:
        raise RuntimeError("Timed out waiting for Instagram media container")

    if before_publish:
        before_publish()

    # Past this point Instagram may have created the post even if we fail to
    # read the response, so every error is raised as PublishedError to stop
    # the run instead of publishing a second topic.
    try:
        publish = requests.post(
            f"{GRAPH}/{ig_user_id}/media_publish",
            data={"creation_id": container_id, "access_token": token},
            timeout=120,
        )
        publish.raise_for_status()
        return publish.json()["id"]
    except Exception as exc:
        raise PublishedError(f"publish may have succeeded but failed to "
                             f"confirm: {exc}") from exc


# ------------------------------------------------------------------ main ---


def make_post(topic, work_dir, dry_run):
    """Write and render one post. Returns (post, kind, media, caption) or None."""
    started = time.time()
    try:
        post = write_post(topic)
        print(f"timing: joke {time.time() - started:.0f}s")
    except RuntimeError as exc:
        if not dry_run:
            raise
        # Locally there's usually no model server running; preview anyway.
        print(f"note: {exc} — using a placeholder joke for the preview")
        post = canned_post(topic)
    if post is None:
        return None

    started = time.time()
    media = render_reel(post, work_dir)
    print(f"timing: render {time.time() - started:.0f}s")
    kind = "video"
    if media is None:
        media = render_card(post, work_dir)
        kind = "image"

    caption = build_caption(post)
    print(f"topic:   {topic['title']}")
    print(f"hook:    {post['hook']}")
    print(f"punch:   {post['punchline']}")
    print(f"media:   {kind} -> {media}")
    print(f"caption:\n{caption}")
    return post, kind, media, caption


def stage_for_pages(topic, post, kind, media, caption):
    """Put the media in site/ for the Pages deploy and save the pending post."""
    if SITE_DIR.exists():
        shutil.rmtree(SITE_DIR)
    SITE_DIR.mkdir()
    # The filename is the topic key, so each day's URL is new and no CDN or
    # Instagram-side cache can serve yesterday's video under today's caption.
    filename = f"{topic['key']}{media.suffix}"
    shutil.copy(media, SITE_DIR / filename)
    (SITE_DIR / "index.html").write_text(
        "<!doctype html><title>Barely Normal</title>", encoding="utf-8")
    PENDING_FILE.write_text(json.dumps({
        "topic": topic, "post": post, "kind": kind,
        "caption": caption, "filename": filename,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"staged {filename} for publishing")


def prepare(dry_run):
    """Phase 1: pick a topic, write it, render it. Nothing is published here,
    so retrying the next topic after a failure is always safe."""
    if PENDING_FILE.exists():
        PENDING_FILE.unlink()

    topics = pick_topics(fetch_headlines(), load_posted())
    if not topics:
        print("No usable headlines found today.")
        sys.exit(1)

    with tempfile.TemporaryDirectory() as tmp:
        for index, topic in enumerate(topics[:MAX_TOPICS_TO_TRY]):
            # A fresh directory per attempt so a stale render can never be
            # picked up for the next topic.
            work_dir = Path(tmp) / f"attempt{index}"
            work_dir.mkdir(parents=True, exist_ok=True)
            try:
                made = make_post(topic, work_dir, dry_run)
                if made is None:
                    continue
                post, kind, media, caption = made
                if dry_run:
                    out_dir = Path(__file__).parent / "out"
                    out_dir.mkdir(exist_ok=True)
                    kept = out_dir / f"preview{media.suffix}"
                    shutil.copy(media, kept)
                    print(f"DRY RUN — preview saved to {kept}, nothing posted.")
                else:
                    stage_for_pages(topic, post, kind, media, caption)
                return
            except Exception as exc:
                print(f"warning: topic failed ({topic['title']!r}): {exc}")

    print("error: all attempted topics failed")
    sys.exit(1)


def publish(base_url):
    """Phase 2: post the staged media, now live on GitHub Pages.

    Exactly one attempt. If it fails before the publish call, nothing is
    posted and the topic stays unused for tomorrow.
    """
    if not PENDING_FILE.exists():
        print("error: nothing staged — run --prepare first")
        sys.exit(1)
    pending = json.loads(PENDING_FILE.read_text(encoding="utf-8"))
    topic, post = pending["topic"], pending["post"]
    kind, caption = pending["kind"], pending["caption"]
    url = f"{base_url.rstrip('/')}/{pending['filename']}"

    def record():
        # Persist BEFORE publishing: a lost dedupe record is worse than a
        # burned topic, because it can produce a duplicate post later.
        posted = load_posted()
        posted.add(topic["key"])
        save_posted(posted)
        insights.add_record(topic, post, kind, caption)

    try:
        wait_for_public_url(url, kind)
        media_id = post_to_instagram(kind, url, caption, before_publish=record)
    except PublishedError as exc:
        print(f"error: {exc}")
        print("The post may be live; it's recorded so it won't be repeated.")
        sys.exit(1)
    except Exception as exc:
        print(f"error: publish failed before posting: {exc}")
        sys.exit(1)

    print(f"Posted! media id {media_id}")
    # The post is live. Nothing below may raise.
    try:
        insights.set_media_id(topic["key"], media_id)
        PENDING_FILE.unlink()
    except Exception as exc:
        print(f"warning: post-publish bookkeeping failed ({exc}); the media "
              f"id will be recovered from the caption on the next run")


def main():
    args = sys.argv[1:]
    load_env_file()

    if "--jokes" in args:
        # Joke-quality check: show every candidate and the editor's pick for
        # several real headlines, without rendering anything.
        idx = args.index("--jokes")
        count = int(args[idx + 1]) if idx + 1 < len(args) else 5
        topics = pick_topics(fetch_headlines(), load_posted())[:count]
        for topic in topics:
            print(f"\n=== {topic['title']}  [{topic['feed']}]")
            started = time.time()
            post = write_post(topic, verbose=True)
            if post:
                print(f"  POST: {post['hook']} / {post['punchline']}")
                print(f"  CAPTION: {post['caption']}")
            print(f"  ({time.time() - started:.0f}s)")
    elif "--dry-run" in args:
        prepare(dry_run=True)
    elif "--prepare" in args:
        require_env()
        check_token()
        refresh_token()
        try:
            insights.collect(os.environ["IG_ACCESS_TOKEN"])
        except Exception as exc:   # analytics must never block posting
            print(f"warning: insights collection failed: {exc}")
        prepare(dry_run=False)
    elif "--publish" in args:
        idx = args.index("--publish")
        if idx + 1 >= len(args):
            print("usage: python bot.py --publish <pages_base_url>")
            sys.exit(2)
        require_env()
        publish(args[idx + 1])
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main()
