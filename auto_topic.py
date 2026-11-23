import os, re, sys, json, gc, asyncio, subprocess, urllib.request, urllib.parse
import edge_tts
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H = 720, 1280
VOICES = ["hi-IN-MadhurNeural", "hi-IN-SwaraNeural", "en-IN-PrabhatNeural"]

def load_font(paths, size):
    for p in paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()

BOLD_P = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/system/fonts/Roboto-Bold.ttf"]
SERIF_P = ["/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"]
F_CAP = load_font(BOLD_P, 54)
F_SERIF = load_font(SERIF_P, 52)
F_HERO = load_font(BOLD_P, 112)
F_HERO_MD = load_font(BOLD_P, 82)

def fallback_scenes(topic):
    t = re.sub(r"[^a-zA-Z0-9 ]+", "", topic).strip().upper()[:12] or "SYSTEM"
    return [
        {"mode": "kinetic", "top": "and before", "hero": "YOU", "accent": "ASK", "cap": "before you ask", "prompt": "", "voice": f"Aur isse pehle ki tum poochho ki {topic} kaise kaam karta hai."},
        {"mode": "3d", "top": "", "hero": t, "accent": "3D", "cap": "inside the system", "prompt": f"3D Blender cutaway render explaining {topic}, glowing yellow highlight, studio lighting, Zack D Films style, vertical 9:16", "voice": "Iske andar ek high precision mechanism laga hota hai jo energy ko control karta hai."},
        {"mode": "3d", "top": "", "hero": "CORE", "accent": "FLOW", "cap": "under pressure", "prompt": f"3D CGI simulation of {topic} working under pressure, glowing energy flow, Cinema 4D render, vertical 9:16", "voice": "Jaise hi pressure badhta hai, iske internal parts tezi se kaam karne lagte hain."},
        {"mode": "kinetic", "top": "that gives", "hero": "100%", "accent": "POWER", "cap": "pure power", "prompt": "", "voice": "Aur isi tarah bina ruke humein instant aur powerful output milta hai."},
    ]

def generate_scenes_from_topic(topic: str):
    api_key = (os.getenv("OPENROUTER_API_KEY") or "").strip()
    if not api_key:
        return fallback_scenes(topic)
    prompt = f'Create a 4-scene viral Shorts script for "{topic}". Return ONLY JSON list of 4 objects with keys: "mode" ("kinetic" or "3d"), "top" (2 italic words), "hero" (1 BIG word), "accent" (1 BIG word), "cap" (2-3 bold subtitle words), "prompt" (3D Blender CGI render prompt), "voice" (1 natural Hinglish sentence).'
    payload = json.dumps({"model": "google/gemini-2.0-flash-exp:free", "messages": [{"role": "user", "content": prompt}], "temperature": 0.7}).encode()
    req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", data=payload, headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=18) as resp:
            raw = (((json.loads(resp.read().decode()).get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
        items = json.loads(re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", raw).strip())
        if isinstance(items, list) and len(items) >= 3:
            return [{"mode": "kinetic" if i in (0, len(items[:4])-1) else "3d", "top": str(it.get("top") or "now look")[:20], "hero": str(it.get("hero") or "CORE").upper()[:8], "accent": str(it.get("accent") or "FLOW").upper()[:8], "cap": str(it.get("cap") or "watch closely").lower()[:24], "prompt": str(it.get("prompt") or f"3D CGI render of {topic}, Zack D Films style"), "voice": str(it.get("voice") or f"Step {i+1} process hota hai.").strip()} for i, it in enumerate(items[:4])]
    except Exception:
        pass
    return fallback_scenes(topic)

async def synthesize_natural_voice(text: str, out_mp3: str):
    clean_txt = re.sub(r"\s+", " ", text).strip()
    for voice in VOICES:
        for _ in range(2):
            try:
                await edge_tts.Communicate(clean_txt, voice, rate="+8%", pitch="+1Hz").save(out_mp3)
                if os.path.exists(out_mp3) and os.path.getsize(out_mp3) > 500:
                    return
            except Exception:
                await asyncio.sleep(0.3)
    from gtts import gTTS
    gTTS(text=clean_txt, lang="hi", tld="co.in").save(out_mp3)

def fetch_3d_cgi(prompt: str, seed: int, out_png: str) -> bool:
    try:
        url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(prompt + ', 3d render, octane, no text')}?width=720&height=1280&seed={seed}&nologo=true&model=flux"
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=20) as resp:
            raw = resp.read()
        if len(raw) < 4000:
            return False
        with open(out_png + ".tmp", "wb") as f:
            f.write(raw)
        Image.open(out_png + ".tmp").convert("RGB").resize((W, H), Image.LANCZOS).save(out_png, "PNG")
        os.remove(out_png + ".tmp")
        return True
    except Exception:
        return False

def draw_centered(draw, text, font, y, fill, stroke=0):
    tw = draw.textlength(text, font=font)
    draw.text(((W - tw) / 2, y), text, font=font, fill=fill, stroke_width=stroke, stroke_fill="#000000")

def render_kinetic(sc, idx, png_path):
    img = Image.new("RGB", (W, H), "#050507")
    glow = Image.new("RGB", (W, H), "#050507")
    gd = ImageDraw.Draw(glow)
    cx, cy = W // 2 + 25, 760
    gd.ellipse([cx - 240, cy - 240, cx + 240, cy + 240], fill="#B84A14")
    gd.ellipse([cx - 150, cy - 150, cx + 150, cy + 150], fill="#FF5A1F")
    img = Image.blend(img, glow.filter(ImageFilter.GaussianBlur(70)), 0.9)
    draw = ImageDraw.Draw(img)
    draw_centered(draw, sc["top"], F_SERIF, 170, "#F3F4F6")
    draw_centered(draw, sc["hero"], F_HERO if len(sc["hero"]) <= 6 else F_HERO_MD, 260, "#E5E7EB")
    draw_centered(draw, sc["accent"], F_HERO if len(sc["accent"]) <= 6 else F_HERO_MD, 430, "#FF6B1A" if idx == 0 else "#EF233C")
    draw.ellipse([cx - 115, cy - 115, cx + 115, cy + 115], fill="#050507", outline="#FF7A2F", width=5)
    if idx == 0:
        draw.rounded_rectangle([cx - 135, cy - 42, cx + 135, cy + 42], radius=42, fill="#1E1F26", outline="#32343F", width=2)
        for di, dcol in enumerate(["#525461", "#FFFFFF", "#525461"]):
            draw.ellipse([cx - 56 + di * 56 - 12, cy - 12, cx - 56 + di * 56 + 12, cy + 12], fill=dcol)
    img.save(png_path, "PNG", optimize=True)
    del img, glow; gc.collect()

async def generate_video(topic: str) -> str:
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    os.makedirs("temp", exist_ok=True); os.makedirs("out", exist_ok=True)
    out_mp4 = f"out/{re.sub(r'[^a-zA-Z0-9]+', '_', topic.lower()).strip('_')[:30] or 'explainer'}.mp4"
    scenes = generate_scenes_from_topic(topic)
    clips = []
    for idx, sc in enumerate(scenes):
        raw_m, wav_p, png_p, clp_p = f"temp/r_{idx}.mp3", f"temp/w_{idx}.wav", f"temp/p_{idx}.png", f"temp/c_{idx}.mp4"
        await synthesize_natural_voice(sc.get("voice") or "Next step", raw_m)
        subprocess.run(["ffmpeg", "-y", "-i", raw_m, "-af", "silenceremove=start_periods=1:start_silence=0.04:start_threshold=-45dB,dynaudnorm=f=150:g=15,apad=pad_dur=0.14", "-ar", "44100", "-ac", "1", wav_p], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        dur = max(1.8, float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", wav_p]).decode().strip()))
        frames = int(dur * 24)
        if sc["mode"] == "3d" and fetch_3d_cgi(sc["prompt"], 100 + idx * 37, png_p):
            im = Image.open(png_p).convert("RGB")
            draw_centered(ImageDraw.Draw(im), sc["cap"], F_CAP, 890, "#FFFFFF", stroke=6)
            im.save(png_p, "PNG", optimize=True); del im; gc.collect()
            vf = f"scale=1080:1920,zoompan=z='min(zoom+0.0022,1.14)':x='iw/2-(iw/zoom/2)+on*0.3':y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps=24"
        else:
            render_kinetic(sc, idx, png_p)
            rgb = ",rgbashift=rh=-4:bh=4:rv=2:bv=-2" if idx > 0 else ""
            vf = f"scale=1080:1920,zoompan=z='1.12-0.12*min(on/10,1)+0.0015*on':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps=24{rgb}"
        subprocess.run(["ffmpeg", "-y", "-i", png_p, "-i", wav_p, "-vf", vf, "-c:v", "libx264", "-preset", "ultrafast", "-threads", "1", "-x264-params", "rc-lookahead=1:sync-lookahead=0:bframes=0", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-t", f"{dur:.2f}", clp_p], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        clips.append(clp_p)
    with open("temp/clips.txt", "w") as f:
        for c in clips:
            f.write(f"file '{os.path.abspath(c)}'\n")
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "temp/clips.txt", "-c", "copy", out_mp4], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    return out_mp4

if __name__ == "__main__":
    asyncio.run(generate_video(" ".join(sys.argv[1:]) or "How turbine work"))
