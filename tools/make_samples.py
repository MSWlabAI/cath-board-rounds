#!/usr/bin/env python3
"""Rebuild every file in examples/ from stored fixtures, so no sample depends on whatever sits in briefs/ at the time.
Fixtures: examples/briefs-*.md (day 1, kept in the repo) and the day-2 briefs, taken from runs-day2b.csv (the last live run) and written to examples/briefs-day2-case-N.md.
The 'approved' sample is an illustration made through the library (plan.write(approved=True)); a real signature needs a recorded Allow (plan.py refuses otherwise).
usage: make_samples.py [--no-pdf]"""
import csv, os, re, sys
HERE = os.path.dirname(os.path.realpath(__file__)); ROOT = os.path.join(HERE, ".."); EX = os.path.join(ROOT, "examples"); sys.path.insert(0, HERE)
SPLIT = re.compile(r"\s\|\s(?=\*\*|🚩|✅|🔁|MISSING)")

def day2_fixtures():
    rows = list(csv.DictReader(open(os.path.join(ROOT, "runs-day2b.csv")))); last = max(r["run"] for r in rows)
    for c in "345":
        t = "\n".join(re.sub(r"^\s*(?:@\w+\s+)+", "", SPLIT.sub("\n", r["brief"])).strip() for a in ("imaging", "labs", "meds", "equipment") for r in rows if r["run"] == last and r["case"] == c and r["agent"] == a)
        open(os.path.join(EX, f"briefs-day2-case-{c}.md"), "w").write(t + "\n")

def main(pdf=True):
    day2_fixtures(); import plan, tempfile, time
    plan.SIGNED_AT = time.mktime((2026, 11, 4, 9, 0, 0, 0, 0, -1))  # a fixed Allow time, so the signed sample is reproducible
    os.environ["RECORDS_DIR"] = tempfile.mkdtemp()  # an empty records folder: samples never pick up the live room's rulings or approvals
    jobs = [("briefs-case-2.md", "2", "day.md", "plan-case-2-draft-sample", False), ("briefs-case-2.md", "2", "day.md", "plan-case-2-approved-sample", True),
            ("briefs-case-4-precath.md", "4", "day.md", "plan-case-4-precath-sample", False),
            ("briefs-day2-case-3.md", "3", "day2.md", "day2-plan-case-3-sample", False), ("briefs-day2-case-4.md", "4", "day2.md", "day2-plan-case-4-precath-sample", False), ("briefs-day2-case-5.md", "5", "day2.md", "day2-plan-case-5-sample", False)]
    tmp = os.path.join(EX, ".build")
    for fx, case, day, name, appr in jobs:
        os.environ["DAY_FILE"] = os.path.join(ROOT, day)
        p, files, err = plan.write(case, open(os.path.join(EX, fx)).read(), tmp, pdf, appr)
        for ext in (".md", ".pdf"):
            src = os.path.join(tmp, f"plan-case-{case}{ext}")
            if os.path.exists(src): os.replace(src, os.path.join(EX, name + ext))
        print(name, "ERR " + err if err else "ok", "missing:" + ",".join(p["missing"]) if p["missing"] else "")
    for f in os.listdir(tmp): os.remove(os.path.join(tmp, f))
    os.rmdir(tmp)
if __name__ == "__main__":
    if {"-h", "--help"} & set(sys.argv): print(__doc__); sys.exit(0)
    main("--no-pdf" not in sys.argv)
