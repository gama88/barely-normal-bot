"""Post history + performance insights for the bot.

Every published post gets a record in history.json. On each daily run, posts
between 1 and 7 days old have their Instagram insights refreshed; after 7 days
the numbers are frozen as final. Over time this becomes the dataset for
figuring out which topics, hooks, and formats actually perform.

Usage:
    python insights.py            # refresh insights now, then print report
    python insights.py --report   # print report from history.json only

Requires the `instagram_business_manage_insights` permission on the token.
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import re

import requests

HISTORY_FILE = Path(__file__).parent / "history.json"

# This repo's Actions logs are public: requests error messages contain the
# full URL, access_token included, so strip it before printing.
_TOKEN_IN_URL = re.compile(r"(access_token=)[^&\s'\"]+")


def scrub(text):
    return _TOKEN_IN_URL.sub(r"\1[redacted]", str(text))


GRAPH = "https://graph.instagram.com/v21.0"

MIN_AGE = timedelta(hours=20)    # too-fresh numbers are noise
FINAL_AGE = timedelta(days=7)    # after this, stop refreshing

# Metric names per the Instagram Media Insights reference. `impressions` and
# `plays` are deprecated for media created after mid-2024 — don't add them.
REELS_METRICS = ["views", "reach", "likes", "comments", "shares", "saved",
                 "total_interactions", "ig_reels_avg_watch_time",
                 "reels_skip_rate"]
FEED_METRICS = ["views", "reach", "likes", "comments", "shares", "saved",
                "total_interactions"]
# Fallback if Meta rejects one of the newer metrics for a given media object.
CORE_METRICS = ["views", "reach", "likes", "comments", "shares", "saved"]


def now_utc():
    return datetime.now(timezone.utc)


def load_history():
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print("warning: history.json unreadable, starting fresh")
    return []


def save_history(history):
    HISTORY_FILE.write_text(json.dumps(history, indent=2, ensure_ascii=False),
                            encoding="utf-8")


def add_record(topic, post, kind, caption):
    """Append a record just before publishing. media_id is filled in after."""
    history = load_history()
    history.append({
        "key": topic["key"],
        "title": topic["title"],
        "feed": topic["feed"],
        "hook": post["hook"],
        "punchline": post["punchline"],
        "caption": caption,
        "kind": kind,
        "media_id": None,
        "posted_at": now_utc().isoformat(timespec="seconds"),
        "insights": None,
        "insights_at": None,
        "final": False,
    })
    save_history(history)


def set_media_id(key, media_id):
    history = load_history()
    for rec in reversed(history):
        if rec["key"] == key:
            rec["media_id"] = media_id
            break
    save_history(history)


# ------------------------------------------------------------ fetching ---


def _get(path, token, **params):
    resp = requests.get(f"{GRAPH}/{path}",
                        params={**params, "access_token": token}, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _parse_insights(payload):
    out = {}
    for item in payload.get("data", []):
        name = item.get("name")
        if "total_value" in item:
            out[name] = item["total_value"].get("value")
        elif item.get("values"):
            out[name] = item["values"][0].get("value")
    return out


def fetch_media_insights(media_id, kind, token):
    metrics = REELS_METRICS if kind == "video" else FEED_METRICS
    try:
        payload = _get(f"{media_id}/insights", token, metric=",".join(metrics))
    except requests.HTTPError as exc:
        if exc.response is None or exc.response.status_code != 400:
            raise
        payload = _get(f"{media_id}/insights", token,
                       metric=",".join(CORE_METRICS))
    return _parse_insights(payload)


def resolve_missing_ids(history, token):
    """Recover media_id for posts whose publish response was lost.

    That happens when the publish call times out after Instagram already
    created the post. Matching on the exact caption is reliable because each
    caption is generated fresh.
    """
    missing = [r for r in history if not r.get("media_id")]
    if not missing:
        return
    try:
        recent = _get("me/media", token, fields="id,caption,timestamp",
                      limit=50).get("data", [])
    except requests.RequestException as exc:
        print(f"warning: couldn't list recent media to recover ids: {scrub(exc)}")
        return
    by_caption = {m.get("caption"): m["id"] for m in recent if m.get("caption")}
    for rec in missing:
        media_id = by_caption.get(rec["caption"])
        if media_id:
            rec["media_id"] = media_id
            print(f"recovered media id for {rec['title']!r}")


def collect(token):
    """Refresh insights for posts in the 20h-7d window. Never raises."""
    history = load_history()
    if not history:
        return
    resolve_missing_ids(history, token)
    now = now_utc()
    refreshed = 0
    for rec in history:
        if rec.get("final") or not rec.get("media_id"):
            continue
        age = now - datetime.fromisoformat(rec["posted_at"])
        if age < MIN_AGE:
            continue
        try:
            rec["insights"] = fetch_media_insights(rec["media_id"], rec["kind"],
                                                   token)
        except requests.RequestException as exc:
            print(f"warning: insights failed for {rec['title']!r}: {scrub(exc)}")
            continue
        rec["insights_at"] = now.isoformat(timespec="seconds")
        if age >= FINAL_AGE:
            rec["final"] = True
        refreshed += 1
    save_history(history)
    print(f"insights: refreshed {refreshed} post(s)")


# -------------------------------------------------------------- report ---


def _rate(num, den):
    return (num or 0) / den if den else 0.0


def report(history=None):
    history = history if history is not None else load_history()
    rows = [r for r in history if r.get("insights")]
    if not rows:
        print("No insights collected yet — posts need ~1 day before numbers "
              "are available.")
        return

    rows.sort(key=lambda r: r["insights"].get("views") or 0, reverse=True)
    print(f"{'date':<11}{'kind':<6}{'views':>7}{'reach':>7}{'eng%':>7}"
          f"{'shr+sv':>8}{'watch':>7}  hook")
    for r in rows:
        ins = r["insights"]
        eng = _rate(ins.get("total_interactions"), ins.get("reach")) * 100
        boosts = (ins.get("shares") or 0) + (ins.get("saved") or 0)
        watch = ins.get("ig_reels_avg_watch_time")
        watch_s = f"{watch / 1000:.1f}s" if watch else "-"
        flag = "" if r.get("final") else "*"
        print(f"{r['posted_at'][:10]:<11}{r['kind']:<6}"
              f"{ins.get('views') or 0:>7}{ins.get('reach') or 0:>7}"
              f"{eng:>6.1f}%{boosts:>8}{watch_s:>7}  {r['hook']}{flag}")
    print("\n* = still updating (under 7 days old)")

    print("\nAverage views by topic feed:")
    by_feed = {}
    for r in rows:
        by_feed.setdefault(r["feed"], []).append(r["insights"].get("views") or 0)
    for feed, views in sorted(by_feed.items(), key=lambda kv: -sum(kv[1]) / len(kv[1])):
        print(f"  {feed:<15}{sum(views) / len(views):>8.0f}  ({len(views)} posts)")


def main():
    if "--report" not in sys.argv:
        import bot   # reuse its .env loader; imported lazily to avoid a cycle
        bot.load_env_file()
        token = os.environ.get("IG_ACCESS_TOKEN")
        if not token:
            print("error: IG_ACCESS_TOKEN not set")
            sys.exit(1)
        collect(token)
    report()


if __name__ == "__main__":
    main()
