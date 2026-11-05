"""Shared Mattermost helpers for the chair-side harness (login, room lookup, post, wait for a reply).
Config comes from the environment (see .env.example); MM_ENV_FILE may point at a KEY=VALUE file."""
import json, os, re, sys, time, urllib.error, urllib.request

def _load_env_file():
    p = os.path.expanduser(os.environ.get("MM_ENV_FILE", ""))
    if p and os.path.exists(p):
        for line in open(p):
            k, _, v = line.strip().partition("=")
            if k and v and not k.startswith("#"): os.environ.setdefault(k, v.strip("\"'"))
_load_env_file()

def need(key):
    return os.environ.get(key) or sys.exit(f"set {key} (see .env.example)")

BASE = os.environ.get("MM_URL", "http://127.0.0.1:8065").rstrip("/") + "/api/v4"
ROOM = os.environ.get("ROOM", "cath-board-rounds")
STATUS = re.compile(r"\*\*(Working|Queued|Turn interrupted|Worked)|(Interrupted|Resetting|I can't reset|Starting a session|Stops what)")

def call(path, body=None, tok=None):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", **({"Authorization": "Bearer " + tok} if tok else {})})
    try: return urllib.request.urlopen(req, timeout=30)
    except urllib.error.HTTPError as e: sys.exit(f"Mattermost {e.code} on {path}: check MM_TEAM / ROOM (a Switch room slug has a random suffix: use the one in the room URL) and the MM_* settings")
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e: sys.exit(f"Mattermost is not reachable at {BASE}: is the container running? ({e})")

def login():
    r = call("/users/login", {"login_id": os.environ.get("MM_CHAIR_USER", "chargenurse"), "password": need("MM_CHAIR_PASSWORD")})
    return r.headers["Token"]

def room(tok):
    team = json.load(call(f"/teams/name/{need('MM_TEAM')}", tok=tok))["id"]
    return json.load(call(f"/teams/{team}/channels/name/{ROOM}", tok=tok))["id"]

def post(tok, ch, msg):
    return json.load(call("/posts", {"channel_id": ch, "message": msg}, tok))["id"]

def user_id(tok, name):
    return json.load(call(f"/users/username/{name}", tok=tok))["id"]

def bare(m):
    return re.sub(r"^\s*(@\w+\s+)+", "", m)  # drop the leading @mention the send tool adds

def posts_since(tok, ch, t0, skip=()):
    """New, non-empty, non-status posts in the room since t0 (oldest first)."""
    d = json.load(call(f"/channels/{ch}/posts?since={int(t0 * 1000) - 1000}", tok=tok))
    return [p for p in sorted(d["posts"].values(), key=lambda x: max(x["create_at"], x.get("update_at", 0)))
            if p["id"] not in skip and max(p["create_at"], p.get("update_at", 0)) >= t0 * 1000 - 500 and p["message"].strip() and not STATUS.match(p["message"])]

def wait(tok, ch, t0, accept, limit=90, skip=()):
    """Poll until accept(post) returns a value; returns (seconds, value) or None on timeout."""
    while time.time() - t0 < limit:
        time.sleep(1.5)
        for p in posts_since(tok, ch, t0, skip):
            hit = accept(p)
            if hit: return time.time() - t0, hit
    return None
