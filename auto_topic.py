import os, re, sys, json, gc, asyncio, subprocess, urllib.request
import edge_tts
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H = 720, 1280
VOICE = "hi-IN-MadhurNeural"

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
FONT_TITLE = get_font(36, bold=True)
FONT_BIG = get_font(44, bold=True)
FONT_CAP = get_font(34, bold=True)

def fallback_scenes(topic):
    t = topic.strip().title()
    return [
        {"title": t[:22], "sub": "CORE CONCEPT", "text": f"Aaj samajhte hain {topic} aakhir kaam kaise karta hai."},
        {"title": "INPUT STAGE", "sub": "STAGE 01", "text": "Sabse pehle system mein energy ya signal enter karta hai."},
        {"title": "CORE PROCESS", "sub": "STAGE 02", "text": "Iske andar main mechanism energy ko usable power mein badalta hai."},
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
    img = Image.new("RGB", (W, H), "#0B0B0E")
    draw = ImageDraw.Draw(img)
    for x in range(0, W, 60):
        draw.line([(x, 0), (x, H)], fill="#15151C", width=2)
    for y in range(0, H, 60):
        draw.line([(0, y), (W, y)], fill="#15151C", width=2)

    draw.rounded_rectangle([60, 80, 290, 132], radius=14, fill="#16161D", outline="#2E2E3A", width=2)
    draw.text((84, 94), f"NODE 0{idx+1} / 0{total}", fill="#F59E0B", font=FONT_SM)

    draw.rounded_rectangle([60, 190, W - 60, 410], radius=24, fill="#14141B", outline="#343444", width=2)
    draw.text((95, 225), scene["sub"].upper(), fill="#9CA3AF", font=FONT_SM)
    draw.text((95, 280), scene["title"].upper(), fill="#FFFFFF", font=FONT_TITLE)

    draw.line([(W // 2, 410), (W // 2, 660)], fill="#F59E0B", width=6)
    draw.ellipse([W // 2 - 16, 519, W // 2 + 16, 551], fill="#FBBF24", outline="#FFFFFF", width=3)

    draw.rounded_rectangle([60, 660, W - 60, 840], radius=24, fill="#131917", outline="#10B981", width=2)
    draw.text((95, 695), "VERIFIED STAGE", fill="#10B981", font=FONT_SM)
    draw.text((95, 745), f"STEP 0{idx+1} ACTIVE", fill="#FFFFFF", font=FONT_BIG)

    lines = wrap_text(draw, scene["text"], FONT_CAP, W - 120)
    y_cap = 920
    for line in lines:
        lw = draw.textlength(line, font=FONT_CAP)
        draw.text(((W - lw) / 2, y_cap), line, fill="#F3F4F6", font=FONT_CAP)
        y_cap += 48

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
        mp3_p = f"temp/part_{idx}.mp3"
        png_p = f"temp/card_{idx}.png"
        clip_p = f"temp/clip_{idx}.mp4"
        for f in (mp3_p, png_p, clip_p):
            if os.path.exists(f):
                os.remove(f)

        txt = (sc.get("text") or "Next step").strip()
        try:
            comm = edge_tts.Communicate(txt, VOICE, rate="+6%")
            await comm.save(mp3_p)
        except Exception:
            from gtts import gTTS
            gTTS(text=txt, lang="hi", tld="co.in").save(mp3_p)

        save_scene_card(sc, idx, len(scenes), png_p)

        subprocess.run([
            "ffmpeg", "-y",
            "-loop", "1", "-framerate", "15", "-i", png_p,
            "-i", mp3_p,
            "-c:v", "libx264", "-preset", "ultrafast", "-tune", "stillimage",
            "-threads", "1", "-x264-params", "rc-lookahead=1:sync-lookahead=0:bframes=0",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "96k", "-ar", "44100", "-ac", "1",
            "-shortest", clip_p
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
