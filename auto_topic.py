import os, re, sys, json, gc, asyncio, subprocess, urllib.request
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

BOLD_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/system/fonts/Roboto-Bold.ttf",
]
SERIF_ITALIC_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Italic.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
    "/system/fonts/NotoSerif-Italic.ttf",
]
MONO_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
    "/system/fonts/DroidSansMono.ttf",
]

F_SERIF = load_font(SERIF_ITALIC_PATHS, 54)
F_HERO = load_font(BOLD_PATHS, 118)
F_HERO_MD = load_font(BOLD_PATHS, 88)
F_MONO = load_font(MONO_PATHS, 22)

def fallback_beats(topic):
    t = re.sub(r"[^a-zA-Z0-9 ]+", "", topic).strip().upper()[:14] or "SYSTEM"
    return [
        {"top": "and before", "hero": "YOU", "accent": "ASK", "style": "eclipse_dots", "voice": f"Aur isse pehle ki tum poochho ki {topic} kaise kaam karta hai."},
        {"top": "can you", "hero": "BELIEVE", "accent": "THIS", "style": "rgb_ring", "voice": "Yakeen nahi hoga par iske peeche ek bahut simple engine chalta hai."},
        {"top": "inside the", "hero": t, "accent": "CORE", "style": "timeline", "voice": "Sabse pehle input signal ek high speed timeline mein process hota hai."},
        {"top": "that gives", "hero": "100%", "accent": "POWER", "style": "chrome", "voice": "Aur isi tarah bina ruke instant aur powerful output milta hai."},
    ]

def generate_beats_from_topic(topic: str):
    api_key = (os.getenv("OPENROUTER_API_KEY") or "").strip()
    if not api_key:
        return fallback_beats(topic)
    prompt = (
        f'Create a 5-beat viral kinetic typography short script explaining: "{topic}". '
        'Return ONLY valid JSON list of 5 objects with keys: '
        '"top" (2-3 lowercase italic connector words like "and before", "can you", "that is why"), '
        '"hero" (1 BIG UPPERCASE impact word, max 8 chars), '
        '"accent" (1 BIG UPPERCASE punch word, max 8 chars), '
        '"style" (one of: "eclipse_dots", "rgb_ring", "timeline", "chrome"), '
        '"voice" (1 natural, energetic Hinglish spoken sentence, 10-15 words).'
    )
    payload = json.dumps({
        "model": "google/gemini-2.0-flash-exp:free",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7
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
        items = json.loads(raw)
        if isinstance(items, list) and len(items) >= 3:
            styles = ["eclipse_dots", "rgb_ring", "timeline", "chrome"]
            return [
                {
                    "top": str(it.get("top") or "now look")[:22],
                    "hero": str(it.get("hero") or "POWER").upper()[:9],
                    "accent": str(it.get("accent") or "FLOW").upper()[:9],
                    "style": it.get("style") if it.get("style") in styles else styles[i % 4],
                    "voice": str(it.get("voice") or f"Step {i+1} kaam karta hai.").strip()
                }
                for i, it in enumerate(items[:6])
            ]
    except Exception as e:
        print("LLM fallback:", e)
    return fallback_beats(topic)

async def synthesize_natural_voice(text: str, out_mp3: str):
    clean_txt = re.sub(r"\s+", " ", text).strip()
    for voice in VOICES:
        for _ in range(2):
            try:
                comm = edge_tts.Communicate(clean_txt, voice, rate="+8%", pitch="+1Hz")
                await comm.save(out_mp3)
                if os.path.exists(out_mp3) and os.path.getsize(out_mp3) > 500:
                    return
            except Exception:
                await asyncio.sleep(0.3)
    from gtts import gTTS
    gTTS(text=clean_txt, lang="hi", tld="co.in", slow=False).save(out_mp3)

def draw_metallic_text(base_img, text, font, y_center):
    tmp = Image.new("L", (W, 200), 0)
    td = ImageDraw.Draw(tmp)
    tw = td.textlength(text, font=font)
    x = max(20, (W - tw) / 2)
    td.text((x, 20), text, fill=255, font=font)
    grad = Image.new("RGB", (W, 200), "#FFFFFF")
    gd = ImageDraw.Draw(grad)
    stops = [(0, (245, 245, 247)), (45, (255, 255, 255)), (75, (150, 152, 160)), (105, (245, 215, 185)), (150, (255, 248, 240))]
    for y in range(200):
        c = stops[-1][1]
        for k in range(len(stops) - 1):
            y0, c0 = stops[k]
            y1, c1 = stops[k + 1]
            if y0 <= y <= y1:
                t = (y - y0) / max(1, (y1 - y0))
                c = tuple(int(c0[j] + (c1[j] - c0[j]) * t) for j in range(3))
                break
        gd.line([(0, y), (W, y)], fill=c)
    base_img.paste(grad, (0, int(y_center - 80)), tmp)

def draw_centered(draw, text, font, y, fill):
    tw = draw.textlength(text, font=font)
    draw.text(((W - tw) / 2, y), text, font=font, fill=fill)

def render_kinetic_card(beat, idx, total, png_path):
    style = beat["style"]
    img = Image.new("RGB", (W, H), "#050507")
    glow = Image.new("RGB", (W, H), "#050507")
    gd = ImageDraw.Draw(glow)
    if style in ("eclipse_dots", "rgb_ring"):
        cx, cy = W // 2 + 30, 790 if style == "eclipse_dots" else 690
        gd.ellipse([cx - 260, cy - 260, cx + 260, cy + 260], fill="#B84A14")
        gd.ellipse([cx - 170, cy - 170, cx + 170, cy + 170], fill="#FF5A1F")
        glow = glow.filter(ImageFilter.GaussianBlur(75))
        img = Image.blend(img, glow, 0.9)
    del glow

    draw = ImageDraw.Draw(img)
    for gx in range(30, W, 95):
        for gy in range(40, H, 110):
            if (gx + gy + idx * 17) % 3 == 0:
                draw.rectangle([gx, gy, gx + 2, gy + 2], fill="#24242C")

    if style == "timeline":
        draw_centered(draw, beat["hero"], F_HERO_MD, 55, "#5A5A66")
        cx0, cy0, cx1, cy1 = 58, 270, W - 58, 635
        draw.rounded_rectangle([cx0, cy0, cx1, cy1], radius=22, fill="#16161F", outline="#2E2E3E", width=2)
        draw.rounded_rectangle([cx0 + 26, cy0 + 22, cx0 + 68, cy0 + 56], radius=8, fill="#26224A")
        draw.text((cx0 + 34, cy0 + 27), "Ae", fill="#A78BFA", font=F_MONO)
        draw.text((cx0 + 84, cy0 + 28), f"COMP 0{idx+1} - TIMELINE", fill="#CBD5E1", font=F_MONO)
        layers = [("Text", 220, 450, "#A78BFA"), ("Shape 1", 270, 520, "#93C5FD"), ("Shape 2", 200, 400, "#C4B5FD"), ("Camera", 300, 550, "#64748B"), ("Null 1", 240, 430, "#A78BFA")]
        for li, (lname, bx0, bx1, bcol) in enumerate(layers):
            ly = cy0 + 92 + li * 48
            draw.text((cx0 + 30, ly), lname, fill="#94A3B8", font=F_MONO)
            draw.rounded_rectangle([bx0, ly + 4, bx1, ly + 22], radius=6, fill=bcol)
            for kx in (bx0, bx1):
                draw.polygon([(kx, ly + 2), (kx + 9, ly + 13), (kx, ly + 24), (kx - 9, ly + 13)], fill="#FFFFFF")
        draw.line([(490, cy0 + 75), (490, cy1 - 18)], fill="#EF4444", width=3)
        draw_centered(draw, f'{beat["top"]}  {beat["accent"]}', F_SERIF, 740, "#F8FAFC")
    else:
        draw_centered(draw, beat["top"], F_SERIF, 165, "#F3F4F6")
        hero_font = F_HERO if len(beat["hero"]) <= 6 else F_HERO_MD
        draw_metallic_text(img, beat["hero"], hero_font, 330)
        acc_font = F_HERO if len(beat["accent"]) <= 6 else F_HERO_MD
        acc_col = "#FF6B1A" if style != "rgb_ring" else "#EF233C"
        draw_centered(draw, beat["accent"], acc_font, 455, acc_col)
        if style == "eclipse_dots":
            cx, cy = W // 2 + 35, 790
            draw.ellipse([cx - 115, cy - 115, cx + 115, cy + 115], fill="#050507", outline="#FF7A2F", width=4)
            draw.rounded_rectangle([cx - 145, cy - 48, cx + 145, cy + 48], radius=48, fill="#1E1F26", outline="#32343F", width=2)
            for di, dcol in enumerate(["#525461", "#FFFFFF", "#525461"]):
                dx = cx - 64 + di * 64
                draw.ellipse([dx - 14, cy - 14, dx + 14, cy + 14], fill=dcol)
            draw.text((cx - 255, cy - 24), "uh,", fill="#E5E7EB", font=F_SERIF)
            draw.text((68, 930), "?", fill="#FF6B1A", font=F_HERO_MD)
        elif style == "rgb_ring":
            cx, cy = W // 2, 760
            draw.ellipse([cx - 145, cy - 145, cx + 145, cy + 145], fill="#050507", outline="#FACC15", width=5)
            draw.ellipse([cx - 151, cy - 151, cx + 151, cy + 151], outline="#EF4444", width=3)
            draw_centered(draw, beat["accent"], F_HERO, cy - 65, "#F43F5E")
        else:
            draw.ellipse([W - 210, 820, W - 110, 920], fill="#FF6B1A")
            draw.ellipse([W - 195, 845, W - 135, 905], fill="#050507")

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
    beats = generate_beats_from_topic(topic)
    clip_paths = []
    for idx, bt in enumerate(beats):
        raw_mp3, clean_wav, png_p, clip_p = f"temp/raw_{idx}.mp3", f"temp/clean_{idx}.wav", f"temp/card_{idx}.png", f"temp/clip_{idx}.mp4"
        for f in (raw_mp3, clean_wav, png_p, clip_p):
            if os.path.exists(f):
                os.remove(f)
        await synthesize_natural_voice(bt.get("voice") or "Next step", raw_mp3)
        subprocess.run([
            "ffmpeg", "-y", "-i", raw_mp3,
            "-af", "silenceremove=start_periods=1:start_silence=0.04:start_threshold=-45dB,dynaudnorm=f=150:g=15,apad=pad_dur=0.14",
            "-ar", "44100", "-ac", "1", clean_wav
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        dur = max(1.6, float(subprocess.check_output([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", clean_wav
        ]).decode().strip()))
        frames = int(dur * 24)
        render_kinetic_card(bt, idx, len(beats), png_p)
        rgb_fx = ",rgbashift=rh=-4:bh=4:rv=2:bv=-2" if bt["style"] == "rgb_ring" else ""
        vf = f"scale=1080:1920,zoompan=z='1.12-0.12*min(on/10,1)+0.0015*on':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps=24{rgb_fx}"
        subprocess.run([
            "ffmpeg", "-y", "-i", png_p, "-i", clean_wav, "-vf", vf,
            "-c:v", "libx264", "-preset", "ultrafast", "-threads", "1",
            "-x264-params", "rc-lookahead=1:sync-lookahead=0:bframes=0",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-t", f"{dur:.2f}", clip_p
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        clip_paths.append(clip_p)

    concat_list = "temp/clips.txt"
    with open(concat_list, "w") as f:
        for cp in clip_paths:
            f.write(f"file '{os.path.abspath(cp)}'\n")
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_list, "-c", "copy", out_mp4], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    return out_mp4

if __name__ == "__main__":
    t = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "How turbine work"
    asyncio.run(generate_video(t))
