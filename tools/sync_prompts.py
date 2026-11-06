#!/usr/bin/env python3
"""Keep every copy of the agent prompts identical to template.yaml (the single source).
usage: sync_prompts.py [--agents-dir DIR] [--write] [--console]
  default   check only: DRIFT lines + SHA-256 per prompt (the freeze list); exit 1 on drift or on a template this tool cannot parse
  --write   also (re)write each agent folder's CLAUDE.md (+AGENTS.md for Cursor agents) and the import copies in the agents dir
  --console also compare each prompt with the copy the Switch Console stored when the template was imported (newest record per agent)"""
import glob, hashlib, json, os, re, sys
ROOT = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..")
CONSOLE = os.path.expanduser("~/Library/Application Support/switchdash/agent-controller/servers/*/watchers/*/config.json")

def agents(t):
    """-> [(name, folder, provider, prompt)]; exits loudly if an agent block cannot be parsed (never skips one silently)."""
    names = re.findall(r"^  ([\w-]+):\n    type: agent\n", t, re.M); out = []
    for m in re.finditer(r"^  ([\w-]+):\n    type: agent\n(.*?)(?=^  [\w-]+:\n    type: |^  room:|\Z)", t, re.S | re.M):
        blk = m.group(2); d = re.search(r'directory: "\{\$agents_dir\}/([\w-]+)"', blk); prov = re.search(r"provider: (\w+)", blk)
        if not (d and prov and "    instructions: |\n" in blk): sys.exit(f"cannot parse agent '{m.group(1)}' in template.yaml (needs a quoted directory, a provider, and `instructions: |`)")
        lines = blk.split("    instructions: |\n", 1)[1].splitlines(); bad = [l for l in lines if l.strip() and not l.startswith("      ")]
        if bad: sys.exit(f"agent '{m.group(1)}': instruction lines must be indented 6 spaces: {bad[0][:40]!r}")
        out.append((m.group(1), d.group(1), prov.group(1), "\n".join(l[6:] for l in lines).strip() + "\n"))
    if len(out) != len(names): sys.exit(f"parsed {len(out)} agents but template.yaml declares {len(names)}")
    return out

def console_prompts():
    best = {}
    for f in glob.glob(CONSOLE):
        try: d = json.load(open(f)); i = d.get("start", {}).get("input", {}); n = i.get("agentName"); p = i.get("agentDefinition", {}).get("prompt")
        except Exception: continue
        if n and p and (n not in best or os.path.getmtime(f) > best[n][0]): best[n] = (os.path.getmtime(f), p.strip() + "\n")
    return {n: v[1] for n, v in best.items()}

def main(a):
    adir = os.path.expanduser(a[a.index("--agents-dir") + 1] if "--agents-dir" in a else "~/agents"); t = open(os.path.join(ROOT, "template.yaml")).read(); bad = 0
    con = console_prompts() if "--console" in a else {}
    for name, d, prov, txt in agents(t):
        files = [os.path.join(adir, d, "CLAUDE.md")] + ([os.path.join(adir, d, "AGENTS.md")] if prov == "cursor" else [])
        for f in files:
            cur = open(f).read() if os.path.exists(f) else ""
            if cur != txt:
                if "--write" in a: os.makedirs(os.path.dirname(f), exist_ok=True); open(f, "w").write(txt); print("wrote", f)
                else: print("DRIFT", f); bad = 1
        if "--console" in a and prov == "claude":
            if name not in con: print(f"DRIFT console: no stored record for '{name}'"); bad = 1
            elif con[name] != txt: print(f"DRIFT console: stored prompt for '{name}' differs from template.yaml ({len(con[name])} vs {len(txt)} chars): re-import the template"); bad = 1
        print(f"{hashlib.sha256(txt.encode()).hexdigest()[:16]}  {name:10} {prov:7} {len(txt)} chars")
    if "--write" in a:
        for out in ("template.local.yaml", "cath-board-rounds-claude.yaml", "cath-board-rounds-final.yaml"): open(os.path.join(adir, out), "w").write(t.replace("{$agents_dir}", adir))
    else:  # check mode also compares the import copies, so a stale yaml cannot be re-imported by accident
        for out in ("cath-board-rounds-claude.yaml", "cath-board-rounds-final.yaml"):
            f = os.path.join(adir, out)
            if os.path.exists(f) and open(f).read() != t.replace("{$agents_dir}", adir): print(f"DRIFT import copy: {out} differs from template.yaml (run with --write)"); bad = 1
    return bad
if __name__ == "__main__": sys.exit(main(sys.argv[1:]))
