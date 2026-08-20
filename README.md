# Barely Normal Entertainment — Daily Original-Content Bot

Posts one **original** piece of entertainment content to Instagram every day,
fully automated, running free on GitHub Actions. Original content — not
reposts — because Instagram's algorithm boosts originals and buries
aggregators.

## How it works

1. **Trending topics** — pulls the day's headlines from Google News RSS
   (entertainment, sports, top stories — no API key needed). Tragic or
   sensitive headlines are filtered out (`BLOCKED_WORDS` in `brand.py`).
2. **The joke** — Claude (Haiku) writes an original hook + punchline +
   caption in the brand voice defined in `brand.py`. Claude can also decline
   a headline it shouldn't joke about.
3. **The visual** — Blender (headless) renders a 7-second vertical reel:
   3D text, brand colors, floating shapes, slow zoom. If Blender fails, a
   Pillow static card is rendered instead so the daily post never dies.
4. **Publish** — media is uploaded to Cloudinary (Instagram requires a
   public URL), then posted as a Reel (or image) via the official Instagram
   API. Every used headline is recorded in `posted.json`.

Edit `brand.py` to change the voice, colors, handle, feeds, or video length.

## Setup status

Already done (2026-08-20):
- ✅ Instagram/Meta app "trending-poster-bot" — permissions, connected
  account, 60-day token generated (`IG_USER_ID` = 17841419875074899)
- ✅ Reddit Data Access Request submitted (pending — future upgrade, the bot
  doesn't need it)

Still needed:
1. **Anthropic API key** — create at https://console.anthropic.com →
   API Keys. Usage for this bot is roughly a few cents per month.
2. **Cloudinary** — free account at https://cloudinary.com, copy the
   `CLOUDINARY_URL` from the dashboard.
3. **GitHub** — create a repo, push this folder, then add repo secrets
   (Settings → Secrets and variables → Actions):
   - `IG_ACCESS_TOKEN`
   - `IG_USER_ID`
   - `CLOUDINARY_URL`
   - `ANTHROPIC_API_KEY`

The workflow runs daily at 17:00 UTC (~noon US Central) and can be triggered
manually from the Actions tab (**Daily Instagram Post → Run workflow**).
GitHub Actions downloads Blender automatically (cached between runs).

## Token refresh (every ~60 days)

The Instagram token expires after 60 days. Refresh it with:

```bash
curl "https://graph.instagram.com/refresh_access_token?grant_type=ig_refresh_token&access_token=<current token>"
```

Then update the `IG_ACCESS_TOKEN` GitHub secret with the new value.

## Testing locally

```bash
pip install -r requirements.txt
python bot.py --dry-run
```

Dry run fetches real headlines, writes the post (uses a placeholder joke if
`ANTHROPIC_API_KEY` isn't set), renders the visual, and saves a preview to
`out/` — nothing is published. Without Blender installed locally you'll get
the static-card fallback; install Blender (blender.org) to preview the reel.
For a real local post, copy `.env.example` to `.env` and fill it in.
