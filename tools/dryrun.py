#!/usr/bin/env python3
"""Full smoke test of the filmed flow in the live room. Needs three human clicks (the script says when).
Steps: 1 briefs for 5 cases (scored)  2 rulings echo  3 board draft  4 board final -> Decline  5 board final -> Allow once (+board PDF)
       6 Plan case 2 -> Allow once (+plan PDF)  7 card sanity (buttons present, short).  Prints a PASS/FAIL table; exit 1 on any FAIL.
usage: dryrun.py [--skip-briefs]"""
import os, re, shutil, sys, time
import mm, board, check, clerk, board_pdf, packet
AGENTS_DIR = os.path.expanduser(os.environ.get("AGENTS_DIR", "~/agents")); CLERK = os.path.join(AGENTS_DIR, "cath-clerk"); res = []
def rec(name, ok, note=""): res.append((name, ok, note)); print(("PASS " if ok else "FAIL ") + name + (f"  [{note}]" if note else ""), flush=True)
def clerk_say(tok, ch, user, msg, accept, limit):
    t0 = time.time(); pid = mm.post(tok, ch, "@clerk " + msg); out = []
    while time.time() - t0 < limit:
        time.sleep(2)
        for p in mm.posts_since(tok, ch, t0, {pid}):
            if p["user_id"] == user and p["id"] not in [x["id"] for x in out]:
                out.append(p)
                if re.match(accept, p["message"].strip()): return time.time() - t0, out
    return None, out
def banner(t): print("\n" + "=" * 70 + f"\n>>> YOUR CLICK: {t}\n" + "=" * 70, flush=True)
def archive(f):
    os.makedirs(os.path.join(AGENTS_DIR, "runs"), exist_ok=True)
    if os.path.exists(f): shutil.move(f, os.path.join(AGENTS_DIR, "runs", os.path.basename(f) + "." + str(int(time.time()))))
def main(a):
    tok = mm.login(); ch = mm.room(tok); user = mm.user_id(tok, "clerk")
    if "--skip-briefs" not in a:
        for c in "12345":
            r = board.collect(c)
            if c == "2": r2 = {ag: (x[1] if x else "") for ag, x in r.items()}
            for ag, x in r.items():
                miss, fmt = check.score(c, ag, x[1]) if x else (["timeout"], [])
                rec(f"brief case {c} {ag}", not miss, "; ".join(miss) or (f"{x[0]:.0f}s" + (f" format: {'; '.join(fmt)}" if fmt else "")))
    t, out = clerk_say(tok, ch, user, "Review case 2", r"\*\*🧾 CASE 2 REVIEW", 150); sheet = out[-1]["message"] if out else ""
    m = check.score_review("2", sheet, locals().get("r2")) if t else ["timeout"]; rec("case review sheet is structured and faithful", not m, "; ".join(m) or f"{t:.0f}s")
    for i, line in enumerate([packet.DEFAULT_RULINGS[0], packet.DEFAULT_RULINGS[3]]):
        t, out = clerk_say(tok, ch, user, line, r"RULING RECEIVED", 90); rec(f"ruling echo {i + 1}", bool(t) and out[-1]["message"].strip() == "RULING RECEIVED: " + line, f"{t:.0f}s" if t else "timeout")
    rul = "RULINGS\n" + "\n".join(packet.DEFAULT_RULINGS)
    day = open(os.path.join(os.path.dirname(__file__), "..", "day.md")).read(); tbl = day.split("## CASE TABLE")[1].split("## PACKETS")[0].strip(); slots = day.split("## SLOTS (scheduled)")[1].split("##")[0].strip()
    t, out = clerk_say(tok, ch, user, f"Board draft\n{rul}\n\nCASE TABLE\n{tbl}\n\nSLOT LIST\n{slots}", r"(?s).*\|---", 120); draft = out[-1]["message"] if out else ""
    rows = [l for l in draft.splitlines() if re.match(r"^\|\s*\d\d:\d\d", l)]
    rec("board draft is a Markdown table", bool(t) and "|---" in draft and len(rows) == 5, f"{len(rows)} rows")
    rec("board draft puts Case 1 last, slots 07:30..14:00", len(rows) == 5 and "| 1 |" in rows[-1] and rows[0].startswith("| 07:30") and rows[-1].startswith("| 14:00"))
    final = draft.strip(); bf = os.path.join(CLERK, "board-final.md"); archive(bf); archive(os.path.join(CLERK, "board-final.pdf"))
    banner("press DECLINE (3rd button) on the Clerk's board card"); t, out = clerk_say(tok, ch, user, "Board is final", r"BOARD NOT SIGNED|BOARD SIGNED", 600)
    card = [p["message"] for p in out if "Permission needed" in p["message"]]
    rec("board card has buttons, answerable in Mattermost", bool(card) and "cannot be answered" not in card[0] and len(card[0]) < 2500, f"{len(card[0])} chars" if card else "no card")
    rec("structured approval block before the card", any("APPROVAL NEEDED" in p["message"] and "Who can answer" in p["message"] for p in out))
    rec("Decline -> BOARD NOT SIGNED and no file", bool(t) and out[-1]["message"].strip() == "BOARD NOT SIGNED" and not os.path.exists(bf))
    time.sleep(4); banner("press ALLOW ONCE (1st button) on the new board card"); t, out = clerk_say(tok, ch, user, "Board is final", r"BOARD NOT SIGNED|BOARD SIGNED", 600)
    rec("Allow once -> BOARD SIGNED and file written", bool(t) and out[-1]["message"].strip() == "BOARD SIGNED" and os.path.exists(bf))
    pdfb = os.path.join(CLERK, "board-final.pdf")
    if os.path.exists(bf):
        wrote = open(bf).read().strip(); rec("board-final.md matches the draft table", [l.strip() for l in wrote.splitlines() if "|" in l] == [l.strip() for l in final.splitlines() if "|" in l])
    rec("signed board PDF written by the Clerk's command", os.path.exists(pdfb) and os.path.getsize(pdfb) > 50000)
    for f in ("plan-case-2.pdf", "plan-case-2.md", "plan-case-2.html"): archive(os.path.join(CLERK, "plans", f))
    time.sleep(4); banner("press ALLOW ONCE on the PLAN card"); t, out = clerk_say(tok, ch, user, "Plan case 2", r"PLAN SIGNED|PLAN NOT SIGNED|PLAN INCOMPLETE", 600)
    card = [p["message"] for p in out if "Permission needed" in p["message"]]
    rec("plan card short, has buttons", bool(card) and "cannot be answered" not in card[0] and len(card[0]) < 1200, f"{len(card[0])} chars" if card else "no card")
    pdf = os.path.join(CLERK, "plans", "plan-case-2.pdf"); mdp = os.path.join(CLERK, "plans", "plan-case-2.md")
    rec("Allow once -> PLAN SIGNED and PDF written", bool(t) and out[-1]["message"].startswith("PLAN SIGNED") and os.path.exists(pdf) and os.path.getsize(pdf) > 50000)
    txt = open(mdp).read() if os.path.exists(mdp) else ""
    rec("plan marked APPROVED by the chair", "APPROVED by the chair" in txt)
    rec("plan content: ratio 7.1, lesion map, chair decides, 4 agents' flags", all(k in txt for k in ("Contrast ratio: 7.1", "Lesion map", "Chair to decide whether to stage", "**Imaging**", "**Labs**", "**Meds**", "**Equipment**")))
    bad = [r for r in res if not r[1]]; print(f"\nDRY RUN: {len(res) - len(bad)}/{len(res)} passed"); [print("  FAIL:", r[0], r[2]) for r in bad]; return 1 if bad else 0
if __name__ == "__main__": sys.exit(main(sys.argv[1:]))
