# Daily AI YouTube Video Bot 🎬

Fully automated, **100% free** YouTube bot. Every day it writes a comedy
script with AI, narrates it with a neural voice, edits stock footage with
timed captions, and uploads two videos (English + Tamil) to your channel —
in vertical **Shorts** format for maximum reach.

## How it works

| Step | Service | Cost |
|------|---------|------|
| Script writing | Groq (auto-picks the best available model) | Free |
| Voiceover | Microsoft Edge neural TTS (`en-IN-Prabhat`, `ta-IN-Valluvar`) | Free |
| Stock footage | Pexels API | Free |
| Editing | MoviePy + FFmpeg (karaoke captions, zoom, crossfades) | Free |
| Upload | YouTube Data API v3 | Free |
| Scheduling | GitHub Actions (daily 06:00 UTC / 11:30 IST) | Free |

### What the videos look like

- **Karaoke captions** — Edge TTS reports the exact start time of every
  spoken word, so each word lights up gold precisely as it is said.
- **A beat before the punchline** — each sentence is narrated separately
  with a short silence between, the way a comedian delivers a setup.
- Captions sit clear of YouTube's Shorts overlay, on a rounded translucent
  pill so they stay readable over bright footage.
- Alternating slow push-in / pull-out on the footage, crossfades between
  scenes, a gold hook title over the first scene, and a spoken outro card.
- Topics rotate by date, so nothing repeats for 24 days and the English and
  Tamil videos of the same day always cover different stories.

## Setup

1. **Groq** — get a free API key at [console.groq.com](https://console.groq.com)
2. **Pexels** — get a free API key at [pexels.com/api](https://www.pexels.com/api/)
3. **YouTube** — create an OAuth Desktop App client in
   [Google Cloud Console](https://console.cloud.google.com) (YouTube Data API v3
   enabled), download `client_secret.json`, then run once on your computer:
   ```
   python setup_youtube_auth.py
   ```
4. Add three **GitHub Secrets** (repo → Settings → Secrets and variables → Actions):
   - `GROQ_API_KEY`
   - `PEXELS_API_KEY`
   - `YOUTUBE_TOKEN_JSON` (full contents of `youtube_token.json`)

## Testing without publishing

Actions tab → **Daily YouTube Video Bot** → *Run workflow* → tick **dry_run**.
The videos are rendered and attached as downloadable artifacts instead of
being uploaded to YouTube.

## Options

- `VIDEO_FORMAT=landscape` env var switches back to 16:9 (default is 9:16 Shorts).
- Run `python check_models.py` to see which Groq model the bot will use.

## Important notes

- **Keep the schedule alive:** GitHub disables cron workflows after ~60 days
  without repository activity. If daily runs stop appearing, open the Actions
  tab and click **Enable workflow**.
- **OAuth token expiry:** if your Google Cloud OAuth consent screen is in
  *Testing* mode, refresh tokens expire every 7 days. Publish the app
  (OAuth consent screen → Publish) so the token lasts indefinitely.
- YouTube upload quota (default 10,000 units/day) comfortably covers the
  2 daily uploads (~1,600 units each).
