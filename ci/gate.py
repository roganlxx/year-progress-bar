#!/usr/bin/env python3
"""스케줄 게이트: state/next_run.txt 시각이 지났으면 due=true를 출력한다."""

import datetime as dt
import os
from pathlib import Path

ROOT = Path(__file__).parent.parent
NEXT_RUN = ROOT / "state" / "next_run.txt"


def main():
    force = os.environ.get("FORCE", "").lower() == "true"
    now = dt.datetime.now(dt.timezone.utc)
    try:
        nxt = dt.datetime.fromisoformat(NEXT_RUN.read_text().strip())
    except FileNotFoundError:
        nxt = now  # 상태 파일이 없으면 즉시 실행
    due = force or now >= nxt
    print(f"due={'true' if due else 'false'}")
    print(f"# now={now.isoformat()} next={nxt.isoformat()} force={force}")


if __name__ == "__main__":
    main()
