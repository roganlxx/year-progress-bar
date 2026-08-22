#!/bin/bash
# year-progress-bar 저장소 생성 + 시크릿 + Pages 활성화 (1회용)
set -e
export PATH="$HOME/.local/bin:$PATH"
cd "/Users/rogan/개발 001/insta-auto"

echo "== 1. git 커밋 =="
git init 2>/dev/null || true
git add -A
git -c user.name="rogan" -c user.email="hxngdabin@gmail.com" commit -m "year progress bar 자동 발행 파이프라인" || echo "(변경 없음)"

echo "== 2. 공개 저장소 생성 + 푸시 =="
gh repo create year-progress-bar --public --source . --push

echo "== 3. TOKEN_KEY 시크릿 등록 (.env에서 읽어서, 화면엔 안 보임) =="
grep '^TOKEN_KEY=' .env | cut -d= -f2- | tr -d '\n' | gh secret set TOKEN_KEY --repo roganlxx/year-progress-bar

echo "== 4. GitHub Pages 활성화 (main 브랜치 /docs) =="
gh api -X POST repos/roganlxx/year-progress-bar/pages \
  -f "source[branch]=main" -f "source[path]=/docs" 2>/dev/null \
  || echo "(이미 활성화됐거나 잠시 후 재시도 필요)"

echo ""
echo "== 완료. 확인 =="
gh repo view roganlxx/year-progress-bar --json url,visibility -q '.url + " (" + .visibility + ")"'
gh secret list --repo roganlxx/year-progress-bar
