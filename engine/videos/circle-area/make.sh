#!/bin/bash
# Why Is the Area of a Circle πr²? : build the finished short on this computer, best quality.
# Run in Git Bash from anywhere:   bash ~/Documents/faceless-shorts/videos/circle-area/make.sh
#   voice (Kokoro bm_george) → Whisper word timing → check → sound → contact sheet → 60 fps master → share copy + cover
# Takes roughly 5-15 minutes (the 60 fps lossless master is the slow part). Safe to re-run.
set -euo pipefail
P="$(cd "$(dirname "$0")" && pwd)"; SKILL="$(cd "$P/../.." && pwd)"; PY="$SKILL/scripts/py"; cd "$P"
step() { printf '\n\033[1m== %s\033[0m\n' "$1"; }

step "1/7 checking the install (setup.sh is quick when everything is already there)"
bash "$SKILL/scripts/setup.sh"

step "2/7 voice: Kokoro bm_george → data/narration.wav"
"$PY" "$SKILL/scripts/voice.py" .

step "3/7 word timing: Whisper → data/words.json (cuts moved onto the heard words)"
"$PY" "$SKILL/scripts/words.py" .

step "4/7 check: every frame draws, shots and captions line up"
mkdir -p review renders
node tools/capture.mjs check | tee review/check.txt
grep -q "CHECK OK" review/check.txt || { echo "CHECK FAILED: see review/check.txt"; exit 1; }

step "5/7 sound: effects + music bed + voice → data/mix.wav (-14 LUFS)"
node tools/capture.mjs cues
"$PY" tools/mix.py .

step "6/7 contact sheet for review → review/all.jpg"
node tools/capture.mjs sheet review/all.jpg 0.5 10

step "7/7 the master: 60 fps, lossless frames, x264 slow CRF 14 → renders/circle-area.mp4"
FPS=60 node tools/capture.mjs video renders/circle-area.mp4 --best

# a smaller copy for phones / chat apps, and a cover frame
ffmpeg -v error -y -i renders/circle-area.mp4 -c:v libx264 -crf 20 -preset slow -c:a aac -b:a 160k -movflags +faststart renders/circle-area-share.mp4
COVER=$(node -e "const w=require('./data/words.json').filter(x=>x.line===11&&/^squared/i.test(x.w));console.log(w.length?(w[0].e+0.5).toFixed(2):'2')")
node tools/capture.mjs frames review/cover "$COVER" >/dev/null 2>&1 || true   # the A = πr² stamp

echo
echo "DONE"
echo "  master: $P/renders/circle-area.mp4  ($(du -h renders/circle-area.mp4 | cut -f1))"
echo "  share:  $P/renders/circle-area-share.mp4  ($(du -h renders/circle-area-share.mp4 | cut -f1))"
echo "  review: $P/review/all.jpg   ·   warnings above (WARN lines) are worth a look"
