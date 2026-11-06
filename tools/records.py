"""Chair-side records the recorder keeps from the room: every approval decision (Allow, Decline, Closed) and the latest ruling per case.
Read by plan.py and board_final.py so the signed PDFs carry a summary with the approvals."""
import json, os, re, time
DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "briefs")
CARD = re.compile(r"^\*\*(Allow once|Allow for this session|Decline|Closed)\*\* · request `(A\d+)`\s*(?:\||\n)\s*([^\n|]*)", re.S)
CHOSEN = re.compile(r"Chosen by @(\w+)")
RULING = re.compile(r"^RULING RECEIVED: (Case ([1-9]) = .*)$")

def approvals(d=DIR):
    p = os.path.join(d, "approvals.jsonl")
    out = []
    for l in (open(p) if os.path.exists(p) else []):
        try: out.append(json.loads(l))
        except ValueError: pass  # a torn line must not take the whole record down
    return out

def rulings(d=DIR):
    p = os.path.join(d, "rulings.json")
    return json.load(open(p)) if os.path.exists(p) else {}

def when(ts): return time.strftime("%H:%M:%S", time.localtime(ts))

def note(post):
    """-> ('approval', record) | ('ruling', (case, text, ts)) | None for one Clerk post."""
    msg = post["message"].strip(); m = CARD.match(msg)
    if m:
        who = CHOSEN.search(msg); return "approval", {"id": post["id"], "ts": max(post["create_at"], post.get("update_at", 0)) / 1000, "request": m.group(2), "decision": m.group(1), "what": m.group(3).strip(), "by": who.group(1) if who else "unknown"}
    m = RULING.match(post["message"].strip())
    if m: return "ruling", (m.group(2), m.group(1), post["create_at"] / 1000)

def chair(): return os.environ.get("MM_CHAIR_USER", "chargenurse")

# Strict request-text patterns. The card text is written by the Clerk model, so a pattern must not match a card that names another case, mixes a plan with the board, or merely contains a word like "dashboard".
def plan_pattern(n): return rf"^(?!.*\bboard\b)(?!.*\bcase (?!{n}\b)[1-9]\b)(?=.*\bplan\b).*\bcase {n}\b"
BOARD_PATTERN = r"^(?!.*\bplan\b)(?!.*\bcase [1-9]\b).*\bboard\b"

def signed(d, pattern, after, wait=0, who=None):
    """The newest approval whose request text matches `pattern` -> that record only if it is an `Allow once` that `who` (default: the chair) chose, decided at or after `after` (epoch s), else None.
    Signing needs this: --approved alone proves nothing. `wait` (seconds): the Clerk's command can start within a second of the click, before the
    recorder's next poll has logged the Allow, so a signing caller waits up to that long for it to appear (a Decline or a missing Allow still ends in None)."""
    who = who or chair(); end = time.time() + wait
    while True:
        hits = sorted((a for a in approvals(d) if re.search(pattern, a.get("what", ""), re.I | re.S)), key=lambda a: a["ts"])
        ok = hits[-1] if hits and hits[-1]["decision"] == "Allow once" and hits[-1].get("by") == who and hits[-1]["ts"] >= after else None
        if ok or time.time() >= end: return ok
        time.sleep(0.5)
