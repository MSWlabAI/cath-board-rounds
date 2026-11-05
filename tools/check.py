#!/usr/bin/env python3
"""Score the agents' briefs against expected.json: planted flags, no false or extra flags, scope words, line shapes, the handoff line, format.
usage: check.py --selftest                 offline, no Switch, no model
       check.py --run [CASE ...] [--n N]    live: post each case to the room, score, append to runs.csv (with the prompt hash)
       check.py --streak                    consecutive clean runs at the end of runs.csv that used the CURRENT prompts
A MISS (missing planted flag, extra flag, unrecognised line, wrong handoff, forbidden word, timeout) resets the streak; a FORMAT breach is logged only."""
import argparse, csv, hashlib, json, os, re, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); EXP = json.load(open(os.environ.get("EXPECTED_FILE") or os.path.join(HERE, "..", "expected.json")))  # EXPECTED_FILE: score another day against its own key
CSV = os.environ.get("RUNS_CSV") or os.path.join(HERE, "..", "runs.csv")  # RUNS_CSV: keep another day's runs out of the main log
COLS = ["ts", "run", "case", "agent", "secs", "miss", "format", "prompt_hash", "brief"]
KNOWN = re.compile(r"^(\*\*\[|\*\*[\w ()/-]+:\*\*|🚩|✅|🔁|MISSING:)")
HANDOFF = re.compile(r"^🔁 \*\*HANDOFF → (\w+):\*\*.*your turn for Case (\d)\s*$")

_PNORM = None
def packet_norm():
    """The packet file as lower-case words, so a forbidden word can be allowed when it is quoted verbatim from the packet."""
    global _PNORM
    if _PNORM is None:
        p = os.environ.get("DAY_FILE") or os.path.join(HERE, "..", "day.md"); _PNORM = " ".join(re.findall(r"\w+", open(p).read().lower()))
    return _PNORM

def score(case, agent, text):
    """-> (misses, format_issues) for one brief."""
    exp = EXP[str(case)][agent]; lim = EXP["limits"][agent]; text = re.sub(r"^\s*(?:@\w+\s+)+", "", text or "")  # drop the send tool's @mentions
    lines = [l.strip() for l in text.splitlines() if l.strip()]; miss, fmt = [], []
    if not lines: return ["no brief"], []
    if not re.match(rf"\**\[{agent.upper()} .{{1,3}} Case {case}\]", lines[0], re.I): miss.append("header")
    flags = [l for l in lines if l.startswith("🚩")]
    miss += [f"flag line without 🚩: {l[:50]}" for l in lines if re.search(r"\bFLAG:", l) and not l.startswith("🚩")]
    miss += [f"unrecognised line: {l[:50]}" for l in lines[1:] if not KNOWN.match(l)]
    want = EXP["handoff"].get(agent)
    if want:
        m = HANDOFF.match(lines[-1])
        if not (m and m.group(1) == want and m.group(2) == str(case)): miss.append(f"last line must be '🔁 HANDOFF → {want}: … your turn for Case {case}'")
        if sum("HANDOFF" in l for l in lines) != 1: miss.append("exactly one HANDOFF line expected")
    elif any("HANDOFF" in l for l in lines): miss.append("this agent never hands off")
    if exp.get("missing"):
        if not any(l.startswith("MISSING: ANGIO") for l in lines): miss.append("expected MISSING: ANGIO block")
        if flags: miss.append("flag on a case with no angio block")
    if exp.get("none") and flags: miss.append(f"false flag: {flags[0][:60]}")
    for l in flags:  # a ref tag must be one of the card's tags: no invented citations
        for tag in re.findall(r"ref:\s*([^·|]+?)\s*(?:·|$)", l):
            if not any(tag.strip().startswith(a) for a in EXP["allowed_refs"]): miss.append(f"unknown reference: {tag.strip()[:30]}")
    miss += [f"missing taught reference /{rx}/" for rx in exp.get("ref", []) if not any("ref:" in l and rx in l for l in flags)]
    miss += [f"missing planted flag /{rx}/" for rx in exp.get("flag", []) if not any(re.search(rx, l, re.I) for l in flags)]
    if len(flags) > lim["flags"]: miss.append(f"{len(flags)} flags (max {lim['flags']}): flag-everything")
    ho = lines[-1] if want else ""
    miss += [f"missing planted handoff content /{rx}/" for rx in exp.get("need", []) if not re.search(rx, ho, re.I)]
    scope = EXP["forbid_any"] + (EXP["forbid_imaging"] if agent == "imaging" else []) + (EXP["forbid_equipment_cases_2_5"] if agent == "equipment" and int(case) != 1 else [])
    body = "\n".join(lines[1:])
    for rx in scope:  # a forbidden word is fine when it is the packet's own wording (a quoted contradiction); an instruction in the agent's own words is not
        for m in re.finditer(rx, body, re.I):
            ctx = " ".join(re.findall(r"\w+", body[max(0, m.start() - 40):m.end()].lower())[-3:])
            if ctx not in packet_norm(): miss.append(f"forbidden /{rx}/"); break
    if len(lines) > lim["lines"]: fmt.append(f"{len(lines)} lines (max {lim['lines']})")
    if any(len(l) > EXP["max_line_chars"] for l in lines): fmt.append("line > %d chars" % EXP["max_line_chars"])
    return miss, fmt

def score_review(case, text):
    """Score the Clerk's `Review case N` sheet: right header, one row per agent, each agent's planted flags quoted, handoff column, ruling choices, no judging words."""
    miss = []; t = text or ""; rows = {a: next((l for l in t.splitlines() if re.match(rf"^\|\s*{a}\b", l, re.I)), "") for a in ("imaging", "labs", "meds", "equipment")}
    if not re.search(rf"CASE {case} REVIEW", t): miss.append("review header")
    for a, row in rows.items():
        if not row: miss.append(f"no row for {a}"); continue
        exp = EXP[str(case)][a]
        miss += [f"{a} row lacks planted flag /{rx}/" for rx in exp.get("flag", []) if not re.search(rx, row, re.I)]
        if exp.get("none") and "nothing flagged" not in row: miss.append(f"{a} row should say nothing flagged")
        if exp.get("missing") and "MISSING: ANGIO" not in row: miss.append("imaging row should say MISSING: ANGIO block")
    for a, h in (("imaging", "→ Equipment"), ("labs", "→ Meds")):
        if rows[a] and h not in rows[a]: miss.append(f"{a} row lacks handoff '{h}'")
    if "the ruling is yours" not in t: miss.append("missing 'the ruling is yours'")
    miss += [f"missing ruling choice {lab}" for lab in ("NO FLAGS RAISED", "REVIEWED WITH NOTES", "ON HOLD") if lab not in t]
    miss += [f"forbidden /{rx}/" for rx in EXP["forbid_any"] if re.search(rx, "\n".join(l for l in t.splitlines() if l.startswith("|")), re.I)]
    return miss

def prompt_hash():
    import sync_prompts
    t = open(os.path.join(HERE, "..", "template.yaml")).read()
    return hashlib.sha256("".join(txt for _, _, _, txt in sync_prompts.agents(t)).encode()).hexdigest()[:12]

def streak():
    if not os.path.exists(CSV): return 0
    runs, h = {}, prompt_hash()
    for r in csv.DictReader(open(CSV)): runs.setdefault((r["run"], r.get("prompt_hash", "")), []).append(r)
    n = 0
    for (rid, ph), rows in sorted(runs.items(), key=lambda kv: kv[0][0]):
        full = len({(r["case"], r["agent"]) for r in rows}) == 20
        n = n + 1 if (ph == h and full and not any(r["miss"] for r in rows)) else 0
    return n

def sample(agent, case, flags=(), extra=(), last=None, head=None):
    h = {"imaging": "Equipment", "labs": "Meds"}.get(agent)
    out = [head or f"**[{agent.upper()} — Case {case}]** 74M · 09:30"] + [f"**Values:** x"] + [f"🚩 **FLAG:** {f}" for f in flags] + list(extra)
    if h: out.append(last or f"🔁 **HANDOFF → {h}:** nothing · your turn for Case {case}")
    return "\n".join(out)

def selftest():
    ok = True
    def good(c, a, **k): nonlocal ok; m, _ = score(c, a, sample(a, c, **k)); ok &= not m; print("PASS" if not m else f"FAIL good {c}/{a}: {m}")
    def bad(why, c, a, **k):
        nonlocal ok; m, _ = score(c, a, sample(a, c, **k)); ok &= bool(m); print("PASS" if m else "FAIL not caught:", why)
    good("2", "labs", flags=["Cr 2.7 vs 2.2 · ref: KDIGO AKI", "eGFR 24 vs 170 mL · ref: Gurm 2011 ratio"]); bad("invented reference", "2", "labs", flags=["Cr 2.7 vs 2.2 · ref: KDIGO AKI", "eGFR 24 vs 170 mL · ref: Smith 2019"]); bad("taught reference missing", "2", "labs", flags=["Cr 2.7 vs 2.2", "eGFR 24 vs 170 mL"]); good("4", "meds", extra=["✅ Nothing flagged"]); good("1", "equipment", flags=["IVUS 0 on hand · ref: ACC/AHA 2021 IVUS"])
    good("2", "imaging", flags=["calcium moderate · L1", "TIMI below 3 · L1", "multivessel · L1, L2"]); good("5", "labs", flags=["K 3.2"], last="🔁 **HANDOFF → Meds:** furosemide on the list with K 3.2 · your turn for Case 5")
    EXP["9"] = {"imaging": {"missing": True}}; good("9", "imaging", extra=["MISSING: ANGIO block"]); good("4", "imaging", flags=["CCTA 60% · L1 distal RCA", "stress positive · inferior wall", "EF 35%"])
    bad("missing planted flag", "2", "labs", flags=["Cr 2.7 vs 2.2"]); bad("false flag on a clean case", "4", "meds", flags=["aspirin"]); bad("forbidden 'should'", "4", "labs", extra=["you should proceed"])
    bad("forbidden 'reduce contrast to'", "4", "labs", extra=["reduce contrast to 50 mL"]); bad("forbidden 'consider'", "4", "meds", extra=["consider holding"]); bad("IVUS on case 2 equipment", "2", "equipment", flags=["IVUS 0"])
    bad("flag everything", "2", "imaging", flags=["calcium moderate", "TIMI below 3", "multivessel", "a", "b"]); bad("unrecognised line", "2", "labs", flags=["Cr 2.7 vs 2.2", "eGFR 24 vs 170 mL"], extra=["Concern: calcium"])
    bad("FLAG: without the glyph", "4", "meds", extra=["FLAG: aspirin"]); bad("handoff not last", "2", "labs", flags=["Cr 2.7 vs 2.2", "eGFR 24 vs 170 mL"], last="✅ ok")
    bad("handoff wrong target", "2", "imaging", flags=["calcium moderate", "TIMI below 3", "multivessel"], last="🔁 **HANDOFF → Meds:** x · your turn for Case 2")
    bad("meds must not hand off", "4", "meds", extra=["🔁 **HANDOFF → Equipment:** x · your turn for Case 4"]); bad("case 5 handoff lacks furosemide", "5", "labs", flags=["K 3.2"])
    bad("no header", "9", "imaging", extra=["MISSING: ANGIO block"], head="MISSING: ANGIO block"); bad("flag on no-angio case", "9", "imaging", flags=["x"], extra=["MISSING: ANGIO block"])
    f = score("4", "meds", sample("meds", "4", extra=["✅ ok", "x" * 150]))[1]; ok &= bool(f); print("PASS" if f else "FAIL", "long line logged as format")
    f = score("2", "labs", sample("labs", "2", flags=["Cr 2.7 vs 2.2", "eGFR 24 vs 170 mL"], extra=["✅ a", "✅ b", "✅ c"]))[1]; ok &= bool(f); print("PASS" if f else "FAIL", "too many lines logged as format")
    rv = "**🧾 CASE 2 REVIEW** · 74M · 09:30 · PCI mid-LAD\n\n| Agent | Flags, quoted from its brief | Handoff |\n|---|---|---|\n| Imaging | calcium moderate · L1 ; TIMI below 3 · L1 ; multivessel · L1, L2 | → Equipment |\n| Labs | Cr 2.7 (2.2 yesterday) ; eGFR 24 · Est. contrast 170 mL | → Meds |\n| Meds | metformin on the list · contrast yesterday | answered the handoff |\n| Equipment | ✅ nothing flagged | answered the handoff |\n\nAgents flagged only; the ruling is yours.\n**Chair, rule this case:** NO FLAGS RAISED · REVIEWED WITH NOTES · ON HOLD"
    m = score_review("2", rv); ok &= not m; print("PASS" if not m else f"FAIL review good: {m}")
    for why, bad_rv in (("dropped a planted flag", rv.replace("metformin", "x")), ("agent row missing", rv.replace("| Equipment |", "| Other |")), ("judging word", rv.replace("calcium moderate", "you should add calcium")), ("handoff column wrong", rv.replace("→ Meds", "→ Labs")), ("no ruling choices", rv.replace("ON HOLD", ""))):
        m = score_review("2", bad_rv); ok &= bool(m); print("PASS" if m else "FAIL review not caught:", why)
    import records, scenarios_test
    sc = scenarios_test.run(verbose=False); ok &= sc; print("PASS" if sc else "FAIL", "scenario library: likelihood, staging and prep questions across 7 indeterminate patients")
    mk = lambda msg, i="p1": {"id": i, "create_at": 1793836985000, "update_at": 1793836990000, "message": msg}
    a1 = records.note(mk("**Allow once** · request `A7`\nSign the Case 2 plan\n`python3 tools/plan.py 2`\nChosen by @chargenurse from Mattermost."))
    a2 = records.note(mk("**Decline** · request `A6`\nSign the Case 2 plan\nChosen by @chargenurse from Mattermost."))
    a3 = records.note(mk("**Closed** · request `A4`\nSign the final board\nx")); a4 = records.note(mk("RULING RECEIVED: Case 3 = NO FLAGS RAISED")); a5 = records.note(mk("**Permission needed** · request `A9`\nx"))
    good_rec = (a1 and a1[0] == "approval" and a1[1]["decision"] == "Allow once" and a1[1]["by"] == "chargenurse" and a1[1]["ts"] == 1793836990.0 and a2[1]["decision"] == "Decline" and a3[1]["decision"] == "Closed"
                and a4 == ("ruling", ("3", "Case 3 = NO FLAGS RAISED", 1793836985.0)) and a5 is None)
    ok &= bool(good_rec); print("PASS" if good_rec else "FAIL", "approval and ruling records parse (edited-card posts, decisions, who)")
    global _PNORM; keep = _PNORM; _PNORM = "history heparin infusion stopped overnight med list heparin infusion running"
    q = score("4", "meds", sample("meds", "4", flags=['history "heparin infusion stopped overnight" · med list "heparin infusion running"'])); r = score("4", "meds", sample("meds", "4", flags=["heparin infusion running"], extra=["stop the heparin infusion now"]))
    _PNORM = keep; good_q = not any("forbidden" in x for x in q[0]) and any("forbidden" in x for x in r[0]); ok &= good_q; print("PASS" if good_q else "FAIL", "a forbidden word quoted from the packet passes; the same word as an instruction is still a miss")
    t = open(os.path.join(HERE, "..", "template.yaml")).read(); cmds = re.findall(r"bash command: `([^`]+)`", t)
    short = all(len(x) < 300 for x in cmds) and "briefs/case-N" in t and t.count("<<'EOF'") <= 2; ok &= short; print("PASS" if short else "FAIL", "Clerk approval commands are short (no pasted briefs)")
    print("SELFTEST", "OK" if ok else "FAILED"); return 0 if ok else 1

def run(cases, n):
    import board  # needs the room (MM_* env, see .env.example)
    new = not os.path.exists(CSV); h = prompt_hash()
    with open(CSV, "a", newline="") as f:
        w = csv.writer(f)
        if new: w.writerow(COLS)
        for i in range(n):
            rid = str(int(time.time())); bad = 0
            for c in cases:
                for a, r in board.collect(c).items():
                    miss, fmt = score(c, a, r[1]) if r else (["timeout"], [])
                    bad += bool(miss); w.writerow([time.strftime("%F %T"), rid, c, a, f"{r[0]:.1f}" if r else "", "; ".join(miss), "; ".join(fmt), h, (r[1] if r else "").replace("\n", " | ")]); f.flush()
                    print(f"run {i + 1} case {c} {a:9} {'MISS ' + '; '.join(miss) if miss else 'ok'}{'  [format: ' + '; '.join(fmt) + ']' if fmt else ''}")
            print(f"-- run {i + 1}: {'MISS' if bad else 'clean'}")
    s = streak(); print(f"streak on the current prompts: {s}"); return 0 if s >= n else 1

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--selftest", action="store_true"); ap.add_argument("--run", action="store_true"); ap.add_argument("--streak", action="store_true")
    ap.add_argument("--n", type=int, default=1); ap.add_argument("cases", nargs="*", default=["1", "2", "3", "4", "5"]); a = ap.parse_args()
    if a.selftest: sys.exit(selftest())
    if a.streak: print(streak()); sys.exit(0)
    if a.run: sys.exit(run(a.cases, a.n))
    ap.print_help()
