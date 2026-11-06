"""Chair-side records the recorder keeps from the room: every approval decision (Allow, Decline, Closed) and the latest ruling per case.
Read by plan.py and board_final.py so the signed PDFs carry a summary with the approvals."""
import json, os, re, time
DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "briefs")
CARD = re.compile(r"^\*\*(Allow once|Allow for this session|Decline|Closed)\*\* · request `(A\d+)`\s*(?:\||\n)\s*([^\n|]*)", re.S)
CHOSEN = re.compile(r"Chosen by @([\w.\-]+) from Mattermost")
RULING = re.compile(r"^@clerk\s+(Case ([1-9]) = [^\n]*)")  # the chair's own post; the Clerk's echo is only an acknowledgement and is never a record

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
    """-> ('approval', record) for one Switch permission-card post by the Clerk account, else None.
    Only a real Switch card counts: Switch tags its card posts with props.switch_publication, which a plain post made by the Clerk's room-post tool cannot carry, so card-shaped text written by the Clerk model is ignored.
    The chair's name is the LAST 'Chosen by @name from Mattermost' (the command text above it is written by the model)."""
    msg = post["message"].strip(); m = CARD.match(msg)
    if not m or not (post.get("props") or {}).get("switch_publication"): return None
    who = CHOSEN.findall(msg)
    return "approval", {"id": post["id"], "ts": max(post["create_at"], post.get("update_at", 0)) / 1000, "request": m.group(2), "decision": m.group(1), "what": m.group(3).strip(), "by": who[-1] if who else "unknown"}

def chair_ruling(post):
    """-> (case, text, ts) for a ruling the CHAIR typed to the Clerk ('@clerk Case N = ...'), else None."""
    m = RULING.match(post["message"].strip())
    return (m.group(2), m.group(1), post["create_at"] / 1000) if m else None


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
