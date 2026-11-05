#!/usr/bin/env python3
"""Do the agents read the packet, or replay an answer? Post Case 2 with four values changed and check that each brief follows the change.
Changes: Cr 2.7 -> 3.1, K 4.1 -> 5.9 (out of its reference range), Hgb 11.8 -> 9.4, L1 90% -> 80%. A replayed brief would still say 2.7 and 90%.
usage: independence.py           live (needs the room, MM_* env, ~40 s); posts one case; logs nothing to runs.csv
       independence.py --selftest offline: the perturbation and the checks"""
import os, re, sys, tempfile
HERE = os.path.dirname(os.path.realpath(__file__)); sys.path.insert(0, HERE)
SWAPS = [("Cr 2.7 (2.2 yesterday)", "Cr 3.1 (2.2 yesterday)"), ("K 4.1 (ref 3.5-5.0)", "K 5.9 (ref 3.5-5.0)"), ("Hgb 11.8", "Hgb 9.4"), ("L1 | mid-LAD | 90%", "L1 | mid-LAD | 80%")]

def perturbed(day):
    for a, b in SWAPS:
        assert day.count(a) >= 1, f"seed text not found: {a}"; i = day.index("CASE 2 "); j = day.index(a, i); day = day[:j] + b + day[j + len(a):]
    return day

def verdict(briefs):
    """briefs: {agent: text} -> list of failures (empty = the briefs follow the packet)."""
    lab, img = briefs.get("labs") or "", briefs.get("imaging") or ""; f = []
    if "3.1" not in lab: f.append("labs brief does not show Cr 3.1")
    if re.search(r"\b2\.7\b", lab): f.append("labs brief still shows the old Cr 2.7")
    if not re.search(r"K 5\.9|5\.9", lab): f.append("labs brief did not flag K 5.9 (out of range)")
    if "80%" not in img: f.append("imaging brief does not show L1 80%")
    if re.search(r"\b90%", img): f.append("imaging brief still shows the old 90%")
    return f

def selftest():
    good = {"labs": "🚩 **FLAG:** Cr 3.1 vs 2.2\n🚩 **FLAG:** K 5.9 (ref 3.5-5.0)", "imaging": "**Lesions:** L1 mid-LAD 80%"}
    old = {"labs": "🚩 **FLAG:** Cr 2.7 vs 2.2", "imaging": "**Lesions:** L1 mid-LAD 90%"}
    d = perturbed(open(os.path.join(HERE, "..", "day.md")).read()); ok = verdict(good) == [] and len(verdict(old)) >= 4 and "Cr 3.1" in d and "L1 | mid-LAD | 80%" in d and "Cr 2.7" not in d.split("CASE 2 ")[1].split("CASE 3 ")[0]
    print("PASS" if ok else "FAIL", "independence: perturbation applied; a replayed brief fails the check, a following brief passes"); print("SELFTEST", "OK" if ok else "FAILED"); return 0 if ok else 1

if __name__ == "__main__":
    if "--selftest" in sys.argv: sys.exit(selftest())
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as t: t.write(perturbed(open(os.path.join(HERE, "..", "day.md")).read()))
    os.environ["DAY_FILE"] = t.name
    import board
    res = board.collect("2"); briefs = {a: (r[1] if r else "") for a, r in res.items()}; f = verdict(briefs)
    for a, b in briefs.items(): print(f"--- {a}\n{b}")
    print("INDEPENDENCE " + ("OK: every changed value shows up in the brief" if not f else "FAILED: " + "; ".join(f))); os.unlink(t.name); sys.exit(1 if f else 0)
