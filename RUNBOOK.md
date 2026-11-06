# Runbook: running the room for a take

For the operator (not the chair's script). The chair's flow is in `README.md`; this is what keeps a live session from dying halfway.

## Before anything (once per sitting)

1. **AC power on, sleep prevented:** `caffeinate -dimu -t 28800 &`. A sleeping Mac stops the recorder and the agents without any error.
2. **At least 10 GB free** on the system disk (`df -h /`). Mattermost, Docker and the agent CLIs all write.
3. **Launch the Switch Console from a fresh Terminal**, with the Cursor CLI's `agent` ahead of any other `agent` on PATH (`which agent` must print the Cursor one). A Console started from the Dock keeps the old PATH.
4. **Start the helpers, one copy each:** `python3 tools/recorder.py` and `python3 tools/callback_forward.py`. Check `pgrep -f tools/recorder.py | wc -l` prints `1` and that `briefs/_heartbeat` is under 10 s old (signing refuses if it is over 180 s). Watch `briefs/_recorder.log` for `error:` lines during the take: after one, the recorder needs a few seconds before it logs an Allow (signing waits up to 10 s).
5. **After any room rebuild** run `tools/after_rebuild.sh` (needs `MM_ENV_FILE` and, if you use it, `PREP_CHECK`). It points the tools at the new room, clears the old state (including the Clerk's old signed files in `~/agents/cath-clerk/plans/` and `board-final.*`), restarts the recorder, resets Meds, pins the intro and runs the offline tests. Add `--streak` only if you want the 10-run check; it fills the room with test packets, so do it before you create the clean filming room. In the terminal you film from, `unset ROOM`: a stale exported `ROOM` makes `./case` post to the old room.
6. **Prompt drift:** `python3 tools/sync_prompts.py --console` must print no DRIFT. If it does, re-import `~/agents/cath-board-rounds-final.yaml` (Console: template, then Use template) before filming.
7. **Wipe stale state** only with the recorder stopped: `rm -rf briefs/case-* briefs/packet-*.json briefs/approvals.jsonl briefs/rulings.json briefs/board-draft.md`, then start it again.
8. **After the Mac wakes,** ping each agent once (any short message) before the first real packet.

## Rehearse once, exactly as filmed

- Same browser zoom, with the filming Chrome open (the PDF is rendered by a headless Chrome and must still be produced).
- Read the card's text before you click: signing matches it. `Write the Case 2 plan PDF` and `Write the final board files` are the expected wordings; a card that names two cases, or a plan for the board, will refuse to sign.
- Only `Allow once`, chosen by the chair account, signs. `Allow for this session` does not.
- `docker exec` the Mattermost container's `date` against the host's `date`: a clock skew of more than a few seconds can make an Allow look older than the briefs.
- Open a PDF only after reading `PLAN SIGNED plans/plan-case-N.pdf` or the board's `written` line: after a Decline nothing is written, and an older file would still be on disk if the cleanup was skipped.

## During a take

- Paste each packet from the clipboard (`./case N imaging labs`), never by hand.
- After the four briefs arrive: `ls -l briefs/case-N` must show four files newer than the packet.
- Before you press Allow, read the recorder's terminal: `PRECHECK plan case N: ready to sign` or `WOULD REFUSE: <reason>`. Fix a refusal first. You can also run `python3 tools/plan.py N --briefs briefs/case-N --check` (writes nothing).
- To preview a plan without signing: `python3 tools/plan.py N --briefs briefs/case-N --out /tmp/plan` (add `--pdf` to see the PDF).
- If briefs are older than 90 minutes or from different runs, the plan refuses: send the packet to the agents again.
- **Never `!reset` during a turn** (the agents post a chatty ready message). If a turn is stuck: `!interrupt @name`, then send the line again.
- If Imaging's handoff does not start Equipment within 60 s, type `@equipment` on the same case once (the chair may always address any agent).
- Signing needs a recorded Allow: `A<n> 1` typed or the button. A Decline writes nothing; a plan stamped without an Allow is refused.

## After filming

1. Stop the recorder and the forwarder (`pkill -f tools/recorder.py; pkill -f tools/callback_forward.py`).
2. Copy the signed PDFs out of `plans/` and `board-final.pdf`; they are git-ignored.
3. Before any push: run the secret scan (the pre-commit hook does it), `git reflog expire --expire=now --all && git gc --prune=now`, push `main` only, never `--all` or `--mirror`.

## When things go wrong

| Symptom | Likely cause | Fix |
|---|---|---|
| Plan refuses: "recorder is not running" | recorder died or the Mac slept | restart it; `briefs/_recorder.log` has the error |
| `set MM_CHAIR_PASSWORD` in the recorder log | started without the env file | `set -a; . <your env file>; set +a` then start it |
| Card has no buttons | the card text is over 4,000 characters | Clerk commands must stay one short line; answer by typing `A<n> 1` |
| Imaging never answers (provider `cursor`) | Cursor not logged in, the wrong `agent` on PATH, or the weekly usage limit (`agent -p ok` says so) | `which agent`; `agent login`; relaunch the Console from Terminal; or set `provider: claude` for Imaging in `template.yaml` and re-import |
| Imaging's session will not start after a crash (`Session ... not found`, `Invalid params`) | the resume record points at a Cursor session with no stored history | restart the Console; if it persists, point the session host's resume record at an older session that has a `store.db` (see `~/.cursor/acp-sessions`) |
| Two cards, or a duplicated brief | two recorders running | `pkill -f tools/recorder.py`, start one |
| "PARSE WARNINGS" banner on a plan | the packet has a value the plan cannot read | read the banner; fix the packet line or accept that the rule did not run |

## A fresh room's Meds posts without reading the room

Symptom: after a rebuild, Meds' `**Values:**` line shows only eGFR, INR or platelets (Labs's handoff) and never the medication list; `check.py --run` misses the metformin and anticoagulant flags. Fix: post `!reset @meds` in the room (off camera), then rerun one case. Check this before the first take.
