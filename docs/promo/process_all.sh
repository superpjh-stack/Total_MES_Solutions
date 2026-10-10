#!/bin/sh
# 업무 프로세스 유형별 영상 전부(또는 인자로 준 코드만) 녹화 → docs/promo/process/<코드>.mp4 · <코드>.jpg(포스터 = 첫 카드)
#   sh docs/promo/process_all.sh [P01 P02 …]   작업 폴더: $WORK (기본 /tmp/test_video_maker/process)
set -e
WORK=${WORK:-${TMPDIR:-/tmp}/test_video_maker/process}
CODES=${*:-"P01 P02 P03 P04 P05 P06 P07 P08 P09 P10"}
mkdir -p docs/promo/process
for c in $CODES; do
  echo "== $c"
  PROC=$c node ~/.claude/skills/test_video_maker/bin/record.mjs docs/promo/process.scenario.mjs --work "$WORK/$c"
  cp "$(ls "$WORK/$c/review/"01_*.jpg | head -1)" "docs/promo/process/$c.jpg"
done
