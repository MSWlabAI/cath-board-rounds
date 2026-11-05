#!/usr/bin/env python3
"""Write freeze.txt: SHA-256 of every file that defines behaviour, the per-agent prompt hashes, and tool versions.
Run it once the prompts are final; any later change to a listed file means the 10-in-a-row run restarts. usage: freeze.py [--check]"""
import hashlib, os, subprocess, sys
ROOT = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..")
import glob
FILES = ["template.yaml", "day.md", "expected.json", "thresholds.json", "case", "check.sh"] + sorted("tools/" + os.path.basename(p) for p in glob.glob(os.path.join(ROOT, "tools", "*.py")))
def sh(*c):
    try: return subprocess.run(c, capture_output=True, text=True, timeout=20).stdout.strip().splitlines()[0]
    except Exception: return "unknown"
def user_claude():
    """model and effort the Claude Code room agents inherit (values only, no paths)."""
    try:
        import json; d = json.load(open(os.path.expanduser("~/.claude/settings.json"))); return f"model={d.get('model', 'default')} effort={d.get('effortLevel', d.get('effort', 'default'))}"
    except Exception: return "unknown"

def build():
    L = ["# freeze.txt: sha256 of everything that defines behaviour. Regenerate with tools/freeze.py; a diff means the streak restarts.", ""]
    L += [f"{hashlib.sha256(open(os.path.join(ROOT, f), 'rb').read()).hexdigest()}  {f}" for f in FILES]
    L += ["", "# agent prompts (from template.yaml)"] + subprocess.run([sys.executable, os.path.join(ROOT, "tools", "sync_prompts.py")], capture_output=True, text=True).stdout.strip().splitlines()
    L += ["", "# tools", "claude: " + sh("claude", "--version"), "cursor-agent: " + sh("cursor-agent", "--version"), "python: " + sys.version.split()[0],
          "cursor model (default on this machine): " + (subprocess.run(["cursor-agent", "about"], capture_output=True, text=True).stdout.split("Model")[1].split("\n")[0].strip() if "Model" in subprocess.run(["cursor-agent", "about"], capture_output=True, text=True).stdout else "unknown"),
          "claude room agents inherit the user-level Claude Code settings: " + user_claude()]
    return "\n".join(L) + "\n"
if __name__ == "__main__":
    t = build(); p = os.path.join(ROOT, "freeze.txt")
    if "--check" in sys.argv: sys.exit(0 if os.path.exists(p) and open(p).read().split("# tools")[0] == t.split("# tools")[0] else (print("DRIFT from freeze.txt") or 1))
    open(p, "w").write(t); print(t)
