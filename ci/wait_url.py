#!/usr/bin/env python3
"""GitHub Pages 배포가 끝나 URL이 video/mp4로 서빙될 때까지 대기한다."""

import sys
import time
import urllib.error
import urllib.request


def main():
    url = sys.argv[1]
    deadline = time.time() + 8 * 60
    while time.time() < deadline:
        try:
            req = urllib.request.Request(url, method="HEAD")
            with urllib.request.urlopen(req, timeout=15) as r:
                ctype = r.headers.get("Content-Type", "")
                if r.status == 200 and "video" in ctype:
                    print(f"준비 완료: {url} ({ctype})")
                    return
                print(f"대기: status={r.status} type={ctype}")
        except urllib.error.HTTPError as e:
            print(f"대기: HTTP {e.code}")
        except Exception as e:
            print(f"대기: {e}")
        time.sleep(15)
    sys.exit("시간 초과: Pages 배포가 완료되지 않음")


if __name__ == "__main__":
    main()
