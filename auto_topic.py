import asyncio
import json
import math
import os
import re
import subprocess
import sys
import requests
import edge_tts
from PIL import Image, ImageDraw, ImageFont, ImageFilter

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

W, H = 720, 1280
FPS = 24
VOICE = "hi-IN-MadhurNeural"

def ease_out_cubic(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1.0 - pow(1.0 - t, 3)

def generate_scenes_from_topic(topic: str):
    prompt = f"""
You are a viral Hinglish tech explainer creator like @samjho.exe.
Create a 5-scene short video script explaining: "{topic}".
Return ONLY valid JSON (no markdown, no backticks) as a list of objects with these exact keys:
- "text": short punchy Hinglish sentence (max 14 words)
- "highlight": 1 or 2 exact words from "text" to highlight in gold
- "tag": "SYSTEM.EXE • EP 01"
- "pill": 2-word uppercase category badge
- "mode": choose ONLY from ["central", "p2p_direct", "mesh", "escrow", "counter"]
- "metric_label": short uppercase HUD label (e.g., "LATENCY", "SECURITY", "EFFICIENCY")
- "metric_val": short uppercase value (e.g., "0.02 SEC", "100% VERIFIED", "₹0 FEE")
- "metric_color": choose from ["#F5B041", "#2ECC71", "#E74C3C"]
- "node_a": top box title (e.g., "USER DEVICE")
- "node_mid": middle box title (used if mode is "central")
- "node_b": bottom box title (e.g., "TARGET SERVER")
- "counter_target": integer number (used if mode is "counter", e.g. 50000)
- "counter_prefix": string prefix (e.g. "₹" or "")
- "counter_suffix": string suffix (e.g. " CR" or " TPS")
"""
    if OPENROUTER_API_KEY:
        res = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
            json={
                "model": "openrouter/free",
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=35
        )
        res.raise_for_status()
        raw = res.json()["choices"][0]["message"]["content"]
    elif GEMINI_API_KEY:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
        res = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=35)
        res.raise_for_status()
        raw = res.json()["candidates"][0]["content"]["parts"][0]["text"]
    else:
        raise ValueError("Set OPENROUTER_API_KEY or GEMINI_API_KEY first!")

    cleaned = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    return json.loads(cleaned)

def get_font(size, bold=False):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/system/fonts/DroidSans-Bold.ttf" if bold else "/system/fonts/DroidSans.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()

FONT_MONO_SM = get_font(26, bold=True)
FONT_MONO_LG = get_font(42, bold=True)
FONT_COUNTER = get_font(96, bold=True)
FONT_CARD_TITLE = get_font(34, bold=True)
FONT_CARD_SUB = get_font(24, bold=False)
FONT_CAPTION = get_font(54, bold=True)

def build_base_background():
    bg = Image.new("RGB", (W, H), "#0B0B0E")
    # Warm radial glow in center
    glow = Image.new("RGB", (W, H), "#0B0B0E")
    gdraw = ImageDraw.Draw(glow)
    gdraw.ellipse([140, 520, 940, 1320], fill="#241B10")
    glow = glow.filter(ImageFilter.GaussianBlur(140))
    bg = Image.blend(bg, glow, 0.85)
    draw = ImageDraw.Draw(bg)
    for x in range(0, W, 80):
        draw.line([(x, 0), (x, H)], fill="#141419", width=2)
    for y in range(0, H, 80):
        draw.line([(0, y), (W, y)], fill="#141419", width=2)
    return bg

BASE_BG = build_base_background()

async def generate_audio_and_timings(scenes):
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    os.makedirs("temp", exist_ok=True); os.makedirs("out", exist_ok=True)
    timings = []
    current_time = 0.0
    audio_parts = []

    for idx, scene in enumerate(scenes):
        part_mp3 = f"temp/part_{idx}.mp3"
        txt = (scene.get("text") or "Next step").strip()
        try:
            communicate = edge_tts.Communicate(txt, VOICE, rate="+8%")
            await communicate.save(part_mp3)
        except Exception:
            from gtts import gTTS
            gTTS(text=txt, lang="hi", tld="co.in").save(part_mp3)

        cmd = [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", part_mp3
        ]
        dur = float(subprocess.check_output(cmd).decode().strip()) + 0.30
        timings.append({"start": current_time, "end": current_time + dur, "duration": dur})
        current_time += dur
        audio_parts.append(part_mp3)

    with open("temp/concat.txt", "w") as f:
        for p in audio_parts:
            f.write(f"file '{os.path.abspath(p)}'\n")

    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", "temp/concat.txt", "-c", "copy", "temp/voice_raw.mp3"
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    return timings, current_time

def draw_rounded_card(draw, box, fill="#16161B", outline="#2E2E3A", width=3, radius=28):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)

def render_frame(scene, progress):
    img = BASE_BG.copy()
    draw = ImageDraw.Draw(img)
    eased = ease_out_cubic(min(1.0, progress * 2.2))
    slide_offset = int((1.0 - eased) * 45)

    # Top Header Pills
    draw_rounded_card(draw, [60, 90, 470, 165], fill="#16161B", outline="#2C2C38", radius=38)
    draw.text((95, 113), str(scene.get("tag", "SYSTEM.EXE"))[:20], fill="#A1A1AA", font=FONT_MONO_SM)

    draw_rounded_card(draw, [610, 90, 1020, 165], fill="#241D11", outline="#F5B041", radius=38)
    draw.text((650, 113), str(scene.get("pill", "EXPLAINER"))[:16], fill="#F5B041", font=FONT_MONO_SM)

    # Top-Right Telemetry Box
    draw_rounded_card(draw, [550, 210, 1020, 355], fill="#141419", outline="#2A2A35", radius=24)
    draw.text((585, 232), str(scene.get("metric_label", "STATUS"))[:18], fill="#71717A", font=FONT_MONO_SM)
    draw.text((585, 280), str(scene.get("metric_val", "ACTIVE"))[:16], fill=scene.get("metric_color", "#F5B041"), font=FONT_MONO_LG)

    mode = scene.get("mode", "p2p_direct")
    node_a = str(scene.get("node_a", "NODE A"))[:22]
    node_mid = str(scene.get("node_mid", "CENTRAL SERVER"))[:22]
    node_b = str(scene.get("node_b", "NODE B"))[:22]

    if mode in ("central", "p2p_direct"):
        draw_rounded_card(draw, [220, 520 + slide_offset, 860, 680 + slide_offset])
        draw.text((265, 555 + slide_offset), node_a, fill="#FFFFFF", font=FONT_CARD_TITLE)
        draw.text((265, 610 + slide_offset), "ACTIVE ENDPOINT • 01", fill="#8E8E98", font=FONT_CARD_SUB)

        b_outline = "#2ECC71" if mode == "p2p_direct" else "#2E2E3A"
        draw_rounded_card(draw, [220, 1160 - slide_offset, 860, 1320 - slide_offset], outline=b_outline)
        draw.text((265, 1195 - slide_offset), node_b, fill="#FFFFFF", font=FONT_CARD_TITLE)
        draw.text((265, 1250 - slide_offset), "ACTIVE ENDPOINT • 02", fill="#8E8E98", font=FONT_CARD_SUB)

        if mode == "central":
            draw.line([(540, 680 + slide_offset), (540, 840)], fill="#E74C3C", width=6)
            draw.line([(540, 1000), (540, 1160 - slide_offset)], fill="#E74C3C", width=6)
            draw_rounded_card(draw, [220, 840, 860, 1000], fill="#211417", outline="#E74C3C")
            draw.text((265, 875), node_mid, fill="#FF6B6B", font=FONT_CARD_TITLE)
            draw.text((265, 930), "BOTTLENECK • MIDDLEMAN", fill="#A1A1AA", font=FONT_CARD_SUB)
        else:
            draw.line([(540, 680 + slide_offset), (540, 1160 - slide_offset)], fill="#F5B041", width=8)
            py = int(680 + (1160 - 680) * ease_out_cubic(min(1.0, progress * 1.3)))
            draw.ellipse([516, py - 24, 564, py + 24], fill="#F5B041", outline="#FFFFFF", width=5)

    elif mode == "mesh":
        nodes = [(540, 610), (250, 870), (830, 870), (330, 1210), (750, 1210)]
        for i in range(len(nodes)):
            for j in range(i + 1, len(nodes)):
                draw.line([nodes[i], nodes[j]], fill="#2A2A38", width=4)
        active_idx = min(len(nodes) - 2, int(progress * (len(nodes) - 1)))
        draw.line([nodes[0], nodes[active_idx + 1]], fill="#F5B041", width=8)
        for idx, (nx, ny) in enumerate(nodes):
            r = 52 if idx == 0 or idx == active_idx + 1 else 44
            col = "#2ECC71" if idx == active_idx + 1 else "#F5B041"
            draw.ellipse([nx - r, ny - r, nx + r, ny + r], fill="#16161B", outline=col, width=5)
            draw.text((nx - 22, ny - 15), f"N{idx+1}", fill="#FFFFFF", font=FONT_MONO_SM)

    elif mode == "escrow":
        unlocked = progress > 0.60
        box_color = "#2ECC71" if unlocked else "#F5B041"
        draw_rounded_card(draw, [190, 730, 890, 1090], fill="#16161B", outline=box_color, width=5)
        status_txt = "VERIFIED & UNLOCKED ✓" if unlocked else "SECURE ESCROW VAULT"
        sub_txt = f"RELEASED TO {node_b}" if unlocked else "VERIFYING TRANSACTION..."
        draw.text((250, 810), status_txt, fill=box_color, font=FONT_CARD_TITLE)
        draw.text((250, 880), sub_txt, fill="#A1A1AA", font=FONT_CARD_SUB)
        bar_w = int(580 * min(1.0, progress * 1.4))
        draw.rounded_rectangle([250, 965, 830, 1005], radius=18, fill="#22222C")
        if bar_w > 20:
            draw.rounded_rectangle([250, 965, 250 + bar_w, 1005], radius=18, fill=box_color)

    elif mode == "counter":
        target = int(scene.get("counter_target", 10000))
        curr_val = int(target * ease_out_cubic(min(1.0, progress * 1.4)))
        prefix = str(scene.get("counter_prefix", ""))
        suffix = str(scene.get("counter_suffix", ""))
        display_num = f"{prefix}{curr_val:,}{suffix}"
        draw_rounded_card(draw, [160, 720, 920, 1080], fill="#16161B", outline="#F5B041", width=4)
        draw.text((220, 770), str(scene.get("metric_label", "LIVE METRIC")), fill="#A1A1AA", font=FONT_MONO_SM)
        draw.text((220, 855), display_num, fill="#F5B041", font=FONT_COUNTER)

    # Bottom Kinetic Subtitles (Safe for string or list highlights)
    hl_raw = scene.get("highlight", "")
    hl_str = " ".join(hl_raw).lower() if isinstance(hl_raw, list) else str(hl_raw).lower()

    words = scene["text"].split()
    lines, curr = [], []
    for w in words:
        curr.append(w)
        if len(" ".join(curr)) > 24:
            lines.append(" ".join(curr))
            curr = []
    if curr:
        lines.append(" ".join(curr))

    y_text = 1510
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=FONT_CAPTION)
        line_w = bbox[2] - bbox[0]
        x_cursor = (W - line_w) // 2
        for word in line.split():
            clean_w = word.strip(".,!?").lower()
            is_hl = len(clean_w) > 1 and clean_w in hl_str
            color = "#F5B041" if is_hl else "#FFFFFF"
            draw.text((x_cursor, y_text), word + " ", fill=color, font=FONT_CAPTION)
            wb = draw.textbbox((0, 0), word + " ", font=FONT_CAPTION)
            x_cursor += (wb[2] - wb[0])
        y_text += 72

    return img

async def generate_video(topic: str) -> str:
    safe_name = re.sub(r"[^a-zA-Z0-9]+", "_", topic.lower()).strip("_")[:30] or "explainer"
    out_mp4 = f"out/{safe_name}.mp4"

    print(f"1/4 Generating Hinglish Script for: {topic}...")
    scenes = generate_scenes_from_topic(topic)

    print("2/4 Generating Voiceover & Ambient Audio...")
    timings, total_dur = await generate_audio_and_timings(scenes)

    print("3/4 Rendering Motion Graphics...")
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
    proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)

    total_frames = int(total_dur * FPS)
    for f_idx in range(total_frames):
        t = f_idx / FPS
        active_scene = scenes[-1]
        prog = 1.0
        for s_idx, tm in enumerate(timings):
            if tm["start"] <= t <= tm["end"]:
                active_scene = scenes[s_idx]
                prog = (t - tm["start"]) / tm["duration"]
                break
        frame = render_frame(active_scene, prog)
        proc.stdin.write(frame.tobytes())

    proc.stdin.close()
    proc.wait()
    print(f"4/4 Done! Saved to: {out_mp4}")
    return out_mp4

if __name__ == "__main__":
    topic_arg = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "How P2P works"
    asyncio.run(generate_video(topic_arg))
