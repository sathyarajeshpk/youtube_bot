"""
Daily AI YouTube Video Bot
Posts 2 videos per day: English + Tamil
Neural voice (Microsoft Edge TTS) + phrase-timed captions
Funny Indian comedy style — vertical Shorts format
100% Free — No billing account needed

Environment variables:
  GROQ_API_KEY        (required) Groq API key — script generation
  PEXELS_API_KEY      (required) Pexels API key — stock footage
  YOUTUBE_TOKEN_JSON  (required) OAuth token JSON — YouTube upload
  DRY_RUN=1           (optional) render videos but skip YouTube upload
  VIDEO_FORMAT        (optional) "portrait" (default, Shorts) or "landscape"
"""

import os
import re
import json
import time
import random
import shutil
import asyncio
import tempfile
import platform
import warnings
import subprocess
import requests
import numpy as np
from pathlib import Path
from datetime import datetime

warnings.filterwarnings("ignore")

import groq as groq_errors
from groq import Groq
import edge_tts  # Microsoft neural TTS — sounds like a real human

from moviepy import (
    VideoFileClip, AudioFileClip, ColorClip, ImageClip,
    TextClip, CompositeVideoClip, concatenate_videoclips,
)
import moviepy.video.fx as vfx

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# ════════════════════════════════════════════════════════
# CONFIG
# ════════════════════════════════════════════════════════

VIDEO_FORMAT = os.environ.get("VIDEO_FORMAT", "portrait").lower()
if VIDEO_FORMAT == "landscape":
    VIDEO_W, VIDEO_H = 1920, 1080
else:  # portrait — uploads ≤3 min in 9:16 are treated as YouTube Shorts
    VIDEO_W, VIDEO_H = 1080, 1920

VIDEO_SIZE = (VIDEO_W, VIDEO_H)
SHORT_EDGE = min(VIDEO_W, VIDEO_H)  # font sizing must not blow up in landscape mode
FPS = 30
TEMP_DIR = Path("temp")
DRY_RUN = os.environ.get("DRY_RUN", "") not in ("", "0", "false", "False")

# Microsoft Edge TTS voices — natural, human-sounding, free
VOICE_ENGLISH = "en-IN-PrabhatNeural"   # Indian English male — warm and clear
VOICE_TAMIL   = "ta-IN-ValluvarNeural"  # Tamil male — natural Tamil accent
RATE_ENGLISH  = "+10%"                  # energetic, stand-up pacing
RATE_TAMIL    = "+6%"                   # a touch faster but still clear

OUTRO_LINES = {
    "English": "If you laughed even once, hit subscribe. It's free — unlike your neighbour's WiFi.",
    "Tamil":   "சிரிச்சிட்டீங்கனா subscribe பண்ணுங்க மக்களே! இது free தான்!",
}

# Groq models in order of preference. The bot checks which ones your key
# can actually use at runtime, so a decommissioned model never kills a run
# again (that is exactly what happened with llama3-8b-8192).
PREFERRED_MODELS = [
    "openai/gpt-oss-120b",         # best free writer on Groq right now
    "llama-3.3-70b-versatile",
    "openai/gpt-oss-20b",
    "moonshotai/kimi-k2-instruct",
    "qwen/qwen3-32b",
    "llama-3.1-8b-instant",
]
_NON_CHAT_HINTS = ("whisper", "tts", "guard", "embed", "moderation", "vision")


# ════════════════════════════════════════════════════════
# FONTS — full path required for MoviePy 2.x
# Auto-downloaded into ./fonts (SIL Open Font License):
#   Anton            — bold display font, the classic viral-Shorts caption look
#   Mukta Malar Bold — covers BOTH Tamil and Latin. DejaVu/Noto-Tamil alone
#                      render the English words inside Tamil speech
#                      ("scientist", "Portugal"...) as empty boxes.
# ════════════════════════════════════════════════════════

REPO_DIR = Path(__file__).resolve().parent

# Downloaded on first run (SIL Open Font License — see fonts/OFL-*.txt)
FONT_URLS = {
    "Anton-Regular.ttf":
        "https://raw.githubusercontent.com/google/fonts/main/ofl/anton/Anton-Regular.ttf",
    "MuktaMalar-Bold.ttf":
        "https://raw.githubusercontent.com/google/fonts/main/ofl/muktamalar/MuktaMalar-Bold.ttf",
}


def ensure_fonts():
    fonts_dir = REPO_DIR / "fonts"
    fonts_dir.mkdir(exist_ok=True)
    for name, url in FONT_URLS.items():
        path = fonts_dir / name
        if path.exists() and path.stat().st_size > 10_000:
            continue
        try:
            r = requests.get(url, timeout=30)
            r.raise_for_status()
            path.write_bytes(r.content)
            print(f"⬇️  Downloaded font: {name}")
        except Exception as e:
            print(f"⚠️  Could not download {name} ({e}) — will use system fonts")


ensure_fonts()


def _first_existing(paths):
    for p in paths:
        if p and os.path.exists(p):
            return str(p)
    return None


def _fc_match(pattern):
    try:
        out = subprocess.run(
            ["fc-match", "--format", "%{file}", pattern],
            capture_output=True, text=True, timeout=10,
        ).stdout.strip()
        return out if out and os.path.exists(out) else None
    except Exception:
        return None


def find_font(language: str = "English") -> str:
    if language == "Tamil":
        font = _first_existing([
            REPO_DIR / "fonts" / "MuktaMalar-Bold.ttf",
            "C:/Windows/Fonts/Nirmala.ttf" if platform.system() == "Windows" else None,
            "/usr/share/fonts/truetype/noto/NotoSansTamil-Bold.ttf",
            "/usr/share/fonts/truetype/lohit-tamil/Lohit-Tamil.ttf",
        ]) or _fc_match(":lang=ta")
        if font:
            return font
        print("⚠️  No Tamil font found — Tamil captions may not render!")

    if platform.system() == "Windows":
        return _first_existing([REPO_DIR / "fonts" / "Anton-Regular.ttf"]) \
            or "C:/Windows/Fonts/arialbd.ttf"

    return _first_existing([
        REPO_DIR / "fonts" / "Anton-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    ]) or _fc_match("DejaVu Sans:bold") or "DejaVuSans-Bold"


FONT_ENGLISH = find_font("English")
FONT_TAMIL   = find_font("Tamil")
print(f"✅ Fonts — English: {FONT_ENGLISH} | Tamil: {FONT_TAMIL}")

# Strip emoji/pictographs before rendering captions — the caption fonts
# have no emoji glyphs and would draw empty boxes instead.
_EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF"
    "\U00002190-\U000021FF\U00002B00-\U00002BFF️‍]+"
)

def strip_emoji(text: str) -> str:
    return _EMOJI_RE.sub("", text).strip()


# ════════════════════════════════════════════════════════
# FUNNY TOPIC BANK
# ════════════════════════════════════════════════════════

FUNNY_TOPICS = [
    "animals doing hilariously dumb things that scientists wasted money studying",
    "bizarre Indian laws that are still active and nobody told us",
    "world records so pointless they make you question human civilization",
    "things Indian moms say that sound loving but are actually threats",
    "food combinations Indians eat that send foreigners to therapy",
    "jobs that exist only in India and nowhere else on earth",
    "things that only happen on Indian trains that would terrify foreigners",
    "superstitions Indians follow with zero explanation and full commitment",
    "how different Indian states roast each other with zero mercy",
    "jugaad life hacks that should not have worked but absolutely did",
    "things Indian dads do that are identical across every household",
    "absurd things NASA found in space that sound completely made up",
    "animals with secret abilities so ridiculous they seem like superheroes",
    "ancient Indian inventions the world uses daily but never credits",
    "things that happen at every Indian wedding without fail",
    "Indian school exam culture that would confuse the entire western world",
    "street food in India that looks dangerous but is completely addictive",
    "things only Indians do in foreign countries that embarrass everyone",
    "Indian office culture habits that baffle foreign colleagues",
    "bizarre government schemes in India that actually existed",
    "things Indian aunties say at weddings that are legally considered weapons",
    "how Indians react to cold weather vs the rest of the world",
    "inventions that Indians accidentally created while trying to fix something else",
    "things Indian students do before exams that make zero scientific sense",
]

# ════════════════════════════════════════════════════════
# STEP 1: SCRIPT GENERATION (Groq — with model auto-discovery)
# ════════════════════════════════════════════════════════

_active_model = None


def pick_groq_model(client: Groq, exclude=()) -> str:
    """Pick the best chat model this API key can actually use right now."""
    try:
        available = {m.id for m in client.models.list().data}
    except Exception as e:
        print(f"⚠️  Could not list Groq models ({e}) — trying preferred list blind")
        for m in PREFERRED_MODELS:
            if m not in exclude:
                return m
        raise RuntimeError("No Groq model available")

    for m in PREFERRED_MODELS:
        if m in available and m not in exclude:
            return m
    for m in sorted(available):
        if m not in exclude and not any(h in m.lower() for h in _NON_CHAT_HINTS):
            return m
    raise RuntimeError(f"No usable chat model found. Available: {sorted(available)}")


def call_groq(client: Groq, prompt: str, max_tokens: int = 3000,
              json_mode: bool = False) -> str:
    global _active_model
    if _active_model is None:
        _active_model = pick_groq_model(client)
        print(f"🤖 Using Groq model: {_active_model}")

    excluded = []
    last_err = None
    for attempt in range(5):
        kwargs = dict(
            model=_active_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.9,
            max_tokens=max_tokens,
        )
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        try:
            response = client.chat.completions.create(**kwargs)
            return (response.choices[0].message.content or "").strip()
        except groq_errors.RateLimitError as e:
            wait = 15 * (attempt + 1)
            print(f"⏳ Groq rate limit — waiting {wait}s (attempt {attempt+1}/5)")
            time.sleep(wait)
            last_err = e
        except groq_errors.BadRequestError as e:
            msg = str(e).lower()
            if json_mode and "response_format" in msg:
                json_mode = False  # model doesn't support JSON mode — plain retry
                continue
            if "model" in msg and ("decommission" in msg or "not found" in msg
                                   or "does not exist" in msg or "deprecat" in msg):
                excluded.append(_active_model)
                _active_model = pick_groq_model(client, exclude=excluded)
                print(f"🔁 Model retired — switching to: {_active_model}")
                continue
            raise
        except (groq_errors.APIConnectionError, groq_errors.InternalServerError) as e:
            wait = 5 * (attempt + 1)
            print(f"⏳ Groq hiccup ({type(e).__name__}) — retrying in {wait}s")
            time.sleep(wait)
            last_err = e
    raise RuntimeError(f"Groq failed after retries: {last_err}")


def clean_json(raw: str) -> str:
    raw = raw.replace("```json", "").replace("```", "").strip()
    raw = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", raw)
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    return match.group(0) if match else raw


def validate_script(script: dict) -> dict:
    """Make sure the LLM output has everything the renderer needs."""
    scenes = script.get("scenes") or []
    scenes = [s for s in scenes
              if isinstance(s, dict) and s.get("narration") and s.get("search_query")]
    if len(scenes) < 3:
        raise ValueError(f"Only {len(scenes)} usable scenes")
    for s in scenes:
        s["narration"] = str(s["narration"]).strip()
        s["search_query"] = str(s["search_query"]).strip()
        try:
            s["duration"] = max(4, min(8, int(s.get("duration", 5))))
        except (TypeError, ValueError):
            s["duration"] = 5
    script["scenes"] = scenes[:6]
    title = re.sub(r"[\r\n<>]", " ", str(script.get("title", "Unbelievable Facts!"))).strip()
    script["title"] = title[:95] or "Unbelievable Facts!"
    script["description"] = str(script.get("description", ""))[:4900]
    tags = script.get("tags") or ["funny", "comedy", "india", "viral", "shorts"]
    script["tags"] = [str(t)[:30] for t in tags][:15]
    return script


def generate_english_script(topic: str, client: Groq) -> dict:
    prompt = f"""You are the head writer for India's most viral comedy YouTube channel — think BB Ki Vines meets Tanmay Bhat meets a facts channel.

Your videos get 10 million views because every single line is either surprising, relatable, or laugh-out-loud funny. Usually all three.

TODAY'S TOPIC: {topic}

---

STUDY THESE REAL EXAMPLES OF VIRAL INDIAN COMEDY NARRATION:

Example 1:
"The pistol shrimp stuns its prey by snapping its claw so fast it creates a flash of light hotter than the surface of the sun. Meanwhile, we can't even snap our fingers in rhythm at a wedding."

Example 2:
"In Rajasthan, there's a law that says you cannot fly a kite without a police permit. The British made this law in 1923 to stop independence fighters from signalling each other. We kept the law. We kept the kite festival. Nobody got the memo."

Example 3:
"A man in Tamil Nadu grew his mustache for 32 years. It is now 4.29 meters long. His wife said — 'it was either me or the mustache.' The mustache won. Respect."

Example 4:
"Indian Railways serves 13 million passengers every single day. That is more than the entire population of Portugal. And somehow the chai still costs 7 rupees and tastes like it was made by someone who personally hates you."

Example 5:
"Scientists in Japan trained a fish to recognize human faces. It got 86% accuracy. Your relatives at a wedding cannot recognize you after 2 years, but sure, the fish is the impressive one."

---

NOW WRITE 6 SCENES in EXACTLY this style. Each scene MUST have:
1. A SPECIFIC surprising fact with actual numbers, names, or places
2. An Indian comparison that makes the viewer think "oh my god that's so true"
3. A punchline that lands — either a twist, a callback, or a burn

STRICT RULES:
- NEVER say "some", "many", "often", "usually" — always use SPECIFIC numbers and places
- NEVER be inspirational or educational-sounding — this is COMEDY
- At least 2 scenes must reference something from daily Indian life (chai, traffic, relatives, CBSE, cricket, arranged marriage, electricity cuts, jugaad, WhatsApp forwards)
- One scene must end with a completely unexpected twist
- One scene must roast the viewer lovingly ("We Indians...", "Your mom...", "Your uncle...")
- Scene 1 is the HOOK — it must be the single most shocking fact of the six, because viewers decide in 2 seconds whether to keep watching
- Speak fast and punchy — like a stand-up comedian, not a documentary narrator
- Do NOT use emoji in narration (it is spoken aloud)

Return ONLY this JSON with no markdown, no explanation:

{{
  "title": "Title that someone will SHARE on their family WhatsApp group — include a number or shocking word, under 65 chars",
  "description": "2 sentences. First sentence: shocking hook. Second sentence: why they must watch.\\n\\n#funny #comedy #india #facts #trending #viral #humor #shorts #lol #desi",
  "tags": ["funny","comedy","india","facts","trending","viral","humor","shorts","lol","desi"],
  "scenes": [
    {{
      "narration": "Specific fact + Indian comparison + punchline. EXACTLY 2 sentences. No more.",
      "search_query": "2-3 word English footage term matching the visual (e.g. 'shrimp underwater', 'man with mustache', 'train crowd india')",
      "duration": 5
    }}
  ]
}}

- Exactly 6 scenes
- Each narration: EXACTLY 2 sentences — punchy, fast, funny
- search_query: plain English only, simple visual terms
- duration: integer 4 to 7
- Output ONLY raw JSON, nothing else"""

    last_err = None
    for attempt in range(3):
        try:
            raw = call_groq(client, prompt, json_mode=True)
            return validate_script(json.loads(clean_json(raw)))
        except (json.JSONDecodeError, ValueError) as e:
            print(f"⚠️  Script parse failed (attempt {attempt+1}/3): {e}")
            last_err = e

    # Final fallback: a dead-simple prompt that even a small model gets right
    simple_prompt = (
        f"Write a funny 6-scene Indian comedy YouTube script about: {topic}\n\n"
        "Each scene: specific funny fact + Indian relatable comparison + punchline.\n"
        "Return ONLY this JSON:\n"
        '{"title": "funny title under 65 chars",'
        '"description": "2 funny sentences\\n\\n#funny #comedy #india #viral #shorts",'
        '"tags": ["funny","comedy","india","viral","shorts"],'
        '"scenes": ['
        + ",".join(
            '{"narration": "specific fact. funny Indian punchline.",'
            ' "search_query": "2 word footage term", "duration": 5}'
            for _ in range(6)
        )
        + "]}"
    )
    try:
        raw = call_groq(client, simple_prompt, json_mode=True)
        return validate_script(json.loads(clean_json(raw)))
    except (json.JSONDecodeError, ValueError) as e:
        raise RuntimeError(f"Script generation failed: {e}") from last_err


def translate_to_tamil(text: str, client: Groq) -> str:
    prompt = (
        "You are a Tamil comedy writer and translator for YouTube. "
        "Your Tamil videos go viral because they sound like a real Chennai comedian talking — "
        "not like a textbook or a news anchor.\n\n"
        "RULES for your translation:\n"
        "- Use natural spoken Tamil, NOT formal written Tamil\n"
        "- Keep all numbers, place names, and facts EXACTLY as they are\n"
        "- Keep the PUNCHLINE — if the English is funny, the Tamil must also be funny\n"
        "- Use Tamil slang where it fits (மச்சான், கில்லி, etc.)\n"
        "- Do NOT translate English words commonly used in Tamil speech (like 'scientist', 'record', 'percent')\n"
        "- Return ONLY the Tamil text, no explanation, no English\n\n"
        "Now translate this:\n\n"
        + text
    )
    result = call_groq(client, prompt, max_tokens=500)
    result = re.sub(r"^(Here is|Translation:|Tamil:|Sure,|இதோ)\s*", "", result, flags=re.IGNORECASE)
    return result.strip()


def generate_script(language: str) -> dict:
    print(f"📝 Generating {language} script with Groq...")
    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    topic = random.choice(FUNNY_TOPICS)
    print(f"🎲 Topic: {topic}")

    script = generate_english_script(topic, client)

    if language == "Tamil":
        print("🔄 Translating to Tamil (scene by scene)...")
        tamil_title = translate_to_tamil(script["title"], client)
        script["title"] = (tamil_title if tamil_title and len(tamil_title.strip()) > 3
                           else script["title"])[:95]

        eng_desc = script["description"].split("\n")[0]
        tamil_desc = translate_to_tamil(eng_desc, client)
        script["description"] = (
            (tamil_desc if tamil_desc and len(tamil_desc.strip()) > 3 else eng_desc)
            + "\n\n#funny #tamil #comedy #tamilcomedy #trending #viral #tamilfacts #shorts #சிரிப்பு #கலாட்டா"
        )
        script["tags"] = [
            "funny", "tamil", "comedy", "tamilcomedy", "trending",
            "viral", "tamilfacts", "shorts", "desi", "india",
        ]
        for i, scene in enumerate(script["scenes"]):
            tamil_narration = translate_to_tamil(scene["narration"], client)
            if tamil_narration and len(tamil_narration.strip()) > 3:
                scene["narration"] = tamil_narration
            print(f"   Translated scene {i+1}/{len(script['scenes'])}")

    print(f"✅ Title: {script['title']}")
    return script


# ════════════════════════════════════════════════════════
# STEP 2: NEURAL VOICEOVER WITH EDGE TTS
# ════════════════════════════════════════════════════════

async def _generate_voiceover_async(text: str, output_path: Path, voice: str, rate: str) -> None:
    communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate)
    await communicate.save(str(output_path))


def generate_voiceover(text: str, output_path: Path, language: str) -> None:
    voice = VOICE_TAMIL if language == "Tamil" else VOICE_ENGLISH
    rate = RATE_TAMIL if language == "Tamil" else RATE_ENGLISH
    last_err = None
    for attempt in range(3):
        try:
            asyncio.run(_generate_voiceover_async(text, output_path, voice, rate))
            if output_path.exists() and output_path.stat().st_size > 1000:
                return
            raise RuntimeError("TTS produced an empty file")
        except Exception as e:
            last_err = e
            print(f"   ⚠️  TTS attempt {attempt+1}/3 failed: {e}")
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"Edge TTS failed: {last_err}")


# ════════════════════════════════════════════════════════
# STEP 3: STOCK FOOTAGE (Pexels)
# ════════════════════════════════════════════════════════

_used_video_ids = set()


def _pexels_search(query: str, min_duration: int):
    headers = {"Authorization": os.environ["PEXELS_API_KEY"]}
    orientation = "portrait" if VIDEO_H > VIDEO_W else "landscape"
    url = (
        f"https://api.pexels.com/videos/search"
        f"?query={requests.utils.quote(query)}"
        f"&per_page=12"
        f"&orientation={orientation}"
        f"&size=medium"
    )
    data = requests.get(url, headers=headers, timeout=20).json()
    videos = [v for v in data.get("videos", [])
              if v.get("duration", 0) >= max(2, min_duration - 3)
              and v["id"] not in _used_video_ids]
    return videos or [v for v in data.get("videos", []) if v["id"] not in _used_video_ids]


def _best_file(video):
    """Pick the file closest to our target resolution (≥ our short edge if possible)."""
    target = min(VIDEO_W, VIDEO_H)
    files = [f for f in video.get("video_files", []) if f.get("link")]
    if not files:
        return None
    def short_edge(f):
        return min(f.get("width") or 0, f.get("height") or 0)
    good = sorted((f for f in files if short_edge(f) >= target), key=short_edge)
    return good[0] if good else max(files, key=short_edge)


def download_stock_video(query: str, min_duration: int, output_path: Path) -> bool:
    fallback_queries = [query, f"{query.split()[0]} india", "india street life"]
    for q in fallback_queries:
        try:
            videos = _pexels_search(q, min_duration)
            if not videos:
                continue
            video = random.choice(videos[:6])
            chosen = _best_file(video)
            if not chosen:
                continue
            r = requests.get(chosen["link"], stream=True, timeout=120)
            r.raise_for_status()
            with open(output_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=65536):
                    f.write(chunk)
            _used_video_ids.add(video["id"])
            if q != query:
                print(f"   ↪️  Used fallback query '{q}'")
            return True
        except Exception as e:
            print(f"   ⚠️  Pexels error for '{q}': {e}")
    print(f"   ⚠️  No footage for '{query}' — gradient fallback")
    return False


# ════════════════════════════════════════════════════════
# STEP 4: VIDEO ASSEMBLY
# ════════════════════════════════════════════════════════

def safe_with_effects(clip, effects: list):
    """Apply effects safely — falls back gracefully if moviepy version differs."""
    try:
        return clip.with_effects(effects)
    except Exception:
        return clip


def fit_cover(clip):
    """Scale to fill the frame and center-crop — never stretch/distort."""
    scale = max(VIDEO_W / clip.w, VIDEO_H / clip.h)
    resized = clip.resized(scale)
    return resized.cropped(
        x_center=resized.w / 2, y_center=resized.h / 2,
        width=VIDEO_W, height=VIDEO_H,
    )


def ken_burns(clip, duration: float):
    """Slow zoom-in — makes static stock footage feel alive."""
    try:
        zoomed = clip.resized(lambda t: 1.0 + 0.06 * (t / max(duration, 0.1)))
        return CompositeVideoClip(
            [zoomed.with_position("center")], size=VIDEO_SIZE
        ).with_duration(duration)
    except Exception:
        return clip


def chunk_narration(text: str, max_chars: int = 34) -> list:
    """Split narration into short phrase chunks for timed captions."""
    words = strip_emoji(text).split()
    chunks, current = [], ""
    for w in words:
        candidate = f"{current} {w}".strip()
        if len(candidate) > max_chars and current:
            chunks.append(current)
            current = w
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks or [strip_emoji(text)]


def make_phrase_captions(text: str, duration: float, font: str) -> list:
    """Phrase-by-phrase captions timed across the scene — much easier to read
    than one giant block of text, and it keeps eyes glued to the screen."""
    chunks = chunk_narration(text)
    total_chars = sum(len(c) for c in chunks) or 1
    usable = max(duration - 0.2, 0.5)
    font_size = int(SHORT_EDGE * 0.058)
    y_pos = int(VIDEO_H * (0.68 if VIDEO_H > VIDEO_W else 0.74))

    caption_clips, t = [], 0.0
    for i, chunk in enumerate(chunks):
        d = usable * len(chunk) / total_chars
        if i == len(chunks) - 1:
            d = max(duration - t, d)  # last phrase holds until scene end
        clip = TextClip(
            text=chunk, font_size=font_size, color="white",
            stroke_color="black", stroke_width=max(2, font_size // 14),
            size=(VIDEO_W - 120, None), method="caption",
            text_align="center", font=font,
            margin=(0, int(font_size * 0.75)),  # moviepy clips descenders without headroom
        ).with_position(("center", y_pos)).with_start(t).with_duration(d)
        caption_clips.append(safe_with_effects(clip, [vfx.CrossFadeIn(0.12)]))
        t += d
    return caption_clips


def make_hook_overlay(title: str, duration: float, font: str):
    """Big title flash at the start of scene 1 — the 2-second retention hook."""
    text = strip_emoji(title)
    if not text:
        return None
    d = min(2.8, duration)
    clip = TextClip(
        text=text, font_size=int(SHORT_EDGE * 0.062), color="#FFD700",
        stroke_color="black", stroke_width=max(3, SHORT_EDGE // 220),
        size=(VIDEO_W - 100, None), method="caption",
        text_align="center", font=font,
        margin=(0, int(SHORT_EDGE * 0.05)),
    ).with_position(("center", int(VIDEO_H * 0.12))).with_duration(d)
    return safe_with_effects(clip, [vfx.CrossFadeIn(0.25), vfx.CrossFadeOut(0.4)])


def gradient_background(duration: float):
    """Animated-feeling dark gradient — far nicer than a flat colour card."""
    palettes = [
        ((18, 12, 48), (96, 24, 72)),   # midnight purple → wine
        ((8, 32, 64), (16, 96, 112)),   # deep blue → teal
        ((40, 12, 12), (128, 64, 16)),  # maroon → amber
        ((12, 40, 24), (24, 96, 64)),   # forest → emerald
    ]
    top, bottom = random.choice(palettes)
    grad = np.linspace(top, bottom, VIDEO_H).astype(np.uint8)
    frame = np.tile(grad[:, None, :], (1, VIDEO_W, 1))
    clip = ImageClip(frame).with_duration(duration)
    return ken_burns(clip, duration)


def get_base_clip(video_path: Path, clip_duration: float):
    raw = VideoFileClip(str(video_path))
    if raw.duration >= clip_duration:
        max_start = raw.duration - clip_duration
        start = random.uniform(0, min(max_start, 3.0))
        clipped = raw.subclipped(start, start + clip_duration)
    else:
        loops = int(clip_duration / raw.duration) + 2
        clipped = concatenate_videoclips([raw] * loops).subclipped(0, clip_duration)
    return ken_burns(fit_cover(clipped), clip_duration)


def make_caption_backdrop(duration: float):
    """Soft dark band behind captions for readability on bright footage."""
    band_h = int(VIDEO_H * 0.22)
    y = int(VIDEO_H * (0.64 if VIDEO_H > VIDEO_W else 0.70))
    return (
        ColorClip(size=(VIDEO_W, band_h), color=(0, 0, 0))
        .with_opacity(0.35).with_position((0, y)).with_duration(duration)
    )


def make_outro_card(language: str, font: str):
    """Short branded outro with a spoken subscribe gag."""
    line = OUTRO_LINES[language]
    audio_path = TEMP_DIR / "outro_audio.mp3"
    generate_voiceover(line, audio_path, language)
    audio = AudioFileClip(str(audio_path))
    duration = audio.duration + 0.7

    bg = gradient_background(duration)
    main_text = TextClip(
        text="LIKE  •  SHARE  •  SUBSCRIBE",
        font_size=int(SHORT_EDGE * 0.055), color="#FFD700",
        stroke_color="black", stroke_width=max(2, SHORT_EDGE // 300),
        size=(VIDEO_W - 100, None), method="caption",
        text_align="center", font=FONT_ENGLISH,
        margin=(0, int(SHORT_EDGE * 0.045)),
    ).with_position(("center", int(VIDEO_H * 0.42))).with_duration(duration)
    sub_text = TextClip(
        text=strip_emoji(line), font_size=int(SHORT_EDGE * 0.037), color="white",
        stroke_color="black", stroke_width=2,
        size=(VIDEO_W - 140, None), method="caption",
        text_align="center", font=font,
        margin=(0, int(SHORT_EDGE * 0.03)),
    ).with_position(("center", int(VIDEO_H * 0.56))).with_duration(duration)

    return CompositeVideoClip(
        [bg, safe_with_effects(main_text, [vfx.CrossFadeIn(0.3)]),
         safe_with_effects(sub_text, [vfx.CrossFadeIn(0.5)])],
        size=VIDEO_SIZE,
    ).with_audio(audio)


def assemble_video(script: dict, output_path: str, language: str) -> None:
    scenes = script["scenes"]
    font = FONT_TAMIL if language == "Tamil" else FONT_ENGLISH
    print(f"🎬 Assembling {language} video ({VIDEO_W}x{VIDEO_H})...")
    TEMP_DIR.mkdir(exist_ok=True)
    clips = []

    for i, scene in enumerate(scenes):
        print(f"   Scene {i+1}/{len(scenes)}: '{scene['search_query']}'")
        audio_path = TEMP_DIR / f"audio_{i}.mp3"
        video_path = TEMP_DIR / f"video_{i}.mp4"

        generate_voiceover(scene["narration"], audio_path, language)
        audio_clip = AudioFileClip(str(audio_path))
        clip_duration = audio_clip.duration + 0.5

        got = download_stock_video(scene["search_query"], scene["duration"], video_path)
        if got:
            try:
                base = get_base_clip(video_path, clip_duration)
            except Exception as e:
                print(f"   ⚠️  Video load failed ({e}), using gradient fallback")
                base = gradient_background(clip_duration)
        else:
            base = gradient_background(clip_duration)

        layers = [base, make_caption_backdrop(clip_duration)]
        layers += make_phrase_captions(scene["narration"], clip_duration, font)
        if i == 0:
            hook = make_hook_overlay(script["title"], clip_duration, font)
            if hook:
                layers.append(hook)

        scene_clip = (
            CompositeVideoClip(layers, size=VIDEO_SIZE)
            .with_duration(clip_duration)
            .with_audio(audio_clip)
        )
        if i > 0:
            scene_clip = safe_with_effects(scene_clip, [vfx.CrossFadeIn(0.3)])
        clips.append(scene_clip)

    try:
        outro = safe_with_effects(make_outro_card(language, font), [vfx.CrossFadeIn(0.3)])
        clips.append(outro)
    except Exception as e:
        print(f"   ⚠️  Outro skipped: {e}")

    final = concatenate_videoclips(clips, method="compose", padding=-0.3)
    final.write_videofile(
        output_path, fps=FPS, codec="libx264", audio_codec="aac",
        preset="medium", threads=4,
        temp_audiofile="temp_audio_merge.aac", remove_temp=True, logger=None,
    )
    shutil.rmtree(TEMP_DIR, ignore_errors=True)
    print(f"✅ Assembled: {output_path} ({final.duration:.1f}s)")


# ════════════════════════════════════════════════════════
# STEP 5: YOUTUBE UPLOAD
# ════════════════════════════════════════════════════════

def upload_to_youtube(video_path: str, title: str, description: str, tags: list) -> str:
    print("📤 Uploading to YouTube...")
    token_json_str = os.environ.get("YOUTUBE_TOKEN_JSON")
    if token_json_str:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".json", mode="w")
        json.dump(json.loads(token_json_str), tmp)
        tmp.close()
        token_path = tmp.name
    else:
        token_path = "youtube_token.json"

    creds = Credentials.from_authorized_user_file(
        token_path, scopes=["https://www.googleapis.com/auth/youtube.upload"]
    )
    # The stored access token is hours-to-months old — always mint a fresh one.
    if creds.refresh_token:
        creds.refresh(Request())

    youtube = build("youtube", "v3", credentials=creds)
    req = youtube.videos().insert(
        part="snippet,status",
        body={
            "snippet": {
                "title": title, "description": description,
                "tags": tags, "categoryId": "23", "defaultLanguage": "en",
            },
            "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False},
        },
        media_body=MediaFileUpload(video_path, chunksize=-1, resumable=True),
    )
    response = None
    while response is None:
        _, response = req.next_chunk()

    video_id = response["id"]
    print(f"✅ Published: https://youtube.com/watch?v={video_id}")
    return video_id


# ════════════════════════════════════════════════════════
# PIPELINE
# ════════════════════════════════════════════════════════

def run_pipeline(language: str, output_path: str):
    print(f"\n{'─'*55}")
    print(f"🚀 Starting {language} video...")
    print(f"{'─'*55}\n")
    try:
        script = generate_script(language)
        assemble_video(script, output_path, language)

        if DRY_RUN:
            print(f"🧪 DRY RUN — skipping upload, video kept at: {output_path}")
            return "dry-run"

        video_id = upload_to_youtube(
            output_path, script["title"], script["description"], script["tags"]
        )
        try:
            os.remove(output_path)
        except OSError:
            pass
        print(f"✅ {language} done: https://youtube.com/watch?v={video_id}\n")
        return video_id
    except Exception as e:
        print(f"❌ {language} failed: {e}")
        import traceback
        traceback.print_exc()
        # Keep the rendered file so the workflow can attach it as an artifact
        return None


def run_daily_pipeline():
    start = datetime.now()
    print(f"\n{'='*55}")
    print(f"🎯 DAILY VIDEO BOT — {start.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"   English + Tamil | Neural Voice | {VIDEO_W}x{VIDEO_H} | Cost: Rs.0")
    if DRY_RUN:
        print("   MODE: DRY RUN (no upload)")
    print(f"{'='*55}")

    eng_id = run_pipeline("English", "final_video_english.mp4")
    tam_id = run_pipeline("Tamil",   "final_video_tamil.mp4")

    elapsed = (datetime.now() - start).seconds // 60
    print(f"\n{'='*55}")
    print(f"⏱️  Done in ~{elapsed} min")
    if eng_id and eng_id != "dry-run":
        print(f"🇬🇧 English: https://youtube.com/watch?v={eng_id}")
    if tam_id and tam_id != "dry-run":
        print(f"🇮🇳 Tamil:   https://youtube.com/watch?v={tam_id}")
    print(f"{'='*55}\n")

    if not eng_id and not tam_id:
        raise RuntimeError("Both pipelines failed.")


if __name__ == "__main__":
    run_daily_pipeline()
