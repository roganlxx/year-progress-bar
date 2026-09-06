#!/usr/bin/env python3
"""릴스 발행: 컨테이너 생성 → 처리 대기 → media_publish.

사용법: python3 publish.py <video_url> [YYYY-MM-DD]
캡션은 날짜 기준으로 자동 생성.
"""

import datetime as dt
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

GRAPH = "https://graph.instagram.com/v23.0"
TOKEN_ENC = Path(__file__).parent / "state" / "token.enc"

# 커버 썸네일 위치(ms). 지정하지 않으면 인스타가 0ms 프레임을 커버로 쓰는데
# 그 프레임은 퍼센트가 0.0%로 굳어 있다(HOLD_IN 구간). 5.6~8.0초 홀드 안으로 잡는다.
THUMB_OFFSET_MS = "7000"


SECRET_KEYS = ("IG_ACCESS_TOKEN", "TOKEN_KEY")
KEYCHAIN_SERVICE = "insta-auto"


def kc_get(key: str):
    """macOS 키체인에서 값을 읽는다. 없거나 실패하면 None."""
    try:
        r = subprocess.run(
            ["security", "find-generic-password", "-w",
             "-s", KEYCHAIN_SERVICE, "-a", key],
            capture_output=True, text=True, timeout=10)
    except Exception:
        return None
    v = r.stdout.strip()
    return v if r.returncode == 0 and v else None


def load_env():
    """비밀값은 키체인에서, 나머지는 .env 에서 읽는다.

    키체인에 없으면 .env 값을 그대로 쓴다(이전 전 상태와 호환).
    CI(깃허브 액션)에서는 os.environ 을 쓰므로 이 함수를 타지 않는다.
    """
    env = {}
    p = Path(__file__).parent / ".env"
    if p.exists():
        for line in p.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    for k in SECRET_KEYS:
        v = kc_get(k)
        if v:
            env[k] = v
    return env


def load_token(env) -> str:
    """토큰의 원본은 state/token.enc다.

    .env의 IG_ACCESS_TOKEN은 아무도 갱신해 주지 않는 두 번째 사본이라
    발급 60일 뒤 조용히 죽는다. CI가 매 실행마다 갱신하는 token.enc를
    먼저 쓰고, 그게 안 될 때만 .env 값으로 물러난다.
    """
    key = env.get("TOKEN_KEY")
    if key and TOKEN_ENC.exists():
        try:
            out = subprocess.run(
                ["openssl", "enc", "-d", "-a", "-aes-256-cbc", "-pbkdf2",
                 "-pass", "env:TOKEN_KEY", "-in", str(TOKEN_ENC)],
                capture_output=True, check=True,
                env={**os.environ, "TOKEN_KEY": key}).stdout.decode().strip()
            if out:
                age = (time.time() - TOKEN_ENC.stat().st_mtime) / 86400
                print(f"토큰: state/token.enc (파일 갱신 {age:.1f}일 전)")
                if age > 30:
                    print("경고: token.enc가 오래됐습니다. git pull 먼저 하세요.")
                return out
        except Exception as e:
            print(f"token.enc 복호화 실패({e}) → .env 토큰으로 대체")
    tok = env.get("IG_ACCESS_TOKEN")
    if not tok:
        sys.exit("토큰이 없습니다 "
                 "(TOKEN_KEY + state/token.enc 또는 IG_ACCESS_TOKEN 필요)")
    print("경고: .env의 IG_ACCESS_TOKEN 사용 "
          "— 갱신되지 않는 사본이라 이미 만료됐을 수 있습니다")
    return tok


def call(method, path, params, fatal=True):
    """fatal=False 면 죽지 않고 RuntimeError 를 올린다(호출한 쪽이 대안을 쓴다)."""
    data = urllib.parse.urlencode(params).encode()
    if method == "GET":
        req = urllib.request.Request(f"{GRAPH}{path}?{data.decode()}")
    else:
        req = urllib.request.Request(f"{GRAPH}{path}", data=data)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        msg = f"API 오류 {e.code}: {e.read().decode()}"
        if fatal:
            sys.exit(msg)
        raise RuntimeError(msg)


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
    uid, token = env["IG_USER_ID"], load_token(env)
    caption = make_caption(day)

    print("컨테이너 생성 중...")
    # 커버 프레임 지정이 거절되면 그것만 빼고 다시 시도한다. 부가 기능 하나로
    # 게시 자체가 막히면 안 된다.
    body = {
        "media_type": "REELS",
        "video_url": video_url,
        "caption": caption,
        "thumb_offset": THUMB_OFFSET_MS,
        "access_token": token,
    }
    try:
        c = call("POST", f"/{uid}/media", body, fatal=False)
    except RuntimeError as e:
        print(f"thumb_offset 포함 요청 실패({e}). 빼고 다시 시도한다")
        body.pop("thumb_offset")
        c = call("POST", f"/{uid}/media", body)
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
