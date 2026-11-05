#!/usr/bin/env python3
"""Room recorder: saves each agent's latest brief per case to briefs/case-N/<agent>.md so the Clerk's plan command stays short
(Switch shows no buttons on long approval cards). Chair-side helper, read-only on the room.
Also saves the Clerk's latest board draft to briefs/board-draft.md. Rules: only a post written by the agent's OWN account is recorded; a new chair packet for a case clears that case's folder (no stale briefs);
oldest-first replay so the newest brief wins; a heartbeat file proves it is alive (plan.py refuses stale briefs without it); errors are logged and retried.
usage: recorder.py [--once]"""
import os, re, shutil, sys, time
import json, mm, records, plan, board_final
OUT = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "briefs")
HEAD = re.compile(r"^\s*(?:@\w+\s+)*\*\*\[(\w+) — Case ([1-9])\]\*\*", re.I)
PACKET = re.compile(r"^@\w+(?:\s+@\w+)*\s+\*\*Case ([1-9])\*\*")
ASKS = re.compile(r"^@clerk\s+(?:plan case ([1-9])\b|(board is final)\b)", re.I)
AGENTS = ("imaging", "labs", "meds", "equipment")

def log(msg):
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "_recorder.log"), "a") as f: f.write(time.strftime("%F %T ") + msg + "\n")

def sweep(tok, ch, ids, since, seen):
    """-> (next since, briefs written, folders cleared). ids maps user_id -> agent name, plus '_chair'."""
    wrote = cleared = 0
    for p in mm.posts_since(tok, ch, since, set()):  # oldest first
        key = (p["id"], p.get("update_at", 0))  # Switch edits a card post in place (pending -> Allow once), so key on the edit time too
        if key in seen: continue
        seen.add(key); since = max(since, max(p["create_at"], p.get("update_at", 0)) / 1000 - 2)
        if p["user_id"] == ids["_chair"]:
            m = PACKET.match(p["message"])
            if m:
                shutil.rmtree(os.path.join(OUT, f"case-{m.group(1)}"), ignore_errors=True); cleared += 1
                open(os.path.join(OUT, f"packet-{m.group(1)}.json.tmp"), "w").write(json.dumps({"id": p["id"], "ts": p["create_at"] / 1000})); os.replace(os.path.join(OUT, f"packet-{m.group(1)}.json.tmp"), os.path.join(OUT, f"packet-{m.group(1)}.json"))
            k = ASKS.match(p["message"].strip())
            if k and p["create_at"] / 1000 > time.time() - 120:  # live asks only, not a replay
                pr = plan.check(k.group(1), os.path.join(OUT, f"case-{k.group(1)}")) if k.group(1) else board_final.problems(OUT)
                what = f"plan case {k.group(1)}" if k.group(1) else "board"; msg = f"PRECHECK {what}: " + ("ready to sign" if not pr else "WOULD REFUSE: " + "; ".join(pr))
                print(msg, flush=True); log(msg)
            continue
        if p["user_id"] == ids["_clerk"]:
            if p["message"].lstrip().startswith("BOARD —") and "|---" in p["message"]: open(os.path.join(OUT, "board-draft.md"), "w").write(p["message"].strip() + "\n"); wrote += 1
            n = records.note(p)
            if n and n[0] == "approval":
                have = {a["id"] for a in records.approvals(OUT)}
                if n[1]["id"] not in have:
                    with open(os.path.join(OUT, "approvals.jsonl"), "a") as f: f.write(json.dumps(n[1]) + "\n")
            elif n and n[0] == "ruling":
                cur = records.rulings(OUT)
                if n[1][2] >= cur.get(n[1][0], {}).get("ts", 0): cur[n[1][0]] = {"text": n[1][1], "ts": n[1][2]}; open(os.path.join(OUT, "rulings.json"), "w").write(json.dumps(cur))
            continue
        m = HEAD.match(p["message"])
        if m and ids.get(p["user_id"]) == m.group(1).lower():  # the brief's header must name the account that posted it
            d = os.path.join(OUT, f"case-{m.group(2)}"); os.makedirs(d, exist_ok=True)
            open(os.path.join(d, m.group(1).lower() + ".md"), "w").write(re.sub(r"^\s*(?:@\w+\s+)+", "", p["message"]).strip() + "\n"); wrote += 1
    return since, wrote, cleared

def main(once):
    os.makedirs(OUT, exist_ok=True); seen = set(); since = time.time() - (3600 if once else 600); tok = None
    while True:
        try:
            if tok is None:
                tok = mm.login(); ch = mm.room(tok); ids = {mm.user_id(tok, a): a for a in AGENTS}; ids["_chair"] = mm.user_id(tok, os.environ.get("MM_CHAIR_USER", "chargenurse")); ids["_clerk"] = mm.user_id(tok, "clerk")
            since, w, c = sweep(tok, ch, ids, since, seen)
            open(os.path.join(OUT, "_heartbeat"), "w").write(str(time.time()))
            if once: print(f"recorded {w} briefs, cleared {c} case folders"); return 0
        except (Exception, SystemExit) as e:  # Mattermost down, token expired, room renamed: log, retry, never die silently
            log(f"error: {e!r}"); tok = None; time.sleep(5)
            if once: print(f"recorder error: {e}"); return 1
        time.sleep(2)

if __name__ == "__main__": sys.exit(main("--once" in sys.argv))
