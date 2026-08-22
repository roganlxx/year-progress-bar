#!/usr/bin/env python3
"""year progress bar 시안 5종 정지컷 생성기 (1080x1920)."""

import datetime as dt
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).parent
OUT = ROOT / "out" / "concepts"
OUT.mkdir(parents=True, exist_ok=True)

W, H = 1080, 1920
HELV = "/System/Library/Fonts/HelveticaNeue.ttc"
MENLO = "/System/Library/Fonts/Menlo.ttc"

YELLOW = (255, 214, 0)
BLACK = (10, 10, 10)
TRACK = (38, 38, 38)
DIM = (122, 122, 122)

DAY = dt.date(2026, 8, 22)
START = dt.date(2026, 1, 1)
TOTAL = (dt.date(2027, 1, 1) - START).days
ELAPSED = (DAY - START).days          # 233
P = ELAPSED / TOTAL                   # 0.6384
LABEL = DAY.strftime("%b %d, %Y").upper()


def helv(size, idx=1):
    return ImageFont.truetype(HELV, size, index=idx)


def menlo(size, idx=0):
    return ImageFont.truetype(MENLO, size, index=idx)


# ---------- 1. 원형 게이지 ----------
def concept_ring():
    img = Image.new("RGB", (W, H), BLACK)
    d = ImageDraw.Draw(img)

    d.text((W / 2, 460), "2026", font=helv(88, 12), fill=DIM, anchor="mm")

    cx, cy, r, width = W / 2, 940, 330, 56
    box = [cx - r, cy - r, cx + r, cy + r]
    d.arc(box, 0, 360, fill=TRACK, width=width)

    a0, a1 = -90, -90 + 360 * P
    d.arc(box, a0, a1, fill=YELLOW, width=width)
    # 양 끝 라운드 캡
    for ang in (a0, a1):
        x = cx + (r - width / 2) * math.cos(math.radians(ang))
        y = cy + (r - width / 2) * math.sin(math.radians(ang))
        d.ellipse([x - width / 2, y - width / 2, x + width / 2, y + width / 2],
                  fill=YELLOW)

    d.text((cx, cy - 30), f"{P * 100:.1f}%", font=helv(150), fill=YELLOW,
           anchor="mm")
    d.text((cx, cy + 110), f"{ELAPSED} / {TOTAL} DAYS", font=helv(40, 10),
           fill=DIM, anchor="mm")

    d.text((W / 2, 1440), LABEL, font=helv(44, 10), fill=DIM, anchor="mm")
    img.save(OUT / "concept-1-ring.png")


# ---------- 2. 옐로 포스터 (반전) ----------
def concept_poster():
    img = Image.new("RGB", (W, H), YELLOW)
    d = ImageDraw.Draw(img)

    d.text((W / 2, 560), "2026", font=helv(110), fill=BLACK, anchor="mm")

    d.text((W / 2, 880), f"{P * 100:.0f}%", font=helv(400, 9), fill=BLACK,
           anchor="mm")

    bar_w, bar_h = 840, 64
    x0, y0 = (W - bar_w) / 2, 1180
    rr = bar_h / 2
    d.rounded_rectangle([x0, y0, x0 + bar_w, y0 + bar_h], radius=rr,
                        outline=BLACK, width=6)
    pad = 14
    fill_w = (bar_w - pad * 2) * P
    d.rounded_rectangle([x0 + pad, y0 + pad, x0 + pad + fill_w,
                         y0 + bar_h - pad], radius=(bar_h - pad * 2) / 2,
                        fill=BLACK)

    d.text((W / 2, 1360), LABEL, font=helv(46, 10), fill=BLACK, anchor="mm")
    img.save(OUT / "concept-2-poster.png")


# ---------- 3. 도트 그리드 (365일) ----------
def concept_dots():
    img = Image.new("RGB", (W, H), BLACK)
    d = ImageDraw.Draw(img)

    d.text((W / 2, 230), "2026", font=helv(80, 12), fill=DIM, anchor="mm")

    cols, rows = 15, 25
    gap = 52
    dot_r = 15
    gx = (W - (cols - 1) * gap) / 2
    gy = 340
    for i in range(TOTAL):
        c, rw = i % cols, i // cols
        x, y = gx + c * gap, gy + rw * gap
        if i < ELAPSED:
            d.ellipse([x - dot_r, y - dot_r, x + dot_r, y + dot_r],
                      fill=YELLOW)
        elif i == ELAPSED:
            # 오늘: 링으로 강조
            d.ellipse([x - dot_r - 8, y - dot_r - 8, x + dot_r + 8,
                       y + dot_r + 8], outline=YELLOW, width=4)
            d.ellipse([x - dot_r + 6, y - dot_r + 6, x + dot_r - 6,
                       y + dot_r - 6], fill=YELLOW)
        else:
            d.ellipse([x - dot_r, y - dot_r, x + dot_r, y + dot_r],
                      fill=TRACK)

    y_txt = gy + (rows - 1) * gap + 130
    d.text((W / 2, y_txt), f"{P * 100:.1f}%", font=helv(120), fill=YELLOW,
           anchor="mm")
    d.text((W / 2, y_txt + 120), LABEL, font=helv(42, 10), fill=DIM,
           anchor="mm")
    img.save(OUT / "concept-3-dots.png")


# ---------- 4. 스위스 에디토리얼 (라이트) ----------
def concept_swiss():
    paper = (246, 245, 240)
    ink = (16, 16, 16)
    img = Image.new("RGB", (W, H), paper)
    d = ImageDraw.Draw(img)

    m = 110  # 왼쪽 여백

    d.rectangle([m, 420, m + 44, 464], fill=YELLOW)
    d.text((m + 70, 442), "YEAR PROGRESS — 2026", font=helv(40, 10),
           fill=ink, anchor="lm")

    d.text((m - 14, 860), f"{P * 100:.1f}", font=helv(430, 9), fill=ink,
           anchor="lm")
    d.text((m + 6, 1140), "PERCENT COMPLETE", font=helv(40, 10), fill=ink,
           anchor="lm")

    bar_y = 1290
    d.rectangle([m, bar_y, W - m, bar_y + 4], fill=ink)
    d.rectangle([m, bar_y - 14, m + (W - 2 * m) * P, bar_y + 18],
                fill=YELLOW)

    d.text((m, 1430), f"{LABEL}  —  DAY {ELAPSED} OF {TOTAL}",
           font=helv(36, 10), fill=(110, 108, 100), anchor="lm")
    img.save(OUT / "concept-4-swiss.png")


# ---------- 5. 터미널 ----------
def concept_terminal():
    img = Image.new("RGB", (W, H), (12, 12, 10))
    d = ImageDraw.Draw(img)

    m = 100
    y = 700
    lh = 92

    d.text((m, y), "$ year --progress", font=menlo(44), fill=DIM,
           anchor="lm")
    y += lh
    d.text((m, y), "YEAR 2026 LOADING...", font=menlo(44), fill=YELLOW,
           anchor="lm")
    y += lh + 20

    # 블록 바 (25칸)
    cells = 25
    filled = round(cells * P)
    cw, ch, gap = 28, 62, 7
    bx = m
    d.text((bx - 6, y + ch / 2), "[", font=menlo(60), fill=DIM, anchor="rm")
    for i in range(cells):
        x = bx + i * (cw + gap)
        if i < filled:
            d.rectangle([x, y, x + cw, y + ch], fill=YELLOW)
        else:
            d.rectangle([x, y, x + cw, y + ch], outline=TRACK, width=3)
    d.text((bx + cells * (cw + gap) + 2, y + ch / 2), "]", font=menlo(60),
           fill=DIM, anchor="lm")

    y += ch + lh
    d.text((m, y), f"{P * 100:.2f}% COMPLETE", font=menlo(66, 1),
           fill=YELLOW, anchor="lm")
    y += lh
    d.text((m, y), f"{ELAPSED}/{TOTAL} DAYS · {LABEL}", font=menlo(40),
           fill=DIM, anchor="lm")
    y += lh
    # 커서
    d.text((m, y), "$", font=menlo(44), fill=DIM, anchor="lm")
    d.rectangle([m + 40, y - 26, m + 68, y + 26], fill=YELLOW)

    img.save(OUT / "concept-5-terminal.png")


if __name__ == "__main__":
    concept_ring()
    concept_poster()
    concept_dots()
    concept_swiss()
    concept_terminal()
    for f in sorted(OUT.glob("concept-*.png")):
        print(f)
