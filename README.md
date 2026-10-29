# Barely Normal Entertainment — Daily Original-Content Bot

Posts one **original** piece of entertainment content to Instagram every day,
fully automated, running free on GitHub Actions. Original content — not
reposts — because Instagram's algorithm boosts originals and buries
aggregators.

## How it works

1. **Trending topics** — pulls the day's headlines from Google News RSS
   (entertainment, sports, top stories — no API key needed). Tragic or
   sensitive headlines are filtered out (`BLOCKED_WORDS` in `brand.py`).
2. **The joke** — an LLM writes an original hook + punchline + caption in
   the brand voice defined in `brand.py`, and can decline a headline it
   shouldn't joke about. It runs on **GitHub Models** (GPT-4.1-mini), which
   is free and uses the workflow's built-in token — no API key, no billing.
3. **The visual** — Blender (headless) renders a 7-second vertical reel:
   3D text, brand colors, floating shapes, slow zoom. If Blender fails, a
   Pillow static card is rendered instead so the daily post never dies.
4. **Publish** — Instagram's API only accepts media from a public URL, so the
   workflow deploys the rendered file to this repo's GitHub Pages site, then
   posts it as a Reel (or image) via the official Instagram API. Each deploy
   replaces the site, so only the current day's file is hosted. Every used
   headline is recorded in `posted.json`.
5. **Learn** — each post is logged in `history.json`. On every run, posts
   1–7 days old get their Instagram insights refreshed (views, reach, shares,
   saves, watch time); after 7 days the numbers are frozen. Run
   `python insights.py` for a performance report.

Edit `brand.py` to change the voice, colors, handle, feeds, or video length.

## Setup

Done:
- ✅ Meta app "trending-poster-bot" (App ID 1086756720675780), Instagram
  account connected as tester, `IG_USER_ID` = 17841419875074899
- ✅ GitHub repo `gama88/barely-normal-bot` created
- ✅ Reddit Data Access Request submitted (pending; the bot doesn't need it)
- ✅ Repo public with GitHub Pages enabled (source: GitHub Actions) to host
  each day's media
- ✅ `instagram_business_manage_insights` permission added; `IG_USER_ID`
  secret set

The only secret left to set is the Instagram token (paste when prompted —
input is hidden). Get it from the Meta app → Use cases → Customize → API
setup with Instagram login → **Generate token** (shown once; copy it
immediately):

```bash
gh secret set IG_ACCESS_TOKEN -R gama88/barely-normal-bot
```

To check everything without posting: Actions tab → Daily Instagram Post →
**Run workflow** with **Test run** ticked. It writes a real joke and renders
the real video, then attaches the video to the run instead of posting.

Then run it again with Test run unticked for the first real post. After that
it runs daily at 17:00 UTC.

GitHub Actions downloads Blender automatically (cached between runs).

## Token expiry

Instagram tokens last 60 days. Each daily run calls the refresh endpoint,
which pushes the expiry 60 days out from that day — so as long as the bot
runs at least every ~50 days, the token should never lapse. The run log
prints the remaining validity. If a refresh ever returns a *different*
token string, the log prints a WARNING and the `IG_ACCESS_TOKEN` secret
needs updating. If the token does expire, the run fails immediately with
instructions instead of rendering first.

## Testing locally

```bash
pip install -r requirements.txt
python bot.py --dry-run
```

Dry run fetches real headlines, writes the post (uses a placeholder joke if
`GITHUB_TOKEN` isn't set), renders the visual, and saves a preview to
`out/` — nothing is published. Without Blender installed locally you'll get
the static-card fallback; install Blender (blender.org) to preview the reel.
Real posting only runs on GitHub Actions, since the media is served from
GitHub Pages.
