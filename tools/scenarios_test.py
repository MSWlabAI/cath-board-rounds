#!/usr/bin/env python3
"""Offline test of the pre-cath logic across a family of synthetic indeterminate patients (scenarios.md, scenarios-expected.json): likelihood score and band,
which drivers fire, which prep questions appear or stay quiet, and the staging scope. Shows the logic is general, not tuned to one case. usage: scenarios_test.py"""
import json, os, sys
HERE = os.path.dirname(os.path.realpath(__file__)); ROOT = os.path.join(HERE, ".."); os.environ["DAY_FILE"] = os.path.join(ROOT, "scenarios.md")
sys.path.insert(0, HERE); import plan
def run(verbose=True):
    exp = json.load(open(os.path.join(ROOT, "scenarios-expected.json"))); ok = True
    for c, e in exp.items():
        p = plan.build(c, ""); lk = p["lk"]; drivers = " | ".join(d for d, _ in (lk["drivers"] if lk else [])); qs = " | ".join(p["prep"]["questions"]); bad = []
        if not lk or lk["band"] != e["band"] or lk["score"] != e["score"]: bad.append(f"likelihood {lk and (lk['band'], lk['score'])} expected {(e['band'], e['score'])}")
        bad += [f"driver missing: {k}" for k in e.get("drivers", []) if k not in drivers] + [f"driver should not fire: {k}" for k in e.get("drivers_not", []) if k in drivers]
        bad += [f"question missing: {k}" for k in e.get("q_has", []) if k not in qs] + [f"question should be quiet: {k}" for k in e.get("q_not", []) if k in qs]
        if e["scope"] not in p["prep"]["scope"]: bad.append(f"scope {p['prep']['scope']!r} lacks {e['scope']!r}")
        if p["pathway"] != "indeterminate" or p["stage"] != "pre-cath" or len(p["groups"]) != 2: bad.append("pathway, stage or branch groups wrong")
        ok &= not bad
        if verbose: print(("PASS" if not bad else "FAIL"), f"scenario {c}: {lk['band'] if lk else '-'} ({lk['score'] if lk else '-'} pts)", "; ".join(bad))
    return ok
if __name__ == "__main__": sys.exit(0 if run() else 1)
