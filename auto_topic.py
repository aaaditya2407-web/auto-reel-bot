import os, re, sys, json, gc, asyncio, subprocess, urllib.request, urllib.parse
import edge_tts
from PIL import Image, ImageDraw, ImageFont

W, H = 720, 1280
VOICES = ["hi-IN-MadhurNeural", "hi-IN-SwaraNeural", "en-IN-PrabhatNeural"]
LLM_MODELS = [
    "openrouter/free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "qwen/qwen-2.5-72b-instruct:free",
    "google/gemini-2.0-flash-exp:free",
]

def load_font(paths, size):
    for p in paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()

F_CAP = load_font(["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/system/fonts/Roboto-Bold.ttf"], 52)
F_SUB = load_font(["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/system/fonts/Roboto-Bold.ttf"], 30)

def smart_fallback_scenes(topic: str):
    clean_t = re.sub(r"[^a-zA-Z0-9 ]+", " ", topic).strip()
    short_t = " ".join(clean_t.split()[:6]) or "this process"
    return [
        {"cap": "watch closely", "prompt": f"3D medical educational animation of {short_t}, transparent human anatomy cutaway, glowing arrows, studio lighting, Zack D Films style, vertical 9:16", "voice": f"Aaj hum 3D animation ki madad se {short_t} ko detail mein samjhenge."},
        {"cap": "step one", "prompt": f"3D Blender close up render showing first stage of {short_t}, glowing blue airflow arrows, transparent body model, Cinema 4D, vertical 9:16", "voice": "Sabse pehle is process ka starting stage activate hota hai aur energy andar aati hai."},
        {"cap": "inside the body", "prompt": f"3D CGI anatomical cross section showing internal mechanism of {short_t}, expansion and movement, glowing highlights, Zack D Films style, vertical 9:16", "voice": "Iske baad andar ke main organs ya parts expand hokar apna kaam shuru karte hain."},
        {"cap": "final release", "prompt": f"3D educational render showing completion and release phase of {short_t}, clear directional arrows, realistic 3D textures, vertical 9:16", "voice": "Aur aakhir mein contraction ke saath ye cycle poori hoti hai."},
    ]

def generate_scenes_from_topic(topic: str):
    api_key = (os.getenv("OPENROUTER_API_KEY") or "").strip()
    if not api_key:
        return smart_fallback_scenes(topic)
    sys_prompt = (
        "You are a Zack D. Films 3D educational Shorts director. Break the user's topic or visual prompt into 5 sequential 3D scenes. "
        'Return ONLY a valid JSON array of 5 objects with keys: '
        '"cap" (2-3 lowercase bold subtitle words describing the action, e.g. "air enters nose", "lungs expand", "air flows out"), '
        '"prompt" (detailed English 3D Blender/Cinema4D CGI scene prompt for image generation, include lighting, transparent cutaway, arrows if needed, no text), '
        '"voice" (1 natural, crisp Hinglish voiceover sentence, 10-14 words explaining that exact visual step).'
    )
    for model in LLM_MODELS:
        payload = json.dumps({
            "model": model,
            "messages": [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": topic[:600]}
            ],
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
            with urllib.request.urlopen(req, timeout=18) as resp:
                raw = (((json.loads(resp.read().decode()).get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
            raw = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", raw).strip()
            m = re.search(r"\[.*\]", raw, re.S)
            items = json.loads(m.group(0) if m else raw)
            if isinstance(items, list) and len(items) >= 3:
                return [
                    {
                        "cap": str(it.get("cap") or f"step {i+1}").lower()[:26],
                        "prompt": str(it.get("prompt") or f"3D CGI educational animation of {topic[:80]}, Zack D Films style"),
                        "voice": str(it.get("voice") or f"Ab agle step mein ye process aage badhta hai.").strip()
                    }
                    for i, it in enumerate(items[:5])
                ]
        except Exception as e:
            print(f"Model {model} skipped:", e)
    return smart_fallback_scenes(topic)

async def synthesize_natural_voice(text: str, out_mp3: str):
    clean_txt = re.sub(r"\s+", " ", text).strip()
    for voice in VOICES:
        for _ in range(2):
            try:
                await edge_tts.Communicate(clean_txt, voice, rate="+8%", pitch="+1Hz").save(out_mp3)
                if os.path.exists(out_mp3) and os.path.getsize(out_mp3) > 500:
                    return
            except Exception:
                await asyncio.sleep(0.25)
    from gtts import gTTS
    gTTS(text=clean_txt, lang="hi", tld="co.in").save(out_mp3)

def fetch_3d_cgi(prompt: str, seed: int, out_png: str) -> bool:
    full_prompt = f"{prompt}, 3d medical educational animation, Blender Cycles render, crisp studio lighting, no text, no watermark"
    for model in ("turbo", "flux"):
        try:
            url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(full_prompt)}?width=720&height=1280&seed={seed}&nologo=true&model={model}"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=22) as resp:
                raw = resp.read()
            if len(raw) > 4000:
                tmp_f = out_png + ".tmp"
                with open(tmp_f, "wb") as f:
                    f.write(raw)
                Image.open(tmp_f).convert("RGB").resize((W, H), Image.LANCZOS).save(out_png, "PNG")
                os.remove(tmp_f)
                return True
        except Exception as e:
            print(f"Image {model} retry:", e)
    return False

def draw_zack_caption(img, cap_text: str):
    draw = ImageDraw.Draw(img)
    cap = cap_text.strip()
    if not cap:
        return
    tw = draw.textlength(cap, font=F_CAP)
    x = max(24, (W - tw) / 2)
    draw.text((x, 895), cap, font=F_CAP, fill="#FFFFFF", stroke_width=6, stroke_fill="#000000")

async def generate_video(topic: str) -> str:
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    os.makedirs("temp", exist_ok=True)
    os.makedirs("out", exist_ok=True)
    out_mp4 = f"out/{re.sub(r'[^a-zA-Z0-9]+', '_', topic.lower()).strip('_')[:28] or 'explainer'}.mp4"
    scenes = generate_scenes_from_topic(topic)

    clips = []
    for idx, sc in enumerate(scenes):
        raw_m, wav_p, png_p, clp_p = f"temp/r_{idx}.mp3", f"temp/w_{idx}.wav", f"temp/p_{idx}.png", f"temp/c_{idx}.mp4"
        for f in (raw_m, wav_p, png_p, clp_p):
            if os.path.exists(f):
                os.remove(f)

        await synthesize_natural_voice(sc.get("voice") or "Next step", raw_m)
        subprocess.run([
            "ffmpeg", "-y", "-i", raw_m,
            "-af", "silenceremove=start_periods=1:start_silence=0.04:start_threshold=-45dB,dynaudnorm=f=150:g=15,apad=pad_dur=0.14",
            "-ar", "44100", "-ac", "1", wav_p
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

        dur = max(1.8, float(subprocess.check_output([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", wav_p
        ]).decode().strip()))
        frames = int(dur * 24)

        ok = fetch_3d_cgi(sc["prompt"], 200 + idx * 41, png_p)
        if not ok:
            im = Image.new("RGB", (W, H), "#0B0E17")
            d = ImageDraw.Draw(im)
            d.text((80, 560), sc["cap"].upper(), fill="#38BDF8", font=F_CAP)
            im.save(png_p, "PNG")
            del im

        im = Image.open(png_p).convert("RGB")
        draw_zack_caption(im, sc["cap"])
        im.save(png_p, "PNG", optimize=True)
        del im
        gc.collect()

        # Alternate smooth push-in and subtle pan per scene
        if idx % 2 == 0:
            vf = f"scale=1080:1920,zoompan=z='min(zoom+0.0022,1.14)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps=24"
        else:
            vf = f"scale=1080:1920,zoompan=z='1.12':x='iw/2-(iw/zoom/2)-20+on*0.5':y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps=24"

        subprocess.run([
            "ffmpeg", "-y", "-i", png_p, "-i", wav_p, "-vf", vf,
            "-c:v", "libx264", "-preset", "ultrafast", "-threads", "1",
            "-x264-params", "rc-lookahead=1:sync-lookahead=0:bframes=0",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-t", f"{dur:.2f}", clp_p
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        clips.append(clp_p)

    with open("temp/clips.txt", "w") as f:
        for c in clips:
            f.write(f"file '{os.path.abspath(c)}'\n")
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "temp/clips.txt", "-c", "copy", out_mp4], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    return out_mp4

if __name__ == "__main__":
    asyncio.run(generate_video(" ".join(sys.argv[1:]) or "How human breathing works"))
