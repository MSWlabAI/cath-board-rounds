#!/usr/bin/env python3
"""Send one message to @clerk as the chair and print the Clerk's next post (author-checked; flags an approval card).
usage: clerk.py "RULING ..."   or   clerk.py "Board draft ..."   or   clerk.py "Board is final ..." """
import sys, time
import mm

def run(msg, limit=90):
    tok = mm.login(); ch = mm.room(tok); clerk = mm.user_id(tok, "clerk"); t0 = time.time()
    pid = mm.post(tok, ch, "@clerk " + msg)
    got = mm.wait(tok, ch, t0, lambda p: p["message"] if p["user_id"] == clerk else None, limit, skip={pid})
    if not got: print(f"TIMEOUT {limit}s"); return 1
    print(f"{got[0]:.1f}s{' CARD' if 'Permission needed' in got[1] else ''}\n{mm.bare(got[1])}")
    if "cannot be answered from this message" in got[1]: print("CARD TOO LONG: no buttons, answerable only in the Console. Shorten the Clerk's command."); return 2
    return 0

if __name__ == "__main__": sys.exit(run(sys.argv[1]))
