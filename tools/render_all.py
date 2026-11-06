#!/usr/bin/env python3
"""Render an unsigned plan PDF for every case of every day from the stored live briefs (last run on the current prompt hash), to prove plan.py handles all 15 packets.
usage: render_all.py [OUTDIR]   (default /tmp/plans-all; needs Google Chrome for the PDFs)"""
import csv, os, re, sys, tempfile
HERE = os.path.dirname(os.path.realpath(__file__)); ROOT = os.path.join(HERE, ".."); sys.path.insert(0, HERE)
SPLIT = re.compile(r"\s\|\s(?=\*\*|🚩|✅|🔁|MISSING)"); AG = ("imaging", "labs", "meds", "equipment")
DAYS = [("day1", "day.md", "runs.csv"), ("day2", "day2.md", "runs-day2c.csv"), ("day3", "day3.md", "runs-day3.csv")]
def briefs(csvf, c):
    rows = list(csv.DictReader(open(os.path.join(ROOT, csvf)))); h = rows[-1]["prompt_hash"]; rows = [r for r in rows if r["prompt_hash"] == h]; last = max(r["run"] for r in rows)
    return "\n".join(re.sub(r"^\s*(?:@\w+\s+)+", "", SPLIT.sub("\n", r["brief"])).strip() for a in AG for r in rows if r["run"] == last and r["case"] == c and r["agent"] == a), h
def main(out):
    os.makedirs(out, exist_ok=True); os.environ["RECORDS_DIR"] = tempfile.mkdtemp(); import plan; bad = 0
    for d, day, csvf in DAYS:
        os.environ["DAY_FILE"] = os.path.join(ROOT, day)
        for c in "12345":
            txt, h = briefs(csvf, c); tmp = os.path.join(out, f"{d}-case-{c}"); os.makedirs(tmp, exist_ok=True)
            try: p, files, err = plan.write(c, txt + "\n", tmp, True, False)
            except Exception as e: p, files, err = {"missing": []}, [], f"EXC {e!r}"
            pdf = os.path.join(tmp, f"plan-case-{c}.pdf"); ok = not err and os.path.exists(pdf) and os.path.getsize(pdf) > 5000
            bad += not ok; print(("ok  " if ok else "FAIL"), d, "case", c, h[:4], f"{os.path.getsize(pdf) // 1024 if os.path.exists(pdf) else 0} KB", ("ERR " + str(err)) if err else "", "missing:" + ",".join(p["missing"]) if p.get("missing") else "")
    print(f"{15 - bad}/15 PDFs written -> {out}"); return bad
if __name__ == "__main__": sys.exit(1 if main(sys.argv[1] if len(sys.argv) > 1 else "/tmp/plans-all") else 0)
