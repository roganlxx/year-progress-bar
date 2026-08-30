#!/usr/bin/env python3
"""발행 + 토큰 갱신 + 다음 실행 시각 추첨.

1. state/token.enc를 TOKEN_KEY로 복호화
2. 릴스 발행 (publish.py의 로직 재사용)
3. 토큰 refresh 후 재암호화 저장
4. 다음 실행 시각 = 지금 + uniform(85h, 131h)
"""

import datetime as dt
import json
import os
import random
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
from publish import make_caption  # noqa: E402

GRAPH = "https://graph.instagram.com/v23.0"
STATE = ROOT / "state"
TOKEN_ENC = STATE / "token.enc"
NEXT_RUN = STATE / "next_run.txt"
LOG = STATE / "log.csv"
IG_USER_ID = (STATE / "ig_user_id.txt").read_text().strip()

# 4일 간격으로 넘어가는 조건: 10월 1일 이후 + 팔로워 100명 이상.
# 둘 중 하나라도 미달이면 매일 1회.
EVERY4_FROM = dt.date(2026, 10, 1)
EVERY4_MIN_FOLLOWERS = 100


def openssl(args, input_bytes):
    return subprocess.run(
        ["openssl"] + args, input=input_bytes, capture_output=True, check=True
    ).stdout


def decrypt_token() -> str:
    out = openssl(
        ["enc", "-d", "-a", "-aes-256-cbc", "-pbkdf2", "-pass",
         "env:TOKEN_KEY", "-in", str(TOKEN_ENC)],
        None,
    )
    return out.decode().strip()


def encrypt_token(token: str):
    out = openssl(
        ["enc", "-a", "-aes-256-cbc", "-pbkdf2", "-salt", "-pass",
         "env:TOKEN_KEY"],
        token.encode(),
    )
    TOKEN_ENC.write_bytes(out)


def call(method, path, params):
    data = urllib.parse.urlencode(params).encode()
    if method == "GET":
        req = urllib.request.Request(f"{GRAPH}{path}?{data.decode()}")
    else:
        req = urllib.request.Request(f"{GRAPH}{path}", data=data)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        sys.exit(f"API 오류 {e.code}: {e.read().decode()}")


def main():
    if "TOKEN_KEY" not in os.environ:
        sys.exit("TOKEN_KEY 환경변수가 없습니다")
    video_url = sys.argv[1]
    token = decrypt_token()
    day = dt.date.today()  # 워크플로가 TZ=Asia/Seoul로 실행
    caption = make_caption(day)

    print("컨테이너 생성...")
    c = call("POST", f"/{IG_USER_ID}/media", {
        "media_type": "REELS",
        "video_url": video_url,
        "caption": caption,
        "access_token": token,
    })
    cid = c["id"]

    for i in range(60):
        st = call("GET", f"/{cid}", {
            "fields": "status_code", "access_token": token,
        })
        code = st.get("status_code")
        print(f"  [{i * 5}s] {code}")
        if code == "FINISHED":
            break
        if code == "ERROR":
            sys.exit(f"처리 실패: {st}")
        time.sleep(5)
    else:
        sys.exit("시간 초과")

    pub = call("POST", f"/{IG_USER_ID}/media_publish", {
        "creation_id": cid, "access_token": token,
    })
    media_id = pub["id"]
    info = call("GET", f"/{media_id}", {
        "fields": "permalink", "access_token": token,
    })
    permalink = info.get("permalink", "")
    print(f"게시 완료: {permalink}")

    print("토큰 갱신...")
    ref = call("GET", "/refresh_access_token", {
        "grant_type": "ig_refresh_token", "access_token": token,
    })
    encrypt_token(ref["access_token"])
    print(f"토큰 갱신 완료 (유효 {ref['expires_in'] // 86400}일)")

    # 10월 1일 이후이면서 팔로워 100명 이상일 때만 4일 간격, 아니면 매일
    followers = None
    try:
        req = urllib.request.Request(
            f"{GRAPH}/me?"
            + urllib.parse.urlencode(
                {"fields": "followers_count", "access_token": token}))
        with urllib.request.urlopen(req, timeout=30) as r:
            followers = json.loads(r.read()).get("followers_count")
    except Exception as e:
        print(f"팔로워 조회 실패({e}) → 매일 모드 유지")

    now = dt.datetime.now(dt.timezone.utc)
    date_ok = now.date() >= EVERY4_FROM
    follow_ok = followers is not None and followers >= EVERY4_MIN_FOLLOWERS
    if date_ok and follow_ok:
        hours = 96.0
        print(f"4일 간격 모드 (팔로워 {followers}명)")
    else:
        hours = 24.0
        print(f"매일 모드 (팔로워 {followers}명, "
              f"10월 이후={date_ok}, 100명 이상={follow_ok})")
    nxt = now + dt.timedelta(hours=hours)
    NEXT_RUN.write_text(nxt.isoformat())
    print(f"다음 게시: {nxt.isoformat()} ({hours:.1f}시간 후)")

    with LOG.open("a") as f:
        f.write(f"{day.isoformat()},{permalink},{nxt.isoformat()}\n")


if __name__ == "__main__":
    main()
