"""Chair-side records the recorder keeps from the room: every approval decision (Allow, Decline, Closed) and the latest ruling per case.
Read by plan.py and board_final.py so the signed PDFs carry a summary with the approvals."""
import json, os, re, time
DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "briefs")
CARD = re.compile(r"^\*\*(Allow once|Allow for this session|Decline|Closed)\*\* · request `(A\d+)`\s*(?:\||\n)\s*([^\n|]*)", re.S)
CHOSEN = re.compile(r"Chosen by @(\w+)")
RULING = re.compile(r"^RULING RECEIVED: (Case ([1-9]) = .*)$")

def approvals(d=DIR):
    p = os.path.join(d, "approvals.jsonl")
    return [json.loads(l) for l in open(p)] if os.path.exists(p) else []

def rulings(d=DIR):
    p = os.path.join(d, "rulings.json")
    return json.load(open(p)) if os.path.exists(p) else {}

def when(ts): return time.strftime("%H:%M:%S", time.localtime(ts))

def note(post):
    """-> ('approval', record) | ('ruling', (case, text, ts)) | None for one Clerk post."""
    msg = post["message"].strip(); m = CARD.match(msg)
    if m:
        who = CHOSEN.search(msg); return "approval", {"id": post["id"], "ts": max(post["create_at"], post.get("update_at", 0)) / 1000, "request": m.group(2), "decision": m.group(1), "what": m.group(3).strip(), "by": who.group(1) if who else ("the chair via interrupt" if m.group(1) == "Closed" else "the chair")}
    m = RULING.match(post["message"].strip())
    if m: return "ruling", (m.group(2), m.group(1), post["create_at"] / 1000)
