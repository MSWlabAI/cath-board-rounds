#!/usr/bin/env python3
"""Format a day.md case as the chair's message to one agent (label line + packet in a code block).
usage: packet.py CASE AGENT [AGENT ...]   (use: packet.py 2 imaging labs; Imaging hands to Equipment and Labs to Meds)   -> prints the message (and copies it with pbcopy on macOS)"""
import os, re, subprocess, sys
DAY = os.environ.get("DAY_FILE") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "day.md")  # DAY_FILE: run the same tools on scenarios.md

KNOWN = ("imaging", "labs", "meds", "equipment", "clerk")

def message(case, agents):
    agents = [agents] if isinstance(agents, str) else list(agents)
    bad = [a for a in agents if a not in KNOWN]
    if bad: sys.exit(f"unknown agent {bad}: use {', '.join(KNOWN[:4])}")
    day = open(DAY).read()
    m = re.search(rf"^(CASE {case} .*?)(?=\nCASE \d |\n## STOCK)", day, re.S | re.M)
    if not m: sys.exit(f"no CASE {case} in day.md")
    pkt = m.group(1).strip()
    if "imaging" not in agents: pkt = "\n".join(l for l in pkt.splitlines() if not l.startswith(("ANGIO:", "CATH REPORT:", "PRECATH:")))  # imaging findings go only to Imaging
    if "equipment" in agents or "imaging" in agents: pkt += "\nSTOCK: " + day.split("## STOCK")[1].split("\n## ")[0].strip().splitlines()[-1]
    row = re.search(rf"^{case} \| (.*)$", day, re.M).group(1).split(" | ")  # Pt | Procedure | Scheduled
    mention = " ".join("@" + a for a in agents)
    return f"{mention} **Case {case}** · {row[0]} · {row[2]} · {row[1]}\n```\n{pkt}\n```"

DEFAULT_RULINGS = ["Case 1 = REVIEWED WITH NOTES ; IVUS short, ETA 13:00 ; MOVE TO LAST ; operator to confirm", "Case 2 = REVIEWED WITH NOTES ; contrast vs eGFR ; operator to confirm",
                   "Case 3 = REVIEWED WITH NOTES ; apixaban timing vs history ; operator to confirm", "Case 4 = NO FLAGS RAISED", "Case 5 = ON HOLD ; K 3.2 with furosemide ; operator to confirm"]
def draft(rulings=None):
    """The chair's 'Board draft' message: rulings + CASE TABLE + SLOT LIST from day.md (./case draft)."""
    day = open(DAY).read(); tbl = day.split("## CASE TABLE")[1].split("## PACKETS")[0].strip(); slots = day.split("## SLOTS (scheduled)")[1].split("##")[0].strip()
    return "@clerk Board draft\nRULINGS\n" + "\n".join(rulings or DEFAULT_RULINGS) + "\n\nCASE TABLE\n" + tbl + "\n\nSLOT LIST\n" + slots

if __name__ == "__main__":
    if sys.argv[1:2] == ["draft"]:
        m = draft(); print(m)
        if os.environ.get("COPY"):
            try: subprocess.run(["pbcopy"], input=m.encode(), check=True); print("\n(copied to clipboard)", file=sys.stderr)
            except Exception: pass
        sys.exit(0)
    if len(sys.argv) < 3: sys.exit("usage: ./case N imaging labs   |   ./case draft")
    m = message(sys.argv[1], sys.argv[2:] if len(sys.argv) > 3 else sys.argv[2]); print(m)
    if os.environ.get("COPY"):
      try: subprocess.run(["pbcopy"], input=m.encode(), check=True); print("\n(copied to clipboard)", file=sys.stderr)
      except Exception: pass
