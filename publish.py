#!/usr/bin/env python3
"""릴스 발행: 컨테이너 생성 → 처리 대기 → media_publish.

사용법: python3 publish.py <video_url> [YYYY-MM-DD]
캡션은 날짜 기준으로 자동 생성.
"""

import datetime as dt
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

GRAPH = "https://graph.instagram.com/v23.0"


def load_env():
    env = {}
    for line in (Path(__file__).parent / ".env").read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


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
        body = e.read().decode()
        sys.exit(f"API 오류 {e.code}: {body}")


def make_caption(day: dt.date) -> str:
    start = dt.date(day.year, 1, 1)
    total = (dt.date(day.year + 1, 1, 1) - start).days
    elapsed = (day - start).days
    pct = elapsed / total * 100
    return f"{day.year}년의 {pct:.1f}%가 지나갔습니다."


def main():
    if len(sys.argv) < 2:
        sys.exit("사용법: python3 publish.py <video_url> [YYYY-MM-DD]")
    video_url = sys.argv[1]
    day = (
        dt.date.fromisoformat(sys.argv[2])
        if len(sys.argv) > 2
        else dt.date.today()
    )

    env = load_env()
    uid, token = env["IG_USER_ID"], env["IG_ACCESS_TOKEN"]
    caption = make_caption(day)

    print("컨테이너 생성 중...")
    c = call("POST", f"/{uid}/media", {
        "media_type": "REELS",
        "video_url": video_url,
        "caption": caption,
        "access_token": token,
    })
    cid = c["id"]
    print(f"컨테이너: {cid}")

    print("영상 처리 대기 중...")
    for i in range(60):  # 최대 5분
        st = call("GET", f"/{cid}", {
            "fields": "status_code",
            "access_token": token,
        })
        code = st.get("status_code")
        print(f"  [{i * 5}s] {code}")
        if code == "FINISHED":
            break
        if code == "ERROR":
            detail = call("GET", f"/{cid}", {
                "fields": "status",
                "access_token": token,
            })
            sys.exit(f"처리 실패: {detail}")
        time.sleep(5)
    else:
        sys.exit("시간 초과: 컨테이너가 FINISHED에 도달하지 못함")

    print("발행 중...")
    pub = call("POST", f"/{uid}/media_publish", {
        "creation_id": cid,
        "access_token": token,
    })
    media_id = pub["id"]
    print(f"미디어 ID: {media_id}")

    info = call("GET", f"/{media_id}", {
        "fields": "permalink",
        "access_token": token,
    })
    print(f"게시 완료: {info.get('permalink', '(permalink 조회 실패)')}")


if __name__ == "__main__":
    main()
