#!/usr/bin/env bash
# .env 에 평문으로 있는 시크릿을 macOS 키체인으로 옮긴다.
# 저장 -> 다시 읽어 검증 -> 검증된 것만 .env 에서 제거. 값은 끝 4자리만 표시한다.
set -euo pipefail
cd "$(dirname "$0")/.."

SERVICE="insta-auto"
ENV_FILE=".env"
SECRETS="IG_ACCESS_TOKEN TOKEN_KEY"

[ -f "$ENV_FILE" ] || { echo "$ENV_FILE 이 없습니다."; exit 1; }

moved=""; failed=""

for k in $SECRETS; do
  line=$(grep -E "^[[:space:]]*${k}=" "$ENV_FILE" | head -1 || true)
  if [ -z "$line" ]; then
    if security find-generic-password -s "$SERVICE" -a "$k" >/dev/null 2>&1; then
      echo "이미 이전됨: $k"
    else
      echo "건너뜀(파일에 없음): $k"
    fi
    continue
  fi

  v=${line#*=}
  v=$(printf '%s' "$v" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' -e 's/^"\(.*\)"$/\1/' -e "s/^'\(.*\)'$/\1/")
  [ -z "$v" ] && { echo "건너뜀(값이 빔): $k"; continue; }

  # 기존 항목에 -T 를 다시 붙이면 GUI 인증창이 뜬다. 최초 생성에만 붙인다.
  if security find-generic-password -s "$SERVICE" -a "$k" >/dev/null 2>&1; then
    security add-generic-password -U -s "$SERVICE" -a "$k" -w "$v" 2>/dev/null
  else
    security add-generic-password -s "$SERVICE" -a "$k" -w "$v" -T /usr/bin/security 2>/dev/null
  fi

  back=$(security find-generic-password -w -s "$SERVICE" -a "$k" 2>/dev/null || true)
  if [ "$back" = "$v" ]; then
    echo "저장/검증 OK: $k (길이 ${#v}, ...${v: -4})"
    moved="$moved $k"
  else
    echo "검증 실패: $k  -> .env 에 그대로 둡니다"
    failed="$failed $k"
  fi
  unset v back
done

[ -z "$moved" ] && { echo; echo "옮긴 항목이 없습니다. $ENV_FILE 은 그대로입니다."; exit 0; }

tmp=$(mktemp); cp "$ENV_FILE" "$tmp"
for k in $moved; do grep -vE "^[[:space:]]*${k}=" "$tmp" > "$tmp.next" && mv "$tmp.next" "$tmp"; done
printf '\n# 아래 시크릿은 macOS 키체인(서비스명: %s)으로 옮겼습니다.\n' "$SERVICE" >> "$tmp"
for k in $moved; do printf '#   %s\n' "$k" >> "$tmp"; done
printf '# 확인: security find-generic-password -w -s %s -a KEY이름\n' "$SERVICE" >> "$tmp"
cat "$tmp" > "$ENV_FILE"; rm -f "$tmp" "$tmp.next" 2>/dev/null || true

echo; echo "완료. $ENV_FILE 에서 제거된 키:$moved"
[ -n "$failed" ] && echo "남아있는 키(검증 실패):$failed"
exit 0
