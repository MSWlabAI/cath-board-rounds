#!/usr/bin/env python3
"""Post one addressed packet to one agent as the chair and time the reply.
usage: ask.py CASE AGENT   (reads day.md; Equipment also gets STOCK). Prints elapsed seconds and the reply."""
import re, sys, time
import mm, packet

def main(case, agent, limit=150):
    tok = mm.login(); ch = mm.room(tok); t0 = time.time()
    pid = mm.post(tok, ch, packet.message(case, agent))
    head = re.compile(rf"\s*(@\w+\s+)*\**\[{agent.upper()} .{{1,3}} Case {case}\]", re.I)
    got = mm.wait(tok, ch, t0, lambda p: p["message"] if head.match(p["message"]) else None, limit, skip={pid})
    if got: print(f"{got[0]:.1f}s\n{got[1]}"); return 0
    mm.post(tok, ch, f"!interrupt @{agent}"); print(f"TIMEOUT {limit}s (interrupted)"); return 1

if __name__ == "__main__": sys.exit(main(sys.argv[1], sys.argv[2]))
