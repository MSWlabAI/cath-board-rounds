#!/usr/bin/env python3
"""Post one case to imaging+labs in a single chair message (the relay then brings in Equipment and Meds) and collect all four briefs.
usage: board.py CASE   (test harness for the chair's './case N imaging labs' paste)"""
import json, re, sys, time
import mm, packet
AGENTS = ("imaging", "labs", "meds", "equipment")   # who must answer
ADDRESSED = ("imaging", "labs")                       # who the chair names; Imaging hands to Equipment, Labs to Meds

def collect(case, agents=AGENTS, limit=150, addressed=ADDRESSED):
    """Post one chair message to all given agents; return {agent: (secs, text) or None}. Interrupts agents that time out."""
    tok = mm.login(); ch = mm.room(tok); t0 = time.time()
    pid = mm.post(tok, ch, packet.message(case, addressed)); got = {}
    heads = {a: re.compile(rf"\s*(@\w+\s+)*\**\[{a.upper()} .{{1,3}} Case {case}\]", re.I) for a in agents}
    while time.time() - t0 < limit and len(got) < len(agents):
        time.sleep(1.5)
        for p in mm.posts_since(tok, ch, t0, {pid}):
            for a in agents:
                if a not in got and heads[a].match(p["message"]): got[a] = (time.time() - t0, p["message"])
    for a in agents:
        if a not in got: mm.post(tok, ch, f"!interrupt @{a}")
    return {a: got.get(a) for a in agents}

def main(case, limit=120):
    res = collect(case, AGENTS, limit)
    for a, r in res.items(): print(f"--- {a} {r[0]:.1f}s\n{r[1]}" if r else f"--- {a} TIMEOUT")
    return 0 if all(res.values()) else 1

if __name__ == "__main__": sys.exit(main(sys.argv[1]))
