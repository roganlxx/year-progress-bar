#!/usr/bin/env python3
"""year progress bar 릴스 생성기 — 도트 그리드 버전.

365개 도트가 전부 켜진 상태에서 시작해, 지나간 날들의 불이
차례로 꺼진다. 남은 날들은 계속 켜져 있고 오늘은 링으로 강조.
사용법: python3 make_reel.py [YYYY-MM-DD]
"""

import datetime as dt
import math
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).parent
OUT = ROOT / "out"
FRAMES = OUT / "frames"

W, H = 1080, 1920
FPS = 30
HOLD_IN_SEC = 0.6       # 전부 켜진 채 잠깐 멈춤
SWEEP_SEC = 5.0         # 불이 꺼져 나가는 시간
HOLD_OUT_SEC = 2.4      # 끝나고 멈춰 있는 시간
TOTAL_FRAMES = int((HOLD_IN_SEC + SWEEP_SEC + HOLD_OUT_SEC) * FPS)

DARK = "--dark" in sys.argv

# 기본: 노란 배경에 검은 도트
BG = (255, 214, 0)
YELLOW = (14, 14, 14)       # 켜진 도트, 퍼센트
TRACK = (214, 176, 10)      # 꺼진 도트
DIM = (96, 78, 0)           # 보조 텍스트
YEAR_COLOR = (14, 14, 14)
if DARK:
    BG = (10, 10, 10)
    YELLOW = (255, 214, 0)
    TRACK = (38, 38, 38)
    DIM = (122, 122, 122)
    YEAR_COLOR = (240, 240, 240)

COLS, ROWS = 15, 25
GAP = 40
DOT_R = 12
GY = 650

FONT_DIR = ROOT / "fonts"
FONT_BOLD = str(FONT_DIR / "Pretendard-Bold.otf")
FONT_MEDIUM = str(FONT_DIR / "Pretendard-Medium.otf")


def font(size, path=FONT_BOLD):
    return ImageFont.truetype(path, size)


def text_tracked(d, center_xy, text, fnt, fill, tracking_em=-0.05):
    """자간(em 비율)을 적용해 가운데 정렬로 그린다. Pillow엔 자간이 없어서 직접."""
    size = fnt.size
    tracking = tracking_em * size
    widths = [fnt.getlength(ch) for ch in text]
    total = sum(widths) + tracking * (len(text) - 1)
    x = center_xy[0] - total / 2
    for ch, w in zip(text, widths):
        d.text((x, center_xy[1]), ch, font=fnt, fill=fill, anchor="lm")
        x += w + tracking


def lerp(c1, c2, t):
    t = max(0.0, min(1.0, t))
    return tuple(round(a + (b - a) * t) for a, b in zip(c1, c2))


def ease_out_expo(t):
    if t >= 1:
        return 1.0
    # 같은 속도감을 유지하되 t=1에서 정확히 1이 되도록 정규화
    return (1 - 2 ** (-9 * t)) / (1 - 2 ** -9)


def year_info(day: dt.date):
    start = dt.date(day.year, 1, 1)
    total = (dt.date(day.year + 1, 1, 1) - start).days
    elapsed = (day - start).days
    return elapsed, total


def draw_frame(n_off: float, elapsed: int, total: int, year: int,
               label: str, blink_on: bool) -> Image.Image:
    """n_off: 지금까지 꺼진 도트 수(소수부는 페이드 진행분).
    blink_on: 오늘 도트 점등 상태 (홀드 구간에서 깜빡임)."""
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # 상단(릴스 UI가 안 가리는 구간): 연도가 히어로, 그 아래 퍼센트와 날짜
    blink_idx = max(elapsed - 1, 0)          # 스윕 종결점 = 깜빡이는 점
    final_pct = elapsed / total * 100
    pct = final_pct if blink_idx == 0 else final_pct * min(1.0, n_off / blink_idx)
    # 숫자 자간 -4%: 첫 게시물(Helvetica Neue Bold)의 인상에 맞춤
    text_tracked(d, (W / 2, 335), str(year), font(150), YEAR_COLOR,
                 tracking_em=-0.04)
    text_tracked(d, (W / 2, 490), f"{pct:.1f}%", font(115), YELLOW,
                 tracking_em=-0.04)
    text_tracked(d, (W / 2, 585), label, font(44, FONT_MEDIUM), DIM,
                 tracking_em=-0.05)

    gx = (W - (COLS - 1) * GAP) / 2
    for i in range(total):
        c, rw = i % COLS, i // COLS
        x, y = gx + c * GAP, GY + rw * GAP

        if i < blink_idx:
            # 지나간 날: n_off를 지나면 꺼진다 (1도트 폭으로 페이드)
            u = n_off - i
            color = lerp(YELLOW, TRACK, u)
        elif i == blink_idx:
            # 스윕이 멈춘 자리: 커서처럼 깜빡인다
            color = YELLOW if blink_on else TRACK
        else:
            color = YELLOW

        d.ellipse([x - DOT_R, y - DOT_R, x + DOT_R, y + DOT_R], fill=color)

    return img


def build_audio(elapsed: int, path: Path):
    """가이거 카운터→시계 초침 컨셉의 사운드를 합성한다.
    도트가 꺼지는 순간마다 틱, 마지막 도트는 묵직한 톡,
    홀드 구간 깜빡임엔 초침 소리."""
    import random
    import struct
    import wave

    sr = 44100
    total_sec = HOLD_IN_SEC + SWEEP_SEC + HOLD_OUT_SEC
    n = int(total_sec * sr)
    buf = [0.0] * n
    rnd = random.Random(42)

    def add_tone(t0, freq, dur, amp, noise=0.0):
        start = int(t0 * sr)
        length = max(1, int(dur * sr))
        for k in range(length):
            idx = start + k
            if idx >= n:
                break
            env = math.exp(-5.0 * k / length)
            s = math.sin(2 * math.pi * freq * k / sr)
            if noise:
                s = (1 - noise) * s + noise * (rnd.random() * 2 - 1)
            buf[idx] += amp * env * s

    # 정규화된 expo 이징의 역함수: 도트 i가 완전히 꺼지는 시각
    denom = 1 - 2 ** -9

    def t_off(i):
        y = (i + 1) / elapsed
        inner = max(2 ** -9, 1 - y * denom)
        return HOLD_IN_SEC + SWEEP_SEC * (-math.log2(inner) / 9)

    if elapsed <= 0:
        # 꺼질 도트가 없으면 초침만
        pass
    last_t = -1.0
    for i in range(max(elapsed - 1, 0)):
        t0 = t_off(i)
        if t0 - last_t < 0.025:   # 틱 최소 간격 (촘촘함 절반으로)
            continue
        last_t = t0
        prog = i / elapsed
        freq = 240 - 120 * prog + rnd.uniform(-10, 10)
        amp = 0.11 + 0.11 * prog
        add_tone(t0, freq, 0.014 + 0.012 * prog, amp, noise=0.35)

    # 마지막 도트: 낮고 묵직하게
    add_tone(t_off(elapsed - 1), 45, 0.22, 0.6)

    # 홀드 구간: 깜빡임과 동기화된 초침 (켜질 때 똑, 꺼질 때 여린 딱)
    t_hold0 = HOLD_IN_SEC + SWEEP_SEC
    k = 0
    while t_hold0 + k < total_sec:
        add_tone(t_hold0 + k, 120, 0.034, 0.2)
        if t_hold0 + k + 0.55 < total_sec:
            add_tone(t_hold0 + k + 0.55, 90, 0.024, 0.1)
        k += 1

    peak = max(max(buf), -min(buf), 1e-9)
    scale = min(1.0, 0.075 / peak)  # 전체 음량 (0.25의 30%)
    with wave.open(str(path), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        frames = bytearray()
        for s in buf:
            frames += struct.pack("<h", int(max(-1.0, min(1.0, s * scale)) * 32767))
        w.writeframes(bytes(frames))


def ffmpeg_bin() -> str:
    local = ROOT / "node_modules" / "ffmpeg-static" / "ffmpeg"
    if local.exists():
        return str(local)
    found = shutil.which("ffmpeg")
    if not found:
        sys.exit("ffmpeg를 찾을 수 없습니다.")
    return found


def main():
    args = [a for a in sys.argv[1:] if a != "--dark"]
    day = dt.date.fromisoformat(args[0]) if args else dt.date.today()
    elapsed, total = year_info(day)
    label = day.strftime("%a, %b %d").upper()

    if FRAMES.exists():
        shutil.rmtree(FRAMES)
    FRAMES.mkdir(parents=True)

    off_total = max(elapsed - 1, 0)   # 깜빡이는 점 직전까지만 끈다

    f_in = int(HOLD_IN_SEC * FPS)
    f_sweep = int(SWEEP_SEC * FPS)

    for f in range(TOTAL_FRAMES):
        if f < f_in:
            n_off, blink_on = 0.0, True
        elif f < f_in + f_sweep:
            t = (f - f_in) / f_sweep
            n_off = off_total * ease_out_expo(t)
            blink_on = True
        else:
            n_off = float(off_total)
            t_hold = (f - f_in - f_sweep) / FPS
            blink_on = (t_hold % 1.0) < 0.55  # 1초 주기 커서 깜빡임

        draw_frame(n_off, elapsed, total, day.year, label, blink_on).save(
            FRAMES / f"{f:04d}.png")

    suffix = "-dark" if DARK else ""
    audio_wav = FRAMES / "audio.wav"
    build_audio(off_total, audio_wav)

    out_mp4 = OUT / f"year-progress-{day.isoformat()}{suffix}.mp4"
    subprocess.run(
        [
            ffmpeg_bin(), "-y",
            "-framerate", str(FPS),
            "-i", str(FRAMES / "%04d.png"),
            "-i", str(audio_wav),
            "-c:v", "libx264", "-preset", "slow", "-crf", "18",
            "-pix_fmt", "yuv420p", "-r", str(FPS),
            "-c:a", "aac", "-b:a", "128k", "-shortest",
            "-movflags", "+faststart",
            str(out_mp4),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    still = OUT / f"year-progress-{day.isoformat()}{suffix}.png"
    draw_frame(float(off_total), elapsed, total, day.year, label, True).save(
        still)

    shutil.rmtree(FRAMES)
    print(f"{day.isoformat()}  {elapsed}/{total}  {elapsed / total * 100:.2f}%")
    print(out_mp4)
    print(still)


if __name__ == "__main__":
    main()
