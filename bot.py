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

POSTED_FILE = Path(__file__).parent / "posted.json"
GRAPH = "https://graph.instagram.com/v21.0"
USER_AGENT = "Mozilla/5.0 (barely-normal-bot/2.0)"
MAX_TOPICS_TO_TRY = 3
BLENDER_TIMEOUT_SECONDS = 3000

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",   # GitHub Actions
    r"C:\Windows\Fonts\arialbd.ttf",                          # local Windows
    r"C:\Windows\Fonts\impact.ttf",
]

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


def load_posted():
    if POSTED_FILE.exists():
        return set(json.loads(POSTED_FILE.read_text()))
    return set()


def save_posted(posted):
    POSTED_FILE.write_text(json.dumps(sorted(posted), indent=2))


def headline_key(title):
    normalized = re.sub(r"[^a-z0-9 ]", "", title.lower()).strip()
    return hashlib.sha1(normalized.encode()).hexdigest()[:16]


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


def pick_topics(headlines, posted):
    """Filter blocked/used headlines, keep feed variety, best first."""
    seen, picked = set(), []
    for h in headlines:
        key = headline_key(h["title"])
        words = set(re.findall(r"[a-z']+", h["title"].lower()))
        if key in posted or key in seen:
            continue
        if words & brand.BLOCKED_WORDS:
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
            "description": "Short punchy setup shown large on screen, max 60 chars",
        },
        "punchline": {
            "type": "string",
            "description": "The joke/take, max 120 chars",
        },
        "caption": {
            "type": "string",
            "description": "1-2 sentence Instagram caption continuing the bit",
        },
        "hashtags": {
            "type": "array",
            "items": {"type": "string"},
            "description": "5-8 relevant hashtags without the # symbol",
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
    return post


def canned_post(headline):
    """Offline stand-in for --dry-run without an API key."""
    hook = headline["title"]
    if len(hook) > 60:
        hook = hook[:60].rsplit(" ", 1)[0] + "…"
    return {
        "usable": True,
        "hook": hook,
        "punchline": "This is a dry-run placeholder joke. The real one comes from Claude.",
        "caption": "Dry-run caption. Nothing was posted.",
        "hashtags": ["memes", "entertainment", "trending"],
    }


# ---------------------------------------------------------------- render ---


def find_blender():
    if os.environ.get("BLENDER_PATH"):
        return os.environ["BLENDER_PATH"]
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
    except subprocess.TimeoutExpired:
        print("blender render timed out — falling back to static card")
        return None
    if result.returncode != 0 or "RENDER_OK" not in result.stdout:
        print("blender render failed — falling back to static card")
        print(result.stdout[-2000:])
        print(result.stderr[-2000:])
        return None

    raw = work_dir / "reel_final.mp4"
    final = work_dir / "reel_audio.mp4"
    # Instagram is happier with an audio stream present; add silence.
    mux = subprocess.run(
        ["ffmpeg", "-y", "-i", str(raw),
         "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
         "-c:v", "copy", "-c:a", "aac", "-shortest", str(final)],
        capture_output=True, text=True,
    )
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
    tags = " ".join(f"#{t.lstrip('#')}" for t in post["hashtags"])
    return f"{post['caption']}\n\n{tags}"


def post_to_instagram(kind, media_url, caption):
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

    deadline = time.time() + 600
    while time.time() < deadline:
        status = requests.get(
            f"{GRAPH}/{container_id}",
            params={"fields": "status_code", "access_token": token},
            timeout=30,
        )
        status.raise_for_status()
        code = status.json().get("status_code")
        if code == "FINISHED":
            break
        if code == "ERROR":
            raise RuntimeError("Instagram media container reported ERROR")
        time.sleep(10)
    else:
        raise RuntimeError("Timed out waiting for Instagram media container")

    publish = requests.post(
        f"{GRAPH}/{ig_user_id}/media_publish",
        data={"creation_id": container_id, "access_token": token},
        timeout=60,
    )
    publish.raise_for_status()
    return publish.json()["id"]


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
    media_id = post_to_instagram(kind, media_url, caption)
    posted = load_posted()
    posted.add(topic["key"])
    save_posted(posted)
    print(f"Posted! media id {media_id}")
    return True


def main():
    dry_run = "--dry-run" in sys.argv
    load_env_file()

    posted = load_posted()
    topics = pick_topics(fetch_headlines(), posted)
    if not topics:
        print("No usable headlines found today.")
        sys.exit(1)

    with tempfile.TemporaryDirectory() as tmp:
        for topic in topics[:MAX_TOPICS_TO_TRY]:
            try:
                if run_one(topic, Path(tmp), dry_run):
                    return
            except Exception as exc:
                print(f"warning: topic failed ({topic['title']!r}): {exc}")

    print("error: all attempted topics failed")
    sys.exit(1)


if __name__ == "__main__":
    main()
