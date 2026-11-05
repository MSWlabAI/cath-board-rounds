#!/usr/bin/env python3
"""Live generalisation check: run scenarios.md patients through the room's agents and score each brief against flags DERIVED from that packet
(a CCTA lesion of 50% or more, a positive stress result, EF 40% or lower), not from fixed answers. Needs the live room (MM_* env). usage: scenarios_live.py [CASE ...]"""
import os, re, sys
HERE = os.path.dirname(os.path.realpath(__file__)); os.environ["DAY_FILE"] = os.path.join(HERE, "..", "scenarios.md"); sys.path.insert(0, HERE)
import board, check, plan
def expected(case):
    pre = plan.precath(plan.packet(case)); fl = []
    if any(int(re.search(r"\d+", c["pct"]).group()) >= 50 for c in pre["cta"]): fl.append("CCTA")
    if pre["stress"] == "positive": fl.append("stress")
    if pre["ef"] is not None and pre["ef"] <= 40: fl.append("EF")
    return {"imaging": {"flag": fl, **({"none": True} if not fl else {})}, "labs": {"none": True}, "meds": {"none": True}, "equipment": {"none": True}}
def main(cases):
    bad = 0
    for c in cases:
        check.EXP[c] = expected(c); res = board.collect(c)
        for a, r in res.items():
            miss, fmt = check.score(c, a, r[1]) if r else (["timeout"], []); bad += bool(miss)
            print(f"scenario {c} {a:9} {'MISS ' + '; '.join(miss) if miss else 'ok'}{'  [format: ' + '; '.join(fmt) + ']' if fmt else ''}")
    print("SCENARIOS LIVE", "OK" if not bad else f"{bad} MISS"); return 1 if bad else 0
if __name__ == "__main__": sys.exit(main(sys.argv[1:] or ["1", "2", "3", "4", "5", "6", "7"]))
