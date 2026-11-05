#!/usr/bin/env python3
"""Sign the board: write board-final.md and board-final.pdf from the Clerk's latest recorded board draft (briefs/board-draft.md).
Run by the Clerk after the chair presses Allow once; refuses a missing or stale draft and a dead recorder.
usage: board_final.py [--out DIR] [--approved] [--briefs DIR]"""
import os, re, sys, time
SIGN_WAIT_S = 10  # the recorder polls every 2 s; the Clerk can run this within 1 s of the click
import board_pdf, html, records, plan
HERE = os.path.dirname(os.path.realpath(__file__)); ROOT = os.path.join(HERE, "..")
MAX_AGE_MIN, HEARTBEAT_S = 90, 180
def ruling_text(ru, c):
    return re.sub(r'^Case \d = ', '', ru.get(c, {}).get('text', 'no ruling recorded'))


def summary(rows, d, approved=False):
    """HTML 'Session summary' (ruling and plan status per case) and 'Approvals' (every card decision) from the recorder's records."""
    e = html.escape; ap = records.approvals(d); ru = records.rulings(d); out = []
    for r in rows:
        c = [x.strip() for x in r.strip().strip("|").split("|")][1]; plan = [x for x in ap if re.search(rf"\bcase {re.escape(c)}\b", x["what"], re.I)]
        last = plan[-1] if plan else None; st = "not requested" if not last else (f"signed {records.when(last['ts'])}" if last["decision"].startswith("Allow") else f"{last['decision'].lower()} {records.when(last['ts'])}")
        out.append(f"<tr><td>{e(c)}</td><td>{e(ruling_text(ru, c))}</td><td>{e(st)}</td></tr>")
    s = "<h2>Session summary</h2><table><tr><th>Case</th><th>Chair's ruling as recorded</th><th>Plan</th></tr>" + "".join(out) + "</table>"
    rows_ap = "".join(f"<tr><td>{e(records.when(x['ts']))}</td><td>{e(x['request'])}</td><td class='{'ok' if x['decision'].startswith('Allow') else 'out'}'>{e(x['decision'])}</td><td>{e(x['what'])}</td><td>{e(x['by'])}</td></tr>" for x in ap)
    if approved: rows_ap += f"<tr><td>{e(time.strftime('%H:%M:%S'))}</td><td>this board</td><td class=ok>Allow once</td><td>Sign the final board</td><td>the chair, on the Switch card</td></tr>"
    return s + "<h2>Approvals</h2>" + (f"<table><tr><th>Time</th><th>Request</th><th>Decision</th><th>What</th><th>By</th></tr>{rows_ap}</table>" if rows_ap else "<p>No approval decisions recorded.</p>")

def problems(d, now=None):
    """What would make `Board is final` refuse (no writes): list of strings, empty = ready."""
    now = now or time.time(); src = os.path.join(d, "board-draft.md"); hb = os.path.join(d, "_heartbeat"); out = []
    if not os.path.exists(src): return ["no board draft recorded; ask the Clerk for a Board draft first"]
    if now - os.path.getmtime(src) > MAX_AGE_MIN * 60: out.append(f"the board draft is older than {MAX_AGE_MIN} min")
    if not os.path.exists(hb) or now - os.path.getmtime(hb) > HEARTBEAT_S: out.append("the room recorder is not running")
    ru = records.rulings(d); newest = max([r.get("ts", 0) for r in ru.values()] or [0])
    if newest > os.path.getmtime(src): out.append("a ruling was recorded after the latest board draft: ask for a new Board draft")
    return out

def main(a):
    arg = lambda k, d=None: a[a.index(k) + 1] if k in a else d
    d = os.path.abspath(arg("--briefs", os.path.join(ROOT, "briefs"))); out = os.path.abspath(arg("--out", ".")); src = os.path.join(d, "board-draft.md"); hb = os.path.join(d, "_heartbeat"); now = time.time()
    if not os.path.exists(src): print("BOARD INCOMPLETE: no board draft recorded; ask the Clerk for a Board draft first"); return 3
    if now - os.path.getmtime(src) > MAX_AGE_MIN * 60: print(f"BOARD INCOMPLETE: the board draft is older than {MAX_AGE_MIN} min; ask for a new Board draft"); return 3
    if not os.path.exists(hb) or now - os.path.getmtime(hb) > HEARTBEAT_S: print("BOARD INCOMPLETE: the room recorder is not running, so the draft may be stale"); return 3
    if "--approved" in a and not records.signed(d, r"board", os.path.getmtime(src), wait=SIGN_WAIT_S): print("BOARD INCOMPLETE: no Allow once recorded for the board after its latest draft; not signing"); return 3
    text = open(src).read().strip(); rows = [l for l in text.splitlines() if re.match(r"^\|\s*\d\d:\d\d", l)]
    if not text.startswith("BOARD —") or not rows: print("BOARD INCOMPLETE: the recorded draft is not a board table"); return 3
    os.makedirs(out, exist_ok=True); md = os.path.join(out, "board-final.md"); pdf = os.path.join(out, "board-final.pdf"); [os.remove(f) for f in (md, pdf) if os.path.exists(f)]; plan.atomic(md, text + "\n")
    board_pdf.render(md, pdf, "--approved" in a, extra=summary(rows, d, "--approved" in a))
    if not (os.path.exists(pdf) and os.path.getsize(pdf) > 1000): print("BOARD INCOMPLETE: the PDF was not produced (is Google Chrome installed?); board-final.md was written"); return 2
    print(f"board-final.md and board-final.pdf written ({len(rows)} cases)"); return 0
if __name__ == "__main__": sys.exit(main(sys.argv[1:]))
