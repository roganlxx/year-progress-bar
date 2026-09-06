#!/usr/bin/env python3
"""스케줄 게이트: state/next_run.txt 시각이 지났으면 due=true를 출력한다.

state/next_run.txt는 UTC 오프셋이 붙은 ISO 8601이어야 한다.
(예: 2026-09-08T13:47:00+00:00). 손으로 고칠 때 오프셋을 빠뜨리면
UTC로 간주하되 경고를 남긴다.
"""

import datetime as dt
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
NEXT_RUN = ROOT / "state" / "next_run.txt"


def read_next_run(now):
    try:
        raw = NEXT_RUN.read_text().strip()
    except FileNotFoundError:
        return now  # 상태 파일이 없으면 즉시 실행
    if not raw:
        # 형식 오류를 now로 때우면 의도치 않은 즉시 게시가 된다 → 크게 실패시킨다.
        sys.exit("state/next_run.txt가 비어 있습니다")
    # '+0000'과 'Z'도 받아 준다(로컬 python 3.9 fromisoformat 호환).
    s = raw.replace("Z", "+00:00")
    m = re.search(r"([+-]\d{2})(\d{2})$", s)
    if m:
        s = s[:m.start()] + f"{m.group(1)}:{m.group(2)}"
    try:
        nxt = dt.datetime.fromisoformat(s)
    except ValueError:
        sys.exit(f"state/next_run.txt 형식 오류: {raw!r} (예: {now.isoformat()})")
    if nxt.tzinfo is None:
        # naive면 aware인 now와 비교할 때 TypeError로 죽는다. UTC로 간주한다.
        print(f"경고: next_run.txt에 UTC 오프셋이 없습니다({raw!r}). "
              "UTC로 간주합니다.", file=sys.stderr)
        nxt = nxt.replace(tzinfo=dt.timezone.utc)
    return nxt


def main():
    force = os.environ.get("FORCE", "").lower() == "true"
    now = dt.datetime.now(dt.timezone.utc)
    nxt = read_next_run(now)
    due = force or now >= nxt
    # stdout은 $GITHUB_OUTPUT으로 들어가므로 due= 한 줄만 내보낸다.
    print(f"due={'true' if due else 'false'}")
    print(f"# now={now.isoformat()} next={nxt.isoformat()} "
          f"force={force} due={due}", file=sys.stderr)


if __name__ == "__main__":
    main()
