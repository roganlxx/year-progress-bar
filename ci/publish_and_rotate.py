#!/usr/bin/env python3
"""발행 + 토큰 갱신 + 다음 실행 시각 추첨.

1. state/token.enc를 TOKEN_KEY로 복호화
2. 중복 게시 방지 확인 (오늘 캡션이 이미 계정에 있으면 게시하지 않는다)
3. 릴스 발행 (publish.py의 로직 재사용)
4. 게시 성공 즉시 state/next_run.txt와 log.csv 기록
5. 토큰 refresh 후 재암호화 저장 (실패해도 게시는 이미 기록됨)
"""

import datetime as dt
import json
import os
import re
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

# 커버 썸네일 위치(ms). HOLD_OUT 구간(5.6~8.0초) 안이라 최종 퍼센트가 떠 있다.
# 지정하지 않으면 인스타가 0ms 프레임을 쓰는데, 그 프레임은 항상 0.0%다.
THUMB_OFFSET_MS = "7000"

# 마지막 게시로부터 이 시간 안이면 중복으로 보고 게시하지 않는다.
# 정상 주기는 24시간(매일 모드)이라 20시간이면 정상 실행을 막지 않는다.
COOLDOWN_HOURS = 20.0


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


def call(method, path, params, fatal=True):
    """fatal=False면 sys.exit 대신 예외를 올린다.

    게시가 끝난 뒤의 호출은 절대 잡을 죽이면 안 된다(죽으면 상태가 커밋되지
    않아 다음 실행이 같은 릴스를 또 올린다). 그런 호출에만 fatal=False를 쓴다.
    """
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


def pick_interval_hours(token) -> tuple:
    """다음 게시까지의 간격(시간)을 정한다. 게시 '전에' 정해 둔다.

    게시 후에 정하면 이 조회가 실패했을 때 next_run을 못 쓰고 죽는다.
    """
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

    date_ok = dt.datetime.now(dt.timezone.utc).date() >= EVERY4_FROM
    follow_ok = followers is not None and followers >= EVERY4_MIN_FOLLOWERS
    if date_ok and follow_ok:
        print(f"4일 간격 모드 (팔로워 {followers}명)")
        return 96.0
    print(f"매일 모드 (팔로워 {followers}명, "
          f"10월 이후={date_ok}, 100명 이상={follow_ok})")
    return 24.0


def parse_ts(ts: str):
    """인스타 timestamp를 파싱한다. 실패하면 None.

    그래프 API는 '+0000'(콜론 없음) 형식을 쓰는데 python 3.10 이하
    fromisoformat은 이 형식을 못 읽는다. 러너는 3.12지만 로컬 3.9에서도
    같게 동작해야 하므로 오프셋을 '+00:00' 형태로 맞춰 준다.
    """
    ts = ts.strip().replace("Z", "+00:00")
    m = re.search(r"([+-]\d{2})(\d{2})$", ts)
    if m:
        ts = ts[:m.start()] + f"{m.group(1)}:{m.group(2)}"
    try:
        return dt.datetime.fromisoformat(ts)
    except ValueError:
        return None


def guard_duplicate(token, caption):
    """이미 올라간 게시물이면 (permalink, 사유)를 돌려준다. 아니면 None.

    조회 자체가 실패하면 '없다'고 가정하지 않고 잡을 죽인다(fail closed).
    아무것도 게시되지 않은 상태라 크게 실패하는 편이 안전하다.
    """
    if os.environ.get("ALLOW_DUPLICATE", "").lower() == "true":
        print("ALLOW_DUPLICATE=true → 중복 확인 건너뜀")
        return None
    try:
        res = call("GET", f"/{IG_USER_ID}/media", {
            "fields": "caption,timestamp,permalink",
            "limit": "5",
            "access_token": token,
        }, fatal=False)
    except Exception as e:
        sys.exit(f"최근 게시물 조회 실패({e}) → 중복 위험이 있어 게시 중단.\n"
                 "조회가 계속 실패하면 ALLOW_DUPLICATE=true 로 우회할 수 있다.")

    items = res.get("data") or []
    now = dt.datetime.now(dt.timezone.utc)
    for it in items:
        if (it.get("caption") or "").strip() == caption.strip():
            return it.get("permalink", ""), "같은 캡션이 이미 있음"
    for it in items:
        ts = it.get("timestamp")
        if not ts:
            continue
        when = parse_ts(ts)
        if when is None:
            # 시각을 못 읽으면 쿨다운 판정을 포기하지 않고 중단한다(fail closed).
            sys.exit(f"최근 게시물 timestamp 해석 실패({ts!r}) → 게시 중단")
        if when.tzinfo is None:
            when = when.replace(tzinfo=dt.timezone.utc)
        age_h = (now - when).total_seconds() / 3600.0
        if age_h < COOLDOWN_HOURS:
            return it.get("permalink", ""), f"직전 게시가 {age_h:.1f}시간 전"
        break  # 최신 것만 본다
    return None


def record_state(day, media_id, permalink, nxt):
    """next_run과 log.csv를 기록한다. 같은 media_id 행이 있으면 갱신만 한다.

    게시 직후 permalink 없이 한 번, permalink를 얻은 뒤 한 번 더 호출한다.
    """
    rows = LOG.read_text().splitlines() if LOG.exists() else []
    rows = [r for r in rows if r.strip()]
    line = f"{day.isoformat()},{permalink or media_id},{nxt.isoformat()}"
    if rows and len(rows[-1].split(",")) > 1 and rows[-1].split(",")[1] == media_id:
        rows[-1] = line
    else:
        rows.append(line)
    LOG.write_text("\n".join(rows) + "\n")
    NEXT_RUN.write_text(nxt.isoformat())


def main():
    if "TOKEN_KEY" not in os.environ:
        sys.exit("TOKEN_KEY 환경변수가 없습니다")
    video_url = sys.argv[1]
    token = decrypt_token()
    day = dt.date.today()  # 워크플로가 TZ=Asia/Seoul로 실행
    caption = make_caption(day)

    hours = pick_interval_hours(token)

    dup = guard_duplicate(token, caption)
    if dup:
        permalink, why = dup
        nxt = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=hours)
        NEXT_RUN.write_text(nxt.isoformat())
        print(f"중복 방지: {why} → 게시하지 않음 ({permalink})")
        print(f"다음 게시: {nxt.isoformat()}")
        return

    print("컨테이너 생성...")
    # thumb_offset 은 커버 프레임을 고르는 부가 기능일 뿐이다. 이 파라미터
    # 하나 때문에 매일 게시가 통째로 멈추면 손해가 훨씬 크므로, 거절당하면
    # 빼고 한 번 더 시도한다(그때는 인스타가 0ms 프레임을 커버로 쓴다).
    body = {
        "media_type": "REELS",
        "video_url": video_url,
        "caption": caption,
        "thumb_offset": THUMB_OFFSET_MS,
        "access_token": token,
    }
    try:
        c = call("POST", f"/{IG_USER_ID}/media", body, fatal=False)
    except RuntimeError as e:
        print(f"::warning::thumb_offset 포함 요청 실패({e}). 빼고 다시 시도한다")
        body.pop("thumb_offset")
        c = call("POST", f"/{IG_USER_ID}/media", body)
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

    # 게시가 확정된 순간 바로 상태를 남긴다. 이 뒤로는 무엇이 실패해도
    # 0이 아닌 종료를 하지 않는다 → 다음 실행이 같은 릴스를 또 올리는 사고 방지.
    nxt = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=hours)
    record_state(day, media_id, "", nxt)
    print(f"게시 완료: media_id={media_id}")
    print(f"다음 게시: {nxt.isoformat()} ({hours:.1f}시간 후)")

    try:
        info = call("GET", f"/{media_id}", {
            "fields": "permalink", "access_token": token,
        }, fatal=False)
        permalink = info.get("permalink", "")
        if permalink:
            record_state(day, media_id, permalink, nxt)
            print(f"permalink: {permalink}")
    except Exception as e:
        print(f"permalink 조회 실패({e}) → 발행은 성공, media_id로 기록됨")

    print("토큰 갱신...")
    try:
        ref = call("GET", "/refresh_access_token", {
            "grant_type": "ig_refresh_token", "access_token": token,
        }, fatal=False)
        encrypt_token(ref["access_token"])
        print(f"토큰 갱신 완료 (유효 {ref['expires_in'] // 86400}일)")
    except Exception as e:
        # 기존 토큰은 그대로 유효하다. 다음 실행에서 다시 갱신하면 된다.
        print(f"토큰 갱신 실패({e}) → 기존 token.enc 유지")


if __name__ == "__main__":
    main()
