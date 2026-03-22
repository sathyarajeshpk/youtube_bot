"""
Daily AI YouTube Video Bot
Posts 2 videos per day: English + Tamil
Neural voice (Microsoft Edge TTS) + Animated captions
Much funnier prompts with stand-up comedy style
100% Free - No billing account needed
"""

import os
import re
import json
import random
import shutil
import asyncio
import tempfile
import platform
import warnings
import requests
from pathlib import Path
from datetime import datetime

warnings.filterwarnings("ignore")

from groq import Groq
import edge_tts                     # Microsoft neural TTS — sounds like a real human
from moviepy import (
    VideoFileClip, AudioFileClip, ColorClip,
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
VIDEO_W    = 1280
VIDEO_H    = 720
VIDEO_SIZE = (VIDEO_W, VIDEO_H)
FPS        = 24
TEMP_DIR   = Path("temp")

# Microsoft Edge TTS voices — natural, human-sounding, free
VOICE_ENGLISH = "en-IN-PrabhatNeural"    # Indian English male — warm and clear
VOICE_TAMIL   = "ta-IN-ValluvarNeural"   # Tamil male — natural Tamil accent

# Font
FONT_BOLD = "C:/Windows/Fonts/arialbd.ttf" if platform.system() == "Windows" else "DejaVu-Sans-Bold"

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
]


# ════════════════════════════════════════════════════════
# STEP 1: SCRIPT GENERATION — MUCH FUNNIER PROMPTS
# ════════════════════════════════════════════════════════

def clean_json(raw: str) -> str:
    raw = raw.replace("```json", "").replace("```", "").strip()
    raw = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", raw)
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    return match.group(0) if match else raw


def call_groq(client: Groq, prompt: str, max_tokens: int = 2000) -> str:
    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": prompt}],
        temperature=1.1,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content.strip()


def generate_english_script(topic: str, client: Groq) -> dict:
    """
    Generate a genuinely funny English script.
    Prompt is engineered for maximum comedy — specific, punchy, Indian-relatable.
    """
    prompt = f"""You are India's funniest YouTube scriptwriter. Your videos go viral because they are SPECIFIC, SURPRISING, and make people laugh out loud.

Topic: {topic}

Write a 6-scene comedy video script. Each scene must follow this formula:
1. State a specific shocking/weird fact
2. Add a funny comparison or reaction that an Indian person would instantly relate to
3. End with a punchline or unexpected twist

COMEDY RULES — follow all of them:
- NEVER be vague. "A fish in Kerala" beats "a fish somewhere"
- Compare weird facts to everyday Indian life: traffic, chai, cricket, UPSC, relatives, weddings, electricity cuts
- Use the comedian's trick of building up then subverting expectations
- Include at least one fact so bizarre the viewer will want to share it
- Speak directly to the viewer like "You" and "We Indians"
- One scene must have a self-aware joke about the video itself

EXAMPLE of BAD narration (boring, vague):
"Some animals have strange abilities. Scientists have studied them."

EXAMPLE of GOOD narration (funny, specific):
"A mantis shrimp can punch with the force of a bullet. Scientists measured it at 1500 newtons. For context, your uncle arguing about cricket uses maybe 2."

Return ONLY this JSON with no markdown, no explanation:
{{
  "title": "A title so good someone would send it to their family WhatsApp group — under 65 chars, include a number or question",
  "description": "2 sentences that make someone curious enough to click. Funny tone.\\n\\n#funny #comedy #india #facts #trending #viral #humor #shorts #lol #desi",
  "tags": ["funny","comedy","india","facts","trending","viral","humor","shorts","lol","desi"],
  "scenes": [
    {{
      "narration": "Scene narration — specific fact + Indian comparison + punchline. 2 sentences MAX.",
      "search_query": "2-3 word English stock footage search term that visually matches the scene",
      "duration": 5
    }}
  ]
}}

Rules:
- Exactly 6 scenes
- Each narration: 2 sentences MAXIMUM — punchy and fast
- search_query: plain English only, simple visual terms (e.g. 'confused man', 'monkey stealing food', 'crowded train')
- duration: integer between 4 and 7
- Output ONLY raw JSON"""

    raw    = call_groq(client, prompt)
    script = json.loads(clean_json(raw))
    return script


def translate_to_tamil(text: str, client: Groq) -> str:
    """Translate English to Tamil. Plain string — never inside JSON."""
    prompt = (
        "You are a Tamil comedian and translator. "
        "Translate the following to Tamil. "
        "Keep the humor, punchline, and energy EXACTLY. "
        "Use natural spoken Tamil that a Tamil YouTube viewer would enjoy — not formal written Tamil. "
        "Return ONLY the Tamil translation, no explanation, no English:\n\n"
        + text
    )
    result = call_groq(client, prompt, max_tokens=400)
    result = re.sub(r"^(Here is|Translation:|Tamil:|Sure,)\s*", "", result, flags=re.IGNORECASE)
    return result.strip()


def generate_script(language: str) -> dict:
    """
    Generate script for the given language.
    Tamil: generate in English first, then translate each field separately.
    This completely avoids Tamil unicode inside JSON — no parse errors ever.
    """
    print(f"   Generating {language} script with Groq...")

    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    topic  = random.choice(FUNNY_TOPICS)

    # Always generate clean English JSON first
    script = generate_english_script(topic, client)

    if language == "Tamil":
        print("   Translating to Tamil (scene by scene)...")
        script["title"] = translate_to_tamil(script["title"], client)
        eng_desc = script["description"].split("\n")[0]
        script["description"] = (
            translate_to_tamil(eng_desc, client)
            + "\n\n#funny #tamil #comedy #tamilcomedy #trending #viral #tamilfacts #shorts #சிரிப்பு #கலாட்டா"
        )
        script["tags"] = [
            "funny", "tamil", "comedy", "tamilcomedy", "trending",
            "viral", "tamilfacts", "shorts", "desi", "india",
        ]
        for i, scene in enumerate(script.get("scenes", [])):
            scene["narration"] = translate_to_tamil(scene["narration"], client)
            print(f"    Translated scene {i+1}/6")

    print(f"   Title: {script['title']}")
    return script


# ════════════════════════════════════════════════════════
# STEP 2: NEURAL VOICEOVER WITH EDGE TTS
# ════════════════════════════════════════════════════════

async def _generate_voiceover_async(text: str, output_path: Path, voice: str) -> None:
    """Async Edge TTS call — Microsoft neural voice, sounds like a real human."""
    communicate = edge_tts.Communicate(text=text, voice=voice, rate="+10%")
    await communicate.save(str(output_path))


def generate_voiceover(text: str, output_path: Path, language: str) -> None:
    """
    Generate neural voiceover using Microsoft Edge TTS.
    Completely free, no API key, sounds natural and human.
    English: Indian English male voice (en-IN-PrabhatNeural)
    Tamil: Tamil male voice (ta-IN-ValluvarNeural)
    """
    voice = VOICE_TAMIL if language == "Tamil" else VOICE_ENGLISH
    # Run async function in sync context
    asyncio.get_event_loop().run_until_complete(
        _generate_voiceover_async(text, output_path, voice)
    )


# ════════════════════════════════════════════════════════
# STEP 3: STOCK FOOTAGE
# ════════════════════════════════════════════════════════

def download_stock_video(query: str, min_duration: int, output_path: Path) -> bool:
    headers = {"Authorization": os.environ["PEXELS_API_KEY"]}
    url = (
        f"https://api.pexels.com/videos/search"
        f"?query={requests.utils.quote(query)}"
        f"&per_page=10"
        f"&min_duration={max(1, min_duration - 2)}"
        f"&max_duration={min_duration + 8}"
        f"&size=medium"
    )
    try:
        data = requests.get(url, headers=headers, timeout=20).json()
        if not data.get("videos"):
            print(f"    No footage for '{query}' — colour fallback")
            return False
        video  = random.choice(data["videos"][:5])
        files  = sorted(video["video_files"], key=lambda x: x.get("width", 0))
        chosen = files[min(len(files) - 1, len(files) // 2)]
        r = requests.get(chosen["link"], stream=True, timeout=90)
        with open(output_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=65536):
                f.write(chunk)
        return True
    except Exception as e:
        print(f"    Pexels error for '{query}': {e}")
        return False


# ════════════════════════════════════════════════════════
# STEP 4: VIDEO ASSEMBLY WITH ANIMATIONS
# ════════════════════════════════════════════════════════

def make_caption(text: str, duration: float):
    return (
        TextClip(
            text=text, font_size=44, color="white",
            stroke_color="black", stroke_width=2,
            size=(VIDEO_W - 120, None), method="caption",
            text_align="center", font=FONT_BOLD,
        )
        .with_position(("center", VIDEO_H - 200))
        .with_duration(duration)
        .with_effects([vfx.FadeIn(0.4), vfx.FadeOut(0.4)])
    )


def make_top_bar(duration: float):
    return (
        ColorClip(size=(VIDEO_W, 80), color=(0, 0, 0))
        .with_opacity(0.45).with_position((0, 0))
        .with_duration(duration).with_effects([vfx.FadeIn(0.5)])
    )


def get_base_clip(video_path: Path, clip_duration: float):
    raw = VideoFileClip(str(video_path))
    if raw.duration >= clip_duration:
        clipped = raw.subclipped(0, clip_duration)
    else:
        loops   = int(clip_duration / raw.duration) + 2
        clipped = concatenate_videoclips([raw] * loops).subclipped(0, clip_duration)
    return clipped.resized(VIDEO_SIZE).with_effects([vfx.FadeIn(0.4), vfx.FadeOut(0.4)])


def assemble_video(scenes: list, output_path: str, language: str) -> None:
    print(f"   Assembling {language} video...")
    TEMP_DIR.mkdir(exist_ok=True)
    clips = []

    for i, scene in enumerate(scenes):
        print(f"    Scene {i+1}/{len(scenes)}: '{scene['search_query']}'")
        audio_path = TEMP_DIR / f"audio_{i}.mp3"
        video_path = TEMP_DIR / f"video_{i}.mp4"

        generate_voiceover(scene["narration"], audio_path, language)
        audio_clip    = AudioFileClip(str(audio_path))
        clip_duration = audio_clip.duration + 0.6

        got = download_stock_video(scene["search_query"], scene["duration"], video_path)
        if got:
            try:
                base = get_base_clip(video_path, clip_duration)
            except Exception:
                base = (ColorClip(size=VIDEO_SIZE, color=(15, 15, 35), duration=clip_duration)
                        .with_effects([vfx.FadeIn(0.4), vfx.FadeOut(0.4)]))
        else:
            base = (ColorClip(size=VIDEO_SIZE, color=(15, 15, 35), duration=clip_duration)
                    .with_effects([vfx.FadeIn(0.4), vfx.FadeOut(0.4)]))

        clips.append(
            CompositeVideoClip([
                base,
                make_top_bar(clip_duration),
                make_caption(scene["narration"], clip_duration),
            ]).with_audio(audio_clip)
        )

    concatenate_videoclips(clips, method="compose").write_videofile(
        output_path, fps=FPS, codec="libx264", audio_codec="aac",
        temp_audiofile="temp_audio_merge.aac", remove_temp=True, logger=None,
    )
    shutil.rmtree(TEMP_DIR, ignore_errors=True)
    print(f"   Assembled: {output_path}")


# ════════════════════════════════════════════════════════
# STEP 5: YOUTUBE UPLOAD
# ════════════════════════════════════════════════════════

def upload_to_youtube(video_path: str, title: str, description: str, tags: list) -> str:
    print("   Uploading to YouTube...")
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
    if creds.expired and creds.refresh_token:
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
    print(f"   Published: https://youtube.com/watch?v={video_id}")
    return video_id


# ════════════════════════════════════════════════════════
# PIPELINE
# ════════════════════════════════════════════════════════

def run_pipeline(language: str, output_path: str):
    print(f"\n{'─'*55}")
    print(f"  Starting {language} video...")
    print(f"{'─'*55}\n")
    try:
        script   = generate_script(language)
        assemble_video(script["scenes"], output_path, language)
        video_id = upload_to_youtube(
            output_path, script["title"], script["description"], script["tags"]
        )
        if os.path.exists(output_path):
            os.remove(output_path)
        print(f"  {language} done: https://youtube.com/watch?v={video_id}\n")
        return video_id
    except Exception as e:
        print(f"  {language} failed: {e}")
        if os.path.exists(output_path):
            os.remove(output_path)
        return None


def run_daily_pipeline():
    start = datetime.now()
    print(f"\n{'='*55}")
    print(f"  DAILY VIDEO BOT — {start.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"  English + Tamil | Neural Voice | Cost: Rs.0")
    print(f"{'='*55}")

    eng_id = run_pipeline("English", "final_video_english.mp4")
    tam_id = run_pipeline("Tamil",   "final_video_tamil.mp4")

    elapsed = (datetime.now() - start).seconds // 60
    print(f"\n{'='*55}")
    print(f"  Done in ~{elapsed} min")
    if eng_id: print(f"  English: https://youtube.com/watch?v={eng_id}")
    if tam_id: print(f"  Tamil:   https://youtube.com/watch?v={tam_id}")
    print(f"{'='*55}\n")

    if not eng_id and not tam_id:
        raise RuntimeError("Both pipelines failed.")


if __name__ == "__main__":
    run_daily_pipeline()
