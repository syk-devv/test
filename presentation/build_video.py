"""대본(script_data.py)과 슬라이드 PNG로 자막+음성이 들어간 유튜브식 영상을 만든다.

사용법:
  pdftoppm -png -scale-to-x 1920 -scale-to-y 1080 deck.pdf SLIDES_DIR/s
  python3 build_video.py SLIDES_DIR WORK_DIR OUT_DIR
필요: ffmpeg, Pillow, gTTS
"""
import os
import subprocess
import sys
import textwrap

from gtts import gTTS
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from script_data import SCENES, SPEECH_REPLACE  # noqa: E402

W, H = 1920, 1080
SW, SH = 1632, 918  # 슬라이드 영역 (아래 162px은 자막 띠)
FONT = "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"
BG = (20, 20, 22)
BLUE = (47, 140, 255)
SPEED = 1.2  # gTTS 기본 속도가 느려서 살짝 올림


def font(size):
    return ImageFont.truetype(FONT, size)


def make_card(card):
    img = Image.new("RGB", (SW, SH), (31, 31, 33))
    d = ImageDraw.Draw(img)
    x, y = 110, 110
    d.text((x, y), card["kicker"], font=font(36), fill=BLUE)
    y += 80
    for line in card["title"].split("\n"):
        d.text((x, y), line, font=font(76), fill="white")
        y += 100
    y += 30
    for b in card.get("bullets", []):
        head, _, rest = b.partition("  ")
        d.text((x, y), head, font=font(42), fill=BLUE)
        hw = d.textlength(head, font=font(42))
        d.text((x + max(hw + 30, 230), y), rest, font=font(42), fill=(225, 225, 230))
        y += 72
    if card.get("sub"):
        d.text((x, SH - 150), card["sub"], font=font(40), fill=(170, 170, 178))
    return img


def frame(base, chapter, subtitle, progress):
    img = Image.new("RGB", (W, H), BG)
    img.paste(base.resize((SW, SH), Image.LANCZOS), ((W - SW) // 2, 0))
    d = ImageDraw.Draw(img)
    # 챕터 라벨 (왼쪽 아래)
    d.text((30, SH + 14), chapter, font=font(24), fill=BLUE)
    # 자막
    lines = textwrap.wrap(subtitle, 40)
    f = font(42)
    total = len(lines) * 54
    ty = SH + (H - SH - total) // 2 + 6
    for ln in lines:
        lw = d.textlength(ln, font=f)
        d.text(((W - lw) / 2, ty), ln, font=f, fill="white", stroke_width=2, stroke_fill="black")
        ty += 54
    # 진행 막대
    d.rectangle([0, H - 6, int(W * progress), H], fill=BLUE)
    return img


def speech_text(s):
    for k, v in SPEECH_REPLACE.items():
        s = s.replace(k, v)
    return s


def run(cmd):
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
        check=True, capture_output=True, text=True,
    ).stdout
    return float(out.strip())


def srt_time(t):
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def main(slides_dir, work, out_dir):
    os.makedirs(work, exist_ok=True)
    os.makedirs(out_dir, exist_ok=True)
    items = [(si, li, sc, ln) for si, sc in enumerate(SCENES) for li, ln in enumerate(sc["lines"])]

    # 1) 문장별 음성
    clips = []
    for si, li, sc, ln in items:
        raw = f"{work}/a_{si:02}_{li:02}.mp3"
        wav = f"{work}/a_{si:02}_{li:02}.wav"
        if not os.path.exists(wav):
            gTTS(speech_text(ln), lang="ko").save(raw)
            pad = 0.9 if li == len(sc["lines"]) - 1 else 0.35
            run(["ffmpeg", "-y", "-i", raw, "-af", f"atempo={SPEED},apad=pad_dur={pad}",
                 "-ar", "44100", "-ac", "1", wav])
        clips.append(wav)
    durs = [duration(c) for c in clips]
    total = sum(durs)

    # 2) 문장별 화면 + 구간 영상
    bases = {}
    segs, srt, t = [], [], 0.0
    for n, ((si, li, sc, ln), wav, dur) in enumerate(zip(items, clips, durs)):
        if si not in bases:
            bases[si] = make_card(sc["card"]) if "card" in sc else Image.open(f"{slides_dir}/{sc['image']}").convert("RGB")
        png = f"{work}/f_{n:03}.png"
        frame(bases[si], sc["chapter"], ln, (t + dur) / total).save(png)
        seg = f"{work}/seg_{n:03}.mp4"
        run(["ffmpeg", "-y", "-loop", "1", "-framerate", "30", "-i", png, "-i", wav,
             "-c:v", "libx264", "-tune", "stillimage", "-pix_fmt", "yuv420p", "-r", "30",
             "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-shortest", "-t", f"{dur:.3f}", seg])
        segs.append(seg)
        srt.append(f"{n + 1}\n{srt_time(t)} --> {srt_time(t + dur)}\n{ln}\n")
        t += dur

    # 3) 이어붙이기
    lst = f"{work}/list.txt"
    with open(lst, "w") as fh:
        fh.writelines(f"file '{s}'\n" for s in segs)
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy",
         "-movflags", "+faststart", f"{out_dir}/rag_chunking_video.mp4"])
    with open(f"{out_dir}/rag_chunking_video.srt", "w") as fh:
        fh.write("\n".join(srt))

    # 4) 챕터(유튜브 설명란에 붙여넣기용)
    chapters, t = [], 0.0
    for si, sc in enumerate(SCENES):
        chapters.append(f"{int(t // 60)}:{int(t % 60):02} {sc['chapter']}")
        t += sum(d for (s, *_), d in zip(items, durs) if s == si)
    with open(f"{out_dir}/chapters.txt", "w") as fh:
        fh.write("\n".join(chapters) + "\n")
    print(f"done: {total:.1f}s")
    print("\n".join(chapters))


if __name__ == "__main__":
    main(*sys.argv[1:4])
