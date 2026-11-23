import os, re, sys, json, math, asyncio, subprocess, urllib.request
import edge_tts
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H = 720, 1280
FPS = 24
VOICE = "hi-IN-MadhurNeural"

def get_font(size, bold=False):
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/system/fonts/Roboto-Bold.ttf" if bold else "/system/fonts/Roboto-Regular.ttf",
    ]
    for p in paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()

FONT_SM = get_font(22, bold=True)
FONT_TITLE = get_font(34, bold=True)
FONT_BIG = get_font(48, bold=True)
FONT_CAP = get_font(36, bold=True)

def build_base_bg():
    bg = Image.new("RGB", (W, H), "#0B0B0E")
    glow = Image.new("RGB", (W, H), "#0B0B0E")
    gdraw = ImageDraw.Draw(glow)
    gdraw.ellipse([90, 340, 630, 880], fill="#241B10")
    glow = glow.filter(ImageFilter.GaussianBlur(90))
    bg = Image.blend(bg, glow, 0.85)
    draw = ImageDraw.Draw(bg)
    for x in range(0, W, 60):
        draw.line([(x, 0), (x, H)], fill="#141419", width=2)
    for y in range(0, H, 60):
        draw.line([(0, y), (W, y)], fill="#141419", width=2)
    return bg

BASE_BG = build_base_bg()

def fallback_scenes(topic):
    t = topic.strip().title()
    return [
        {"title": t[:28], "sub": "CORE CONCEPT", "text": f"Aaj samajhte hain {topic} aakhir kaam kaise karta hai."},
        {"title": "INPUT & TRIGGER", "sub": "STAGE 01", "text": "Sabse pehle system mein energy ya signal enter karta hai."},
        {"title": "CORE MECHANISM", "sub": "STAGE 02", "text": "Iske andar main mechanism is energy ko usable power mein convert karta hai."},
        {"title": "FINAL OUTPUT", "sub": "RESULT", "text": "Aur isi tarah bina ruke fast aur reliable output milta hai."}
    ]

def generate_scenes_from_topic(topic: str):
    api_key = (os.getenv("OPENROUTER_API_KEY") or "").strip()
    if not api_key:
        return fallback_scenes(topic)
    prompt = (
        f'Create a 4-scene Hinglish tech explainer short script for: "{topic}". '
        'Return ONLY valid JSON list of 4 objects with keys: "title" (max 3 English words), '
        '"sub" (max 3 English words), "text" (1 short Hinglish voiceover sentence, max 16 words).'
    )
    payload = json.dumps({
        "model": "google/gemini-2.0-flash-exp:free",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.6
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
        with urllib.request.urlopen(req, timeout=25) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        raw = (((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
        raw = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", raw).strip()
        scenes = json.loads(raw)
        if isinstance(scenes, list) and len(scenes) >= 2:
            clean = []
            for i, sc in enumerate(scenes[:5]):
                clean.append({
                    "title": str(sc.get("title") or f"STEP {i+1}")[:28],
                    "sub": str(sc.get("sub") or "SYSTEM NODE")[:28],
                    "text": str(sc.get("text") or f"Step {i+1} process hota hai.").strip()
                })
            return clean
    except Exception as e:
        print("LLM fallback used:", e)
    return fallback_scenes(topic)

async def generate_audio_and_timings(scenes):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(base_dir)
    os.makedirs("temp", exist_ok=True)
    os.makedirs("out", exist_ok=True)

    timings = []
    current_time = 0.0
    audio_parts = []

    for idx, scene in enumerate(scenes):
        part_mp3 = f"temp/part_{idx}.mp3"
        if os.path.exists(part_mp3):
            os.remove(part_mp3)
        txt = (scene.get("text") or "Next step").strip()
        try:
            communicate = edge_tts.Communicate(txt, VOICE, rate="+6%")
            await communicate.save(part_mp3)
        except Exception:
            from gtts import gTTS
            gTTS(text=txt, lang="hi", tld="co.in").save(part_mp3)

        if not os.path.exists(part_mp3) or os.path.getsize(part_mp3) < 200:
            raise RuntimeError(f"Audio file empty for scene {idx}")

        dur_out = subprocess.check_output([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", part_mp3
        ]).decode().strip()
        dur = max(1.5, float(dur_out) + 0.25)
        timings.append({"start": current_time, "end": current_time + dur, "duration": dur})
        current_time += dur
        audio_parts.append(part_mp3)

    concat_txt = "temp/concat.txt"
    with open(concat_txt, "w") as f:
        for p in audio_parts:
            f.write(f"file '{os.path.abspath(p)}'\n")

    voice_raw = "temp/voice_raw.mp3"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_txt, "-c:a", "libmp3lame", "-ar", "44100", "-ac", "1", voice_raw],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
    )
    return timings, current_time

def wrap_text(draw, text, font, max_w):
    words = text.split()
    lines, cur = [], ""
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

def render_frame(scene, prog, idx, total):
    img = BASE_BG.copy()
    draw = ImageDraw.Draw(img)

    # Top status badge
    draw.rounded_rectangle([60, 70, 290, 122], radius=14, fill="#16161D", outline="#2E2E3A", width=2)
    draw.text((84, 84), f"NODE 0{idx+1} / 0{total}", fill="#F59E0B", font=FONT_SM)

    # Top card
    draw.rounded_rectangle([60, 180, W - 60, 390], radius=24, fill="#14141B", outline="#343444", width=2)
    draw.text((95, 215), scene["sub"].upper(), fill="#9CA3AF", font=FONT_SM)
    draw.text((95, 265), scene["title"].upper(), fill="#FFFFFF", font=FONT_TITLE)

    # Animated energy line + pulse dot
    y1, y2 = 390, 670
    draw.line([(W // 2, y1), (W // 2, y2)], fill="#F59E0B", width=6)
    dot_y = int(y1 + (y2 - y1) * min(1.0, max(0.0, prog)))
    r = int(14 + 4 * math.sin(prog * math.pi * 4))
    draw.ellipse([W // 2 - r, dot_y - r, W // 2 + r, dot_y + r], fill="#FBBF24", outline="#FFFFFF", width=3)

    # Bottom active card
    draw.rounded_rectangle([60, 670, W - 60, 860], radius=24, fill="#131917", outline="#10B981", width=2)
    draw.text((95, 

cd ~/cloud-reel-bot
cat << 'EOF' > auto_topic.py
import os, re, sys, json, math, asyncio, subprocess, urllib.request
import edge_tts
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H = 720, 1280
FPS = 24
VOICE = "hi-IN-MadhurNeural"

def get_font(size, bold=False):
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/system/fonts/Roboto-Bold.ttf" if bold else "/system/fonts/Roboto-Regular.ttf",
    ]
    for p in paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()

FONT_SM = get_font(22, bold=True)
FONT_TITLE = get_font(34, bold=True)
FONT_BIG = get_font(48, bold=True)
FONT_CAP = get_font(36, bold=True)

def build_base_bg():
    bg = Image.new("RGB", (W, H), "#0B0B0E")
    glow = Image.new("RGB", (W, H), "#0B0B0E")
    gdraw = ImageDraw.Draw(glow)
    gdraw.ellipse([90, 340, 630, 880], fill="#241B10")
    glow = glow.filter(ImageFilter.GaussianBlur(90))
    bg = Image.blend(bg, glow, 0.85)
    draw = ImageDraw.Draw(bg)
    for x in range(0, W, 60):
        draw.line([(x, 0), (x, H)], fill="#141419", width=2)
    for y in range(0, H, 60):
        draw.line([(0, y), (W, y)], fill="#141419", width=2)
    return bg

BASE_BG = build_base_bg()

def fallback_scenes(topic):
    t = topic.strip().title()
    return [
        {"title": t[:28], "sub": "CORE CONCEPT", "text": f"Aaj samajhte hain {topic} aakhir kaam kaise karta hai."},
        {"title": "INPUT & TRIGGER", "sub": "STAGE 01", "text": "Sabse pehle system mein energy ya signal enter karta hai."},
        {"title": "CORE MECHANISM", "sub": "STAGE 02", "text": "Iske andar main mechanism is energy ko usable power mein convert karta hai."},
        {"title": "FINAL OUTPUT", "sub": "RESULT", "text": "Aur isi tarah bina ruke fast aur reliable output milta hai."}
    ]

def generate_scenes_from_topic(topic: str):
    api_key = (os.getenv("OPENROUTER_API_KEY") or "").strip()
    if not api_key:
        return fallback_scenes(topic)
    prompt = (
        f'Create a 4-scene Hinglish tech explainer short script for: "{topic}". '
        'Return ONLY valid JSON list of 4 objects with keys: "title" (max 3 English words), '
        '"sub" (max 3 English words), "text" (1 short Hinglish voiceover sentence, max 16 words).'
    )
    payload = json.dumps({
        "model": "google/gemini-2.0-flash-exp:free",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.6
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
        with urllib.request.urlopen(req, timeout=25) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        raw = (((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
        raw = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", raw).strip()
        scenes = json.loads(raw)
        if isinstance(scenes, list) and len(scenes) >= 2:
            clean = []
            for i, sc in enumerate(scenes[:5]):
                clean.append({
                    "title": str(sc.get("title") or f"STEP {i+1}")[:28],
                    "sub": str(sc.get("sub") or "SYSTEM NODE")[:28],
                    "text": str(sc.get("text") or f"Step {i+1} process hota hai.").strip()
                })
            return clean
    except Exception as e:
        print("LLM fallback used:", e)
    return fallback_scenes(topic)

async def generate_audio_and_timings(scenes):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(base_dir)
    os.makedirs("temp", exist_ok=True)
    os.makedirs("out", exist_ok=True)

    timings = []
    current_time = 0.0
    audio_parts = []

    for idx, scene in enumerate(scenes):
        part_mp3 = f"temp/part_{idx}.mp3"
        if os.path.exists(part_mp3):
            os.remove(part_mp3)
        txt = (scene.get("text") or "Next step").strip()
        try:
            communicate = edge_tts.Communicate(txt, VOICE, rate="+6%")
            await communicate.save(part_mp3)
        except Exception:
            from gtts import gTTS
            gTTS(text=txt, lang="hi", tld="co.in").save(part_mp3)

        if not os.path.exists(part_mp3) or os.path.getsize(part_mp3) < 200:
            raise RuntimeError(f"Audio file empty for scene {idx}")

        dur_out = subprocess.check_output([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", part_mp3
        ]).decode().strip()
        dur = max(1.5, float(dur_out) + 0.25)
        timings.append({"start": current_time, "end": current_time + dur, "duration": dur})
        current_time += dur
        audio_parts.append(part_mp3)

    concat_txt = "temp/concat.txt"
    with open(concat_txt, "w") as f:
        for p in audio_parts:
            f.write(f"file '{os.path.abspath(p)}'\n")

    voice_raw = "temp/voice_raw.mp3"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_txt, "-c:a", "libmp3lame", "-ar", "44100", "-ac", "1", voice_raw],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
    )
    return timings, current_time

def wrap_text(draw, text, font, max_w):
    words = text.split()
    lines, cur = [], ""
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

def render_frame(scene, prog, idx, total):
    img = BASE_BG.copy()
    draw = ImageDraw.Draw(img)

    # Top status badge
    draw.rounded_rectangle([60, 70, 290, 122], radius=14, fill="#16161D", outline="#2E2E3A", width=2)
    draw.text((84, 84), f"NODE 0{idx+1} / 0{total}", fill="#F59E0B", font=FONT_SM)

    # Top card
    draw.rounded_rectangle([60, 180, W - 60, 390], radius=24, fill="#14141B", outline="#343444", width=2)
    draw.text((95, 215), scene["sub"].upper(), fill="#9CA3AF", font=FONT_SM)
    draw.text((95, 265), scene["title"].upper(), fill="#FFFFFF", font=FONT_TITLE)

    # Animated energy line + pulse dot
    y1, y2 = 390, 670
    draw.line([(W // 2, y1), (W // 2, y2)], fill="#F59E0B", width=6)
    dot_y = int(y1 + (y2 - y1) * min(1.0, max(0.0, prog)))
    r = int(14 + 4 * math.sin(prog * math.pi * 4))
    draw.ellipse([W // 2 - r, dot_y - r, W // 2 + r, dot_y + r], fill="#FBBF24", outline="#FFFFFF", width=3)

    # Bottom active card
    draw.rounded_rectangle([60, 670, W - 60, 860], radius=24, fill="#131917", outline="#10B981", width=2)
    draw.text((95, 705), "ACTIVE PROCESS", fill="#10B981", font=FONT_SM)
    draw.text((95, 755), f"{int(prog * 100)}% COMPLETE", fill="#FFFFFF", font=FONT_BIG)

    # Captions at bottom
    lines = wrap_text(draw, scene["text"], FONT_CAP, W - 120)
    y_cap = 950
    for line in lines:
        lw = draw.textlength(line, font=FONT_CAP)
        draw.text(((W - lw) / 2, y_cap), line, fill="#F3F4F6", font=FONT_CAP)
        y_cap += 50

    return img.convert("RGB").resize((W, H))

async def generate_video(topic: str) -> str:
    safe_name = re.sub(r"[^a-zA-Z0-9]+", "_", topic.lower()).strip("_")[:30] or "explainer"
    out_mp4 = f"out/{safe_name}.mp4"

    scenes = generate_scenes_from_topic(topic)
    timings, total_dur = await generate_audio_and_timings(scenes)

    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-f", "rawvideo", "-vcodec", "rawvideo",
        "-s", f"{W}x{H}", "-pix_fmt", "rgb24", "-r", str(FPS),
        "-i", "-",
        "-i", "temp/voice_raw.mp3",
        "-c:v", "libx264", "-preset", "ultrafast", "-threads", "1",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-shortest",
        out_mp4
    ]
    proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    total_frames = max(1, int(total_dur * FPS))
    try:
        for f_idx in range(total_frames):
            t = f_idx / FPS
            active_idx = len(scenes) - 1
            prog = 1.0
            for s_idx, tm in enumerate(timings):
                if tm["start"] <= t <= tm["end"]:
                    active_idx = s_idx
                    prog = (t - tm["start"]) / max(0.01, tm["duration"])
                    break
            frame = render_frame(scenes[active_idx], prog, active_idx, len(scenes))
            proc.stdin.write(frame.tobytes())
        proc.stdin.close()
    except BrokenPipeError:
        err = proc.stderr.read().decode(errors="ignore")[-400:]
        raise RuntimeError(f"FFmpeg pipe closed: {err}")

    ret = proc.wait()
    if ret != 0:
        err = proc.stderr.read().decode(errors="ignore")[-400:]
        raise RuntimeError(f"FFmpeg failed ({ret}): {err}")
    return out_mp4

if __name__ == "__main__":
    topic_arg = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "How P2P works"
    asyncio.run(generate_video(topic_arg))
