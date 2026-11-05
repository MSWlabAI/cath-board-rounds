#!/usr/bin/env bash
# Needs MM_ENV_FILE (env file) and PREP_CHECK (your preflight script) in the environment.
# One command after the Console rebuild: point the tools at the new room, restart the recorder, pin the intro, run the preflight, the offline tests and the freeze,
# then start the 10-run live streak in the background (log in ~/agents/runs/streak.log). usage: tools/after_rebuild.sh <room-slug>   (the slug is the part after /channels/ in the room URL)
set -u
SLUG="${1:?usage: tools/after_rebuild.sh <room-slug>}"; REPO="$(cd "$(dirname "$0")/.." && pwd)"; ENVF="${MM_ENV_FILE:?set MM_ENV_FILE to your env file (see .env.example)}"; AG="${AGENTS_DIR:-$HOME/agents}"
grep -q '^ROOM=' "$ENVF" && sed -i '' "s/^ROOM=.*/ROOM=$SLUG/" "$ENVF" || echo "ROOM=$SLUG" >> "$ENVF"
export ROOM="$SLUG" MM_ENV_FILE="$ENVF"; cd "$REPO" || exit 1
echo "== recorder"; for p in $(ps -axo pid,command | grep "tools/recorder.py" | grep -v grep | awk '{print $1}'); do kill "$p"; done; rm -rf briefs/case-* briefs/approvals.jsonl briefs/rulings.json briefs/board-draft.md
(nohup python3 -u tools/recorder.py > /tmp/recorder.log 2>&1 &); sleep 6; ls briefs | head -3
echo "== pin the intro"; python3 tools/pin_intro.py
echo "== prompts: template vs folders vs the Console's stored copies"; python3 tools/sync_prompts.py --console || echo "!! DRIFT: re-import the template in the Console, then rerun this script"
echo "== offline tests"; ./check.sh --selftest | tail -1; python3 tools/plan.py --selftest | tail -1; python3 tools/scenarios_test.py | grep -c PASS
echo "== preflight"; ROOM="$SLUG" REPO="$REPO" bash "${PREP_CHECK:?set PREP_CHECK to your preflight script}" 2>&1 | grep -E "FAIL|READY"
echo "== freeze"; python3 tools/freeze.py | tail -12
echo "== 10-run streak (background; ~25 min): tail -f $AG/runs/streak.log"; mkdir -p "$AG/runs"; (nohup python3 -u tools/check.py --run --n 10 > "$AG/runs/streak.log" 2>&1 &); echo started
