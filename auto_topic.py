import os, re, sys, json, gc, asyncio, subprocess, urllib.request
import edge_tts
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H = 720, 1280
VOICES = ["hi-IN-MadhurNeural", "hi-IN-SwaraNeural", "en-IN-PrabhatNeural"]

def get_font(size, bold=False):
    for p in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/system/fonts/Roboto-Bold.ttf" if bold else "/system/fonts/Roboto-Regular.ttf",
    ]:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()

FONT_SM = get_font(22, bold=True)
FONT_TITLE = get_font(38, bold=True)
FONT_BIG = get_font(44, bold=True)
FONT_CAP = get_font(34, bold=True)

def fallback_scenes(topic):
    t = topic.strip().title()
    return [
        {"title": t[:22], "sub": "CORE CONCEPT", "text": f"Aaj hum aasaan bhasha mein samjhenge ki {topic} aakhir kaam kaise karta hai."},
        {"title": "INPUT STAGE", "sub": "STAGE 01", "text": "Sabse pehle is system ke andar raw energy ya input signal enter karta hai."},
        {"title": "CORE MECHANISM", "sub": "STAGE 02", "text": "Iske andar ka main mechanism is energy ko tezi se usable power mein badal deta hai."},
        {"title": "FINAL OUTPUT", "sub": "RESULT", "text": "Aur isi smart process ki wajah se humein bina ruke smooth aur reliable output milta hai."}
    ]

def generate_scenes_from_topic(topic: str):
    api_key = (os.getenv("OPENROUTER_API_KEY") or "").strip()
    if not api_key:
        return fallback_scenes(topic)
    prompt = (
        f'Create a 4-scene natural Hinglish tech explainer short script for: "{topic}". '
        'Write smooth, conversational spoken Hinglish like a top Indian tech YouTuber. '
        'Return ONLY valid JSON list of 4 objects with keys: "title" (max 3 English words), '
        '"sub" (max 3 English words), "text" (1 natural flowing Hinglish sentence, 12-18 words).'
    )
    payload = json.dumps({
        "model": "google/gemini-2.0-flash-exp:free",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.65
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://auto-reel-bot.onrender.com",
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        raw = (((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
        raw = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", raw).strip()
        scenes = json.loads(raw)
        if isinstance(scenes, list) and len(scenes) >= 2:
            return [
                {
                    "title": str(sc.get("title") or f"STEP {i+1}")[:22],
                    "sub": str(sc.get("sub") or "SYSTEM NODE")[:22],
                    "text": str(sc.get("text") or f"Step {i+1} process hota hai.").strip()
                }
                for i, sc in enumerate(scenes[:5])
            ]
    except Exception as e:
        print("LLM fallback:", e)
    return fallback_scenes(topic)

async def synthesize_natural_voice(text: str, out_mp3: str):
    clean_txt = re.sub(r"\s+", " ", text).strip()
    for voice in VOICES:
        for attempt in range(2):
            try:
                comm = edge_tts.Communicate(clean_txt, voice, rate="+4%", pitch="+0Hz")
                await comm.save(out_mp3)
                if os.path.exists(out_mp3) and os.path.getsize(out_mp3) > 500:
                    return
            except Exception:
                await asyncio.sleep(0.4)
    from gtts import gTTS
    gTTS(text=clean_txt, lang="hi", tld="co.in", slow=False).save(out_mp3)

def wrap_text(draw, text, font, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        test = f"{cur} {w}".strip()
        if draw.textlength(test, font=font) <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines[:3]

def save_scene_card(scene, idx, total, png_path):
    img = Image.new("RGB", (W, H), "#090A0F")
    glow = Image.new("RGB", (W, H), "#090A0F")
    gdraw = ImageDraw.Draw(glow)
    accent = ["#F59E0B", "#3B82F6", "#10B981", "#A855F7"][idx % 4]
    gdraw.ellipse([100, 320, 620, 860], fill="#1D2233")
    glow = glow.filter(ImageFilter.GaussianBlur(85))
    img = Image.blend(img, glow, 0.85)
    del glow

    draw = ImageDraw.Draw(img)
    for x in range(0, W, 60):
        draw.line([(x, 0), (x, H)], fill="#141722", width=2)
    for y in range(0, H, 60):
        draw.line([(0, y), (W, y)], fill="#141722", width=2)

    # Top progress bar segments
    seg_w = (W - 120 - (total - 1) * 12) // total
    for i in range(total):
        sx = 60 + i * (seg_w + 12)
        col = accent if i <= idx else "#232736"
        draw.rounded_rectangle([sx, 58, sx + seg_w, 68], radius=5, fill=col)

    # Node badge
    draw.rounded_rectangle([60, 96, 300, 148], radius=14, fill="#151823", outline=accent, width=2)
    draw.text((84, 110), f"STAGE 0{idx+1} / 0{total}", fill=accent, font=FONT_SM)

    # Main Title Card
    draw.rounded_rectangle([60, 195, W - 60, 425], radius=26, fill="#121520", outline="#2C3246", width=2)
    draw.text((95, 232), scene["sub"].upper(), fill="#9CA3AF", font=FONT_SM)
    draw.text((95, 285), scene["title"].upper(), fill="#FFFFFF", font=FONT_TITLE)

    # Glowing connector
    draw.line([(W // 2, 425), (W // 2, 655)], fill=accent, width=6)
    draw.ellipse([W // 2 - 18, 522, W // 2 + 18, 558], fill=accent, outline="#FFFFFF", width=3)

    # Active Module Card
    draw.rounded_rectangle([60, 655, W - 60, 835], radius=26, fill="#11181C", outline=accent, width=2)
    draw.text((95, 690), "LIVE MECHANISM", fill=accent, font=FONT_SM)
    draw.text((95, 742), f"PHASE 0{idx+1} ACTIVE", fill="#FFFFFF", font=FONT_BIG)

    # Caption box
    draw.rounded_rectangle([48, 895, W - 48, 1110], radius=22, fill="#0E1017", outline="#222636", width=2)
    lines = wrap_text(draw, scene["text"], FONT_CAP, W - 136)
    y_cap = 925
    for line in lines:
        lw = draw.textlength(line, font=FONT_CAP)
        draw.text(((W - lw) / 2, y_cap), line, fill="#F9FAFB", font=FONT_CAP)
        y_cap += 50

    img.save(png_path, "PNG", optimize=True)
    del img
    gc.collect()

async def generate_video(topic: str) -> str:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(base_dir)
    os.makedirs("temp", exist_ok=True)
    os.makedirs("out", exist_ok=True)

    safe_name = re.sub(r"[^a-zA-Z0-9]+", "_", topic.lower()).strip("_")[:30] or "explainer"
    out_mp4 = f"out/{safe_name}.mp4"
    scenes = generate_scenes_from_topic(topic)

    clip_paths = []
    for idx, sc in enumerate(scenes):
        raw_mp3 = f"temp/raw_{idx}.mp3"
        clean_wav = f"temp/clean_{idx}.wav"
        png_p = f"temp/card_{idx}.png"
        clip_p = f"temp/clip_{idx}.mp4"
        for f in (raw_mp3, clean_wav, png_p, clip_p):
            if os.path.exists(f):
                os.remove(f)

        await synthesize_natural_voice(sc.get("text") or "Next step", raw_mp3)

        # Trim silence & normalize voice for smooth continuous flow
        subprocess.run([
            "ffmpeg", "-y", "-i", raw_mp3,
            "-af", "silenceremove=start_periods=1:start_silence=0.05:start_threshold=-45dB,dynaudnorm=f=150:g=15,apad=pad_dur=0.22",
            "-ar", "44100", "-ac", "1", clean_wav
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

        dur_str = subprocess.check_output([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", clean_wav
        ]).decode().strip()
        dur = max(2.0, float(dur_str))
        frames = int(dur * 24)
        fade_out_st = max(0.2, dur - 0.25)

        save_scene_card(sc, idx, len(scenes), png_p)

        # Smooth 24fps zoom-in animation + fade transition via FFmpeg zoompan
        vf = (
            f"scale=1080:1920,"
            f"zoompan=z='min(zoom+0.0012,1.08)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps=24,"
            f"fade=t=in:st=0:d=0.22,fade=t=out:st={fade_out_st:.2f}:d=0.22"
        )
        subprocess.run([
            "ffmpeg", "-y",
            "-i", png_p,
            "-i", clean_wav,
            "-vf", vf,
            "-c:v", "libx264", "-preset", "ultrafast",
            "-threads", "1", "-x264-params", "rc-lookahead=1:sync-lookahead=0:bframes=0",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k",
            "-t", f"{dur:.2f}", clip_p
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        clip_paths.append(clip_p)

    concat_list = "temp/clips.txt"
    with open(concat_list, "w") as f:
        for cp in clip_paths:
            f.write(f"file '{os.path.abspath(cp)}'\n")

    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_list,
        "-c", "copy", out_mp4
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    return out_mp4

if __name__ == "__main__":
    t = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "How turbine work"
    asyncio.run(generate_video(t))
