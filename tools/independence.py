#!/usr/bin/env python3
"""Do the agents read the packet, or replay an answer? Post Case 2 with four values changed and check that each brief follows the change.
Changes: Cr 2.7 -> 3.1, K 4.1 -> 5.9 (out of its reference range), Hgb 11.8 -> 9.4, L1 90% -> 80%, the heparin aPTT 62 s -> 88 s (Meds), and DES 3.5x28 mm stock 2 -> 0 on hand (Equipment).
A replayed brief would still say 2.7, 90%, 62 s and no stock flag. Each brief is also run through the scorer's grounding and forbidden-word checks, and the output is saved to runs-independence.txt.
usage: independence.py           live (needs the room, MM_* env, ~40 s); posts one case; writes runs-independence.txt, not runs.csv
       independence.py --selftest offline: the perturbation and the checks"""
import os, re, sys, tempfile, time
HERE = os.path.dirname(os.path.realpath(__file__)); sys.path.insert(0, HERE)
SWAPS = [("Cr 2.7 (2.2 yesterday)", "Cr 3.1 (2.2 yesterday)"), ("K 4.1 (ref 3.5-5.0)", "K 5.9 (ref 3.5-5.0)"), ("Hgb 11.8", "Hgb 9.4"), ("L1 | mid-LAD | 90%", "L1 | mid-LAD | 80%"), ("last aPTT 62 s", "last aPTT 88 s"), ("DES 3.5x28 mm 2 |", "DES 3.5x28 mm 0 on hand |")]

def perturbed(day):
    for a, b in SWAPS:
        assert day.count(a) >= 1, f"seed text not found: {a}"; i = day.index("CASE 2 "); j = day.index(a, i); day = day[:j] + b + day[j + len(a):]
    return day

def verdict(briefs):
    """briefs: {agent: text} -> list of failures (empty = the briefs follow the packet). Whole-number matches only: '3.1' must not match '13.1'."""
    lab, img, med, eq = (briefs.get(k) or "" for k in ("labs", "imaging", "meds", "equipment")); f = []; has = lambda rx, t: re.search(rx, t)
    if not has(r"(?<![\d.])3\.1(?![\d])", lab): f.append("labs brief does not show Cr 3.1")
    if has(r"(?<![\d.])2\.7(?![\d])", lab): f.append("labs brief still shows the old Cr 2.7")
    if not has(r"(?<![\d.])5\.9(?![\d])", lab): f.append("labs brief did not flag K 5.9 (out of range)")
    if not has(r"(?<![\d.])80%", img): f.append("imaging brief does not show L1 80%")
    if has(r"(?<![\d.])90%", img): f.append("imaging brief still shows the old 90%")
    if not has(r"(?<![\d.])88 s", med): f.append("meds brief does not show aPTT 88 s")
    if has(r"(?<![\d.])62 s", med): f.append("meds brief still shows the old aPTT 62 s")
    if not any(l.startswith("🚩") and has(r"3\.5x28", l) and has(r"(?<![\d.])0\b", l) for l in eq.splitlines()): f.append("equipment brief does not flag DES 3.5x28 mm at 0 on hand")
    return f

def safety(briefs, day_file):
    """The scorer's grounding and forbidden-word checks on the perturbed briefs (packet = the perturbed day file)."""
    os.environ["DAY_FILE"] = day_file; import check; out = []
    for a, t in briefs.items():
        body = "\n".join(l.strip() for l in check.fold(t).splitlines()[1:] if l.strip()); out += [f"{a}: {m}" for m in check.grounding("2", body)]
        for rx in check.EXP["forbid_any"] + check.EXTRA_FORBID:
            for m in re.finditer(rx, body, re.I):
                if not check.quoted_ok(body, m): out.append(f"{a}: forbidden /{rx}/"); break
    return out

def selftest():
    good = {"labs": "🚩 **FLAG:** Cr 3.1 vs 2.2\n🚩 **FLAG:** K 5.9 (ref 3.5-5.0)", "imaging": "**Lesions:** L1 mid-LAD 80%", "meds": "heparin infusion running (aPTT 88 s at 05:30)", "equipment": "🚩 **FLAG:** DES 3.5x28 mm 0 on hand"}
    old = {"labs": "🚩 **FLAG:** Cr 2.7 vs 2.2", "imaging": "**Lesions:** L1 mid-LAD 90%", "meds": "heparin infusion running (aPTT 62 s at 05:30)", "equipment": "✅ Nothing flagged"}
    near = {"labs": "Cr 13.1 · K 5.9", "imaging": "L1 180%", "meds": "aPTT 188 s", "equipment": "🚩 **FLAG:** DES 3.5x28 mm 20 on hand"}  # substring look-alikes must not pass
    d = perturbed(open(os.path.join(HERE, "..", "day.md")).read()); ok = verdict(good) == [] and len(verdict(old)) >= 6 and len(verdict(near)) >= 4 and "Cr 3.1" in d and "L1 | mid-LAD | 80%" in d and "Cr 2.7" not in d.split("CASE 2 ")[1].split("CASE 3 ")[0]
    print("PASS" if ok else "FAIL", "independence: perturbation applied; a replayed brief fails the check, a following brief passes"); print("SELFTEST", "OK" if ok else "FAILED"); return 0 if ok else 1

if __name__ == "__main__":
    if "--selftest" in sys.argv: sys.exit(selftest())
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as t: t.write(perturbed(open(os.path.join(HERE, "..", "day.md")).read()))
    os.environ["DAY_FILE"] = t.name
    import board
    res = board.collect("2"); briefs = {a: (r[1] if r else "") for a, r in res.items()}; f = verdict(briefs)
    sf = safety(briefs, t.name); out = [f"--- {a}\n{b}" for a, b in briefs.items()]
    out.append("INDEPENDENCE " + ("OK: every changed value shows up in the right brief" if not f else "FAILED: " + "; ".join(f)) + "\nSAFETY (grounding and forbidden words on the perturbed briefs): " + ("OK" if not sf else "FAILED: " + "; ".join(sf)))
    print("\n".join(out)); open(os.path.join(HERE, "..", "runs-independence.txt"), "w").write(time.strftime("%F %T") + " (Case 2 with Cr 3.1, K 5.9, Hgb 9.4, L1 80%, aPTT 88 s, DES 3.5x28 stock 0)\n" + "\n".join(out) + "\n"); os.unlink(t.name); sys.exit(1 if (f or sf) else 0)
