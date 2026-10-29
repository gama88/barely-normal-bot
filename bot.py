"""Barely Normal Entertainment — daily original-content Instagram bot.

Pipeline (runs once per day on GitHub Actions):
  1. Pull trending headlines from Google News RSS (no API key needed)
  2. Claude writes an original joke/take in the brand voice (brand.py)
  3. Blender renders a branded vertical reel (blender_scene.py);
     falls back to a Pillow static card if Blender is unavailable/fails
  4. Media is uploaded to Cloudinary (Instagram needs a public URL)
  5. Published to Instagram via the official Graph API (Instagram Login flow)
  6. Topic recorded in posted.json so it's never reused

Usage:
    python bot.py            # post for real (needs env vars / .env)
    python bot.py --dry-run  # write copy + render locally, publish nothing
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
GRAPH = "https://graph.instagram.com/v21.0"
USER_AGENT = "Mozilla/5.0 (barely-normal-bot/2.0)"
MAX_TOPICS_TO_TRY = 3
BLENDER_TIMEOUT_SECONDS = 3000
FFMPEG_TIMEOUT_SECONDS = 300
CONTAINER_POLL_SECONDS = 600
MAX_CONSECUTIVE_POLL_ERRORS = 3

REQUIRED_ENV = ("IG_ACCESS_TOKEN", "IG_USER_ID", "CLOUDINARY_URL",
                "ANTHROPIC_API_KEY")

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
    """Fail fast before spending a Claude call and a multi-minute render."""
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
    tokens = re.findall(r"[a-z]+", title.lower().replace("'", "").replace("\u2019", ""))
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


# ----------------------------------------------------------------- claude ---

POST_SCHEMA = {
    "type": "object",
    "properties": {
        "usable": {
            "type": "boolean",
            "description": "false if this headline is not appropriate joke material",
        },
        "hook": {
            "type": "string",
            "maxLength": brand.MAX_HOOK_CHARS,
            "description": "Short punchy setup shown large on screen. No emoji.",
        },
        "punchline": {
            "type": "string",
            "maxLength": brand.MAX_PUNCH_CHARS,
            "description": "The joke/take. No emoji.",
        },
        "caption": {
            "type": "string",
            "maxLength": 600,
            "description": "1-2 sentence Instagram caption continuing the bit",
        },
        "hashtags": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": brand.MAX_HASHTAGS,
            "description": "5-8 relevant single-word hashtags without the # symbol",
        },
    },
    "required": ["usable", "hook", "punchline", "caption", "hashtags"],
    "additionalProperties": False,
}


def write_post(headline):
    """Ask Claude for the joke. Returns dict or None if headline unusable."""
    import anthropic

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
    response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=1024,
        system=brand.VOICE,
        messages=[{
            "role": "user",
            "content": (
                "Today's trending headline:\n"
                f"\"{headline['title']}\" (category: {headline['feed']})\n\n"
                "Write the post. If this headline shouldn't be joked about "
                "per your rules, set usable to false."
            ),
        }],
        output_config={"format": {"type": "json_schema", "schema": POST_SCHEMA}},
    )
    text = next(b.text for b in response.content if b.type == "text")
    post = json.loads(text)
    if not post.get("usable"):
        print(f"claude declined headline: {headline['title']!r}")
        return None

    # Enforce limits in code — schema descriptions alone don't guarantee them.
    post["hook"] = clean_text(post["hook"], brand.MAX_HOOK_CHARS)
    post["punchline"] = clean_text(post["punchline"], brand.MAX_PUNCH_CHARS)
    if not post["hook"] or not post["punchline"]:
        print("claude returned empty hook/punchline after cleaning")
        return None
    return post


def canned_post(headline):
    """Offline stand-in for --dry-run without an API key."""
    return {
        "usable": True,
        "hook": clean_text(headline["title"], brand.MAX_HOOK_CHARS),
        "punchline": "Dry-run placeholder. The real joke comes from Claude.",
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


def upload_to_cloudinary(path, kind):
    import cloudinary
    import cloudinary.uploader

    cloudinary.config(cloudinary_url=os.environ["CLOUDINARY_URL"])
    result = cloudinary.uploader.upload_large(
        str(path),
        resource_type="video" if kind == "video" else "image",
        folder="ig-bot",
    )
    return result["secure_url"]


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


def run_one(topic, work_dir, dry_run):
    if dry_run and not os.environ.get("ANTHROPIC_API_KEY"):
        post = canned_post(topic)
    else:
        post = write_post(topic)
    if post is None:
        return False

    media = render_reel(post, work_dir)
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

    if dry_run:
        out_dir = Path(__file__).parent / "out"
        out_dir.mkdir(exist_ok=True)
        kept = out_dir / f"preview{media.suffix}"
        shutil.copy(media, kept)
        print(f"DRY RUN — preview saved to {kept}, nothing posted.")
        return True

    media_url = upload_to_cloudinary(media, kind)

    def record():
        # Persist BEFORE publishing: a lost dedupe record is worse than a
        # burned topic, because it can produce a duplicate post later.
        posted = load_posted()
        posted.add(topic["key"])
        save_posted(posted)
        insights.add_record(topic, post, kind, caption)

    media_id = post_to_instagram(kind, media_url, caption,
                                 before_publish=record)
    print(f"Posted! media id {media_id}")
    # The post is live. Nothing below may raise, or main() would treat this
    # as a failed topic and publish a second post.
    try:
        insights.set_media_id(topic["key"], media_id)
    except Exception as exc:
        print(f"warning: couldn't save media id ({exc}); it will be "
              f"recovered from the caption on the next run")
    return True


def main():
    dry_run = "--dry-run" in sys.argv
    load_env_file()
    if not dry_run:
        require_env()
        check_token()
        refresh_token()
        try:
            insights.collect(os.environ["IG_ACCESS_TOKEN"])
        except Exception as exc:   # analytics must never block posting
            print(f"warning: insights collection failed: {exc}")

    posted = load_posted()
    topics = pick_topics(fetch_headlines(), posted)
    if not topics:
        print("No usable headlines found today.")
        sys.exit(1)

    with tempfile.TemporaryDirectory() as tmp:
        for index, topic in enumerate(topics[:MAX_TOPICS_TO_TRY]):
            # A fresh directory per attempt: sharing one lets a stale render
            # from a failed attempt be published with the next topic's caption.
            work_dir = Path(tmp) / f"attempt{index}"
            work_dir.mkdir(parents=True, exist_ok=True)
            try:
                if run_one(topic, work_dir, dry_run):
                    return
            except PublishedError as exc:
                print(f"error: {exc}")
                print("Stopping: a publish was already issued this run.")
                sys.exit(1)
            except Exception as exc:
                print(f"warning: topic failed ({topic['title']!r}): {exc}")

    print("error: all attempted topics failed")
    sys.exit(1)


if __name__ == "__main__":
    main()
