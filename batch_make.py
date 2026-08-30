#!/usr/bin/env python3
"""예정된 게시 날짜들의 영상을 미리 일괄 생성한다.

make_reel의 렌더링 로직을 그대로 쓰되, 워커마다 별도 임시 폴더를 써서
병렬로 돌린다. 결과는 docs/media/<날짜>.mp4 (CI가 그대로 발행하는 경로).

사용법: python3 batch_make.py [--force]
"""

import datetime as dt
import multiprocessing as mp
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import make_reel as M

ROOT = Path(__file__).parent
MEDIA = ROOT / "docs" / "media"
MEDIA.mkdir(parents=True, exist_ok=True)


def schedule() -> list:
    """매일 40일 + 10월 1일부터 4일 간격 100회."""
    daily = [dt.date(2026, 8, 31) + dt.timedelta(days=i) for i in range(40)]
    every4 = [dt.date(2026, 10, 1) + dt.timedelta(days=4 * i)
              for i in range(100)]
    return sorted(set(daily) | set(every4))


def render_one(day: dt.date) -> tuple:
    out_mp4 = MEDIA / f"{day.isoformat()}.mp4"
    if out_mp4.exists() and "--force" not in sys.argv:
        return (day, "skip", out_mp4.stat().st_size)

    elapsed, total = M.year_info(day)
    label = day.strftime("%a, %b %d").upper()
    off_total = max(elapsed - 1, 0)

    f_in = int(M.HOLD_IN_SEC * M.FPS)
    f_sweep = int(M.SWEEP_SEC * M.FPS)

    tmp = Path(tempfile.mkdtemp(prefix=f"yp-{day.isoformat()}-"))
    try:
        for f in range(M.TOTAL_FRAMES):
            if f < f_in:
                n_off, blink_on = 0.0, True
            elif f < f_in + f_sweep:
                t = (f - f_in) / f_sweep
                n_off = off_total * M.ease_out_expo(t)
                blink_on = True
            else:
                n_off = float(off_total)
                t_hold = (f - f_in - f_sweep) / M.FPS
                blink_on = (t_hold % 1.0) < 0.55

            M.draw_frame(n_off, elapsed, total, day.year, label,
                         blink_on).save(tmp / f"{f:04d}.png")

        audio = tmp / "audio.wav"
        M.build_audio(off_total, audio)

        subprocess.run(
            [
                M.ffmpeg_bin(), "-y",
                "-framerate", str(M.FPS),
                "-i", str(tmp / "%04d.png"),
                "-i", str(audio),
                "-c:v", "libx264", "-preset", "slow", "-crf", "18",
                "-pix_fmt", "yuv420p", "-r", str(M.FPS),
                "-c:a", "aac", "-b:a", "128k", "-shortest",
                "-movflags", "+faststart",
                str(out_mp4),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    return (day, "made", out_mp4.stat().st_size)


def main():
    days = schedule()
    workers = max(1, min(os.cpu_count() or 4, 8))
    print(f"{len(days)}개 생성 시작 (워커 {workers}개)", flush=True)

    done = 0
    with mp.Pool(workers) as pool:
        for day, status, size in pool.imap_unordered(render_one, days):
            done += 1
            if done % 10 == 0 or status == "skip":
                print(f"[{done}/{len(days)}] {day} {status} "
                      f"{size // 1024}KB", flush=True)
    print("완료", flush=True)


if __name__ == "__main__":
    main()
