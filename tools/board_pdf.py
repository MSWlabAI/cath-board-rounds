#!/usr/bin/env python3
"""Render the Clerk's board (board-final.md, a Markdown table) as a styled PDF. usage: board_pdf.py board-final.md OUT.pdf [--approved]"""
import html, os, re, subprocess, sys
import plan
def render(src, out, approved, extra=""):
    lines = [l for l in open(src).read().splitlines() if l.strip()]
    head = next((l for l in lines if "|" not in l), "BOARD"); rows = [[c.strip() for c in l.strip().strip("|").split("|")] for l in lines if "|" in l and not re.match(r"^[|\-: ]+$", l)]
    e = html.escape; th = "".join(f"<th>{e(c)}</th>" for c in rows[0]); body = "".join("<tr>" + "".join(f"<td>{e(c)}</td>" for c in r) + "</tr>" for r in rows[1:])
    page = f"""<!doctype html><html><head><meta charset=utf-8><title>Board</title><style>{plan.CSS}@page{{size:Letter landscape}}body,html{{width:9.9in}}</style></head><body>
<div class=band><h1>MORNING BOARD · Cath Lab</h1><div class=sub>Planning record · the operator decides</div></div><div class=strip>{e(head)}</div>
<table><tr>{th}</tr>{body}</table>
{extra}<div class=sig><div><b>Chair</b><br><span style="font-size:9pt;color:#556">Rulings are the chair's. Agents only flagged.</span></div><div class="stamp{'' if approved else ' pend'}">{'SIGNED BY CHAIR' if approved else 'DRAFT'}</div></div></body></html>"""
    h = out[:-4] + ".html"; open(h, "w").write(page)
    subprocess.run([plan.CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", f"--print-to-pdf={out}", "file://" + os.path.abspath(h)], capture_output=True, timeout=60); os.remove(h)
if __name__ == "__main__": render(sys.argv[1], sys.argv[2], "--approved" in sys.argv)
