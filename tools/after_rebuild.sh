#!/usr/bin/env bash
# Needs MM_ENV_FILE (env file) in the environment; PREP_CHECK (your preflight script) is optional. macOS only (sed -i '').
# One command after the Console rebuild: point the tools at the new room, restart the recorder, pin the intro, run the preflight, the offline tests and the freeze,
# optionally start the 10-run live streak with --streak (log in ~/agents/runs/streak.log). usage: tools/after_rebuild.sh <room-slug> [--streak]   (the slug is the part after /channels/ in the room URL)
set -u
SLUG="${1:?usage: tools/after_rebuild.sh <room-slug> [--streak]}"; REPO="$(cd "$(dirname "$0")/.." && pwd)"; ENVF="${MM_ENV_FILE:?set MM_ENV_FILE to your env file (see .env.example)}"; AG="${AGENTS_DIR:-$HOME/agents}"
case "$SLUG" in *[!a-z0-9_-]*|"") echo "bad room slug: use only lower-case letters, digits, - and _ (the part after /channels/)"; exit 2;; esac
grep -q '^ROOM=' "$ENVF" && sed -i '' "s/^ROOM=.*/ROOM=$SLUG/" "$ENVF" || echo "ROOM=$SLUG" >> "$ENVF"
export ROOM="$SLUG" MM_ENV_FILE="$ENVF"; cd "$REPO" || exit 1
echo "== recorder"; for p in $(ps -axo pid,command | grep "tools/recorder.py" | grep -v grep | awk '{print $1}'); do kill "$p"; done; rm -rf briefs/case-* briefs/packet-*.json briefs/approvals.jsonl briefs/rulings.json briefs/board-draft.md
SAVE="$AG/runs/signed.$(date +%s)"; mkdir -p "$SAVE"; mv "$AG"/cath-clerk/plans/* "$AG"/cath-clerk/board-final.* "$SAVE"/ 2>/dev/null; rmdir "$SAVE" 2>/dev/null || echo "== previous signed files moved to $SAVE"   # the Clerk writes its signed files here; an old APPROVED PDF must not survive into a new take, but a finished take is moved aside, never deleted
[ -n "${ROOM_BEFORE:-}" ] || true
(nohup python3 -u tools/recorder.py > "$REPO/briefs/_recorder.out" 2>&1 &); sleep 6; ls briefs | head -3
echo "== reset Meds (a fresh room's Meds can start without reading the room)"; python3 -c "import sys; sys.path.insert(0, 'tools'); import mm; t = mm.login(); mm.post(t, mm.room(t), '!reset @meds')" && sleep 20
echo "== pin the intro"; python3 tools/pin_intro.py
echo "== prompts: template vs folders vs the Console's stored copies"; python3 tools/sync_prompts.py --console || echo "!! DRIFT: re-import the template in the Console, then rerun this script"
echo "== offline tests"; ./check.sh --selftest | tail -1; python3 tools/plan.py --selftest | tail -1; python3 tools/scenarios_test.py | grep -c PASS
echo "== preflight"; if [ -n "${PREP_CHECK:-}" ]; then ROOM="$SLUG" REPO="$REPO" bash "$PREP_CHECK" 2>&1 | grep -E "FAIL|WARN|READY" | tee /tmp/prep.$$ | cut -c1-160; grep -q READY /tmp/prep.$$ || echo "!! preflight did not finish: do not film"; rm -f /tmp/prep.$$; else echo "(PREP_CHECK not set: preflight skipped)"; fi
echo "== freeze"; python3 tools/freeze.py | tail -12
echo "!! In the terminal you will film from: run 'unset ROOM' (or export ROOM=$SLUG), or ./case posts to the wrong room"
if [ "${2:-}" = "--streak" ]; then echo "== 10-run streak (background; ~7 min; do NOT film while it runs): tail -f $AG/runs/streak.log"; mkdir -p "$AG/runs"; (nohup python3 -u tools/check.py --run --n 10 > "$AG/runs/streak.log" 2>&1 &); echo started
else echo "== streak skipped (pass --streak as the 2nd argument to run it; it fills the room with test packets, so run it BEFORE a clean filming room is made)"; fi
