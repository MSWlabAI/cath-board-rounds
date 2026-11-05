#!/usr/bin/env python3
"""Assemble the CATH PLAN draft for one case: deterministic template, no model. Inputs: day.md packet, thresholds.json,
and the agents' own briefs (--briefs FILE | - | DIR). Outputs plan-case-N.md/.html and, with --pdf, plan-case-N.pdf (headless Chrome).
usage: plan.py CASE [--briefs FILE|-|DIR] [--out DIR] [--pdf] [--approved] [--force]      plan.py --selftest
With --briefs DIR (the Clerk's flow) it refuses stale or mixed-run briefs and a dead room recorder unless --force."""
import glob, hashlib, html, json, os, re, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import records, angio, pk
HERE = os.path.dirname(os.path.realpath(__file__)); ROOT = os.path.join(HERE, "..")
CHROME = os.environ.get("CHROME", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
AGENTS = ("imaging", "labs", "meds", "equipment")
DRAFT = "Synthetic teaching content. Not clinical advice. Not a medical device. DRAFT for the chair to rule on."
SIGNED = "Synthetic teaching content. Not clinical advice. Not a medical device. Approved by the chair on the Switch card; still a planning draft, not an order."
LOGIC = "Template logic is unreviewed: the likelihood point weights and bands, the prep rules, the Imaging trigger set, the Heart Team factor rules, the stage assignment and Labs' eGFR cutoff. Setting verified=true does not cover them."
LOGIC_SHORT = "Template logic (likelihood weights and bands, prep rules, Imaging triggers, Heart Team factors, stage assignment, Labs' eGFR cutoff) is also unreviewed."
MAX_AGE_MIN, MAX_SPREAD_MIN, HEARTBEAT_S = 90, 15, 180

def provenance(case, rec_dir=None):
    """Which inputs produced this plan: short hashes of template/thresholds/plan.py, the data file, and the chair packet id the briefs answer."""
    h = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()[:10] if os.path.exists(p) else "n/a"
    pk_ = {}
    try: pk_ = json.load(open(os.path.join(rec_dir or os.environ.get("RECORDS_DIR") or os.path.join(ROOT, "briefs"), f"packet-{case}.json")))
    except (OSError, ValueError): pass
    day = os.environ.get("DAY_FILE") or os.path.join(ROOT, "day.md")
    return dict(template=h(os.path.join(ROOT, "template.yaml")), thresholds=h(os.path.join(ROOT, "thresholds.json")), plan=h(os.path.realpath(__file__)), day=os.path.basename(day), packet=(pk_.get("id") or "n/a")[:8])

def check(case, d):
    """Everything that would make `Plan case N` refuse, without writing: -> list of problems (empty = ready). Used by --check and by the recorder before the chair presses Allow."""
    text, probs = read_dir(d); probs = list(probs)
    if text:
        have = briefs(text); probs += [f"no brief from {a}" for a in AGENTS if a not in have]
        try: pt = json.load(open(os.path.join(os.path.dirname(os.path.abspath(d)), f"packet-{case}.json")))["ts"]
        except (OSError, ValueError, KeyError): pt = None
        if pt and any(os.path.getmtime(f) < pt - 2 for f in glob.glob(os.path.join(d, "*.md"))): probs.append("a brief is older than the chair's latest packet for this case")
    return probs

def packet(case):
    day = open(os.environ.get("DAY_FILE") or os.path.join(ROOT, "day.md")).read()  # DAY_FILE: run the same logic on the scenario library
    m = re.search(rf"^(CASE {case} .*?)(?=\nCASE \d |\n## STOCK)", day, re.S | re.M)
    if not m: sys.exit(f"no CASE {case} in day.md")
    f = {}
    for l in m.group(1).splitlines()[1:]:
        m2 = re.match(r"^([A-Z][A-Z ]*?)(?: \([^)]*\))?:\s*(.*)$", l)
        if m2: f[m2.group(1)] = m2.group(2).strip()
    f["_head"] = m.group(1).splitlines()[0]; f["_stock"] = day.split("## STOCK")[1].split("\n## ")[0].strip().splitlines()[-1]
    return f

def lesions(f, warn=None):
    out = []; warn = warn if warn is not None else []
    for part in (x for x in re.split(r"\s*;\s*", f.get("ANGIO", "")) if x.strip()):
        c = [x.strip() for x in part.split("|")]
        if len(c) != 6: warn.append(f"ANGIO row not read (expected 6 fields, found {len(c)}): {part[:60]}"); continue
        l = dict(id=c[0], vessel=c[1], pct=c[2], timi=c[3], calcium=c[4], flag=c[5]); out.append(l)
        if pk.pct(l["pct"]) is None: warn.append(f"{l['id']}: stenosis '{l['pct']}' not readable, treated as 0%")
        if pk.timi(l["timi"]) is None: warn.append(f"{l['id']}: TIMI '{l['timi']}' not readable, the TIMI check was skipped for it")
        if not pk.family(l["vessel"]): warn.append(f"{l['id']}: vessel '{l['vessel']}' not recognised, so it is not drawn and not counted for Heart Team factors")
    return out

def triggers(ls):
    t = []
    if any(pk.calc(l["calcium"]) for l in ls): t.append("calcium moderate or severe")
    if any(pk.has_flag(l["flag"]) or pk.is_lm(l["vessel"]) for l in ls): t.append("bifurcation, ostial or left main")
    if any((pk.timi(l["timi"]) if pk.timi(l["timi"]) is not None else 3) < 3 for l in ls): t.append("TIMI flow below 3")
    if len(ls) > 1: t.append("more than one lesion (multivessel)")
    return t

def stock(f):
    """STOCK line -> {device name (lower): (count, note)}. The count is the last integer before 'on hand' or the end: names like 'DES 3.5x28 mm' contain digits."""
    s = {}
    for seg in f["_stock"].split("|"):
        m = re.match(r"^\s*(.*?\S)\s+(\d+)(\s+on hand.*|,.*)?\s*$", seg.strip())
        if m: s[m.group(1).lower()] = (int(m.group(2)), re.sub(r"\s*\(.*?\)", "", re.sub(r"^\s*(on hand)?,?\s*", "", m.group(3) or "")).strip(" ,"))
    return s

def manifest(f): return [r for _, rows in manifest_groups(f) for r in rows]

def precath(f):
    """PRECATH line (indeterminate pathway) -> {cta: [lesion dicts], stress, stress_text, symptoms, symptoms_text} or None."""
    s = f.get("PRECATH")
    if not s: return None
    out = {"cta": [], "stress": "", "stress_text": "", "symptoms": "", "symptoms_text": "", "ef": None}
    for part in (x.strip() for x in s.split(" ; ")):
        if part.startswith("CCTA "):
            c = [x.strip() for x in part[5:].split("|")]
            if len(c) == 4: out["cta"].append(dict(id=c[0], vessel=c[1], pct=c[2], timi="TIMI n/a", calcium=c[3], flag="none", cta=True))
        elif part.startswith("STRESS "):
            out["stress_text"] = part[7:].lstrip(": "); first = re.search(r"\b(positive|equivocal|negative)\b", out["stress_text"], re.I); out["stress"] = first.group(1).lower() if first else ""
        elif re.match(r"(LV)?EF\b", part, re.I): out["ef"] = pk.ef(part)
        elif part.startswith("SYMPTOMS "): out["symptoms_text"] = part[9:]; out["symptoms"] = part[9:].split()[0].lower()
    return out

def likelihood(pre, th):
    """Points rule from thresholds.json (proposed): -> {score, band, drivers[(text, points)]}. A label for the chair, never a probability."""
    L = th.get("likelihood")
    if not (pre and L): return None
    P = L["points"]; drivers = []
    for l in pre["cta"]:
        n = pk.pct(l["pct"]) or 0; lm = pk.is_lm(l["vessel"])
        if n >= L.get("ccta_obstructive_percent", 70) or (lm and n >= L.get("ccta_left_main_percent", 50)): drivers.append((f"CCTA {l['pct']}, severe stenosis, CAD-RADS 4A/4B range ({l['id']} {l['vessel']}; E5)", P["ccta_obstructive"]))
        elif n >= L.get("ccta_intermediate_percent", 50): drivers.append((f"CCTA {l['pct']}, intermediate stenosis ({l['id']} {l['vessel']}; E6)", P["ccta_intermediate"]))
    if len(pre["cta"]) >= 2: drivers.append(("two or more CCTA lesions", P["ccta_two_or_more_lesions"]))
    if pre["stress"] == "positive": drivers.append((f"stress test positive ({re.sub(r'^positive\s*', '', pre['stress_text'], flags=re.I) or 'no detail'})", P["stress_positive"]))
    elif pre["stress"] == "equivocal": drivers.append(("stress test equivocal", P["stress_equivocal"]))
    if pre["symptoms"] == "typical": drivers.append(("typical angina", P["typical_angina"]))
    wall = (pre["stress_text"].split(",", 1)[1] if "," in pre["stress_text"] else "").lower(); vessels = sorted({v for w, vs in L.get("territories", {}).items() if w in wall for v in vs})
    if pre["stress"] == "positive" and any((angio.norm_vessel(c["vessel"]) or "").split("-")[-1].split(" ")[-1] in vessels for c in pre["cta"]): drivers.append((f"the positive stress result ({wall.strip()}) is in the territory of the CCTA lesion", P["mpi_concordant_with_ccta_lesion"]))
    if pre["ef"] is not None and pre["ef"] <= L.get("low_ef_percent", 40): drivers.append((f"low EF ({pre['ef']}%)", P["low_ef"]))
    if len([s for s in re.split(r",| and ", pre["symptoms_text"]) if s.strip()]) >= 2: drivers.append((f"more than one symptom ({pre['symptoms_text']})", P["additional_symptom"]))
    score = sum(p for _, p in drivers); band = next(b["label"] for b in L["bands"] if score <= b["max_points"])
    return dict(score=score, band=band, drivers=drivers)

def stock_names(f):
    """{lower name: the name as written in the STOCK line}, for display."""
    out = {}
    for seg in f["_stock"].split("|"):
        m = re.match(r"^\s*(.*?\S)\s+(\d+)(\s+on hand.*|,.*)?\s*$", seg.strip())
        if m: out[m.group(1).lower()] = m.group(1)
    return out

def manifest_groups(f):
    """[(label, [(device, status)])]: one group for a single DEVICES line, or Branch A / Branch B when the packet lists DEVICES DIAGNOSTIC and DEVICES IF PCI."""
    st = stock(f); groups = []
    for key, label in (("DEVICES", ""), ("DEVICES DIAGNOSTIC", "Branch A · stays diagnostic"), ("DEVICES IF PCI", "Branch B · proceeds to PCI")):
        if key not in f: continue
        rows = []
        for d in [x.strip() for x in re.split(r"[,;]", f[key]) if x.strip()]:
            hit = next((k for k in st if k == d.lower() or d.lower().startswith(k) or k.startswith(d.lower())), None); n, note = st[hit] if hit else (None, "")
            rows.append((d, "not in STOCK line" if n is None else ("OUT: 0 on hand" + (f" · {note}" if note else "") if n == 0 else f"{n} on hand")))
        groups.append((label, rows))
    return groups

def prep(ls, groups, lk, pre, th, pathway, stock_all=None, case_time="99:99", names=None, ef=None):
    names = names or {}
    """Prep check: which branches are staged, what is out of stock, and completeness questions for the chair (devices named in the packet against the lesions). Never names a device."""
    P = th.get("prep", {}); allrows = [r for _, rows in groups for r in rows]; text = " ".join(d for d, _ in allrows).lower(); kw = lambda k: any(w.lower() in text for w in P.get(k, []))
    out = [d for d, s in allrows if s.startswith("OUT")]; qs = []
    findings = [l for l in (ls or (pre["cta"] if pre else [])) if (pk.pct(l["pct"]) or 0) >= P.get("min_stenosis_percent", 50)]; src = "angiography" if ls else "CCTA"
    if findings:
        stents = sum(text.count(w.lower()) for w in P.get("stent_keywords", ["DES"][:0])[:1]) if kw("stent_keywords") else 0
        stents = len(re.findall(r"\bdes\b|stent", text))
        if len(findings) > stents: qs.append(f"{len(findings)} lesion{'s' if len(findings) != 1 else ''} on {src} and {stents} stent{'s' if stents != 1 else ''} named in the packet: chair to confirm what to stage.")
        ca = [l for l in findings if pk.calc(l["calcium"])]
        if ca and not kw("calcium_modification_or_imaging_keywords"): qs.append(f"Calcium {ca[0]['calcium'].replace('calcium ', '')} on {ca[0]['id']} {ca[0]['vessel']} ({src}): the packet names no calcium-modification device or intravascular imaging catheter. Chair to decide whether any is needed.")
        lm = [l for l in findings if pk.is_lm(l["vessel"]) or (pk.has_flag(l["flag"]) and not l.get("cta"))]
        if lm and not kw("calcium_modification_or_imaging_keywords"): qs.append(f"Left main or bifurcation on {lm[0]['id']} ({src}): the packet names no intravascular imaging catheter. Chair to decide.")
        if not kw("wire_keywords"): qs.append("No wire is named in the packet's device lines: chair to confirm.")
        if not kw("balloon_keywords") and pathway == "indeterminate": qs.append("No balloon is named for the PCI branch: chair to confirm.")
    sef = P.get("support_question_ef_percent"); ef_val = ef if ef is not None else (pre["ef"] if pre else None)
    if ef_val is not None and sef is not None and ef_val <= sef:
        sup = [f"{names.get(k, k)} {n}" for k, (n, _) in (stock_all or {}).items() if any(w in k for w in ("impella", "iabp"))]
        qs.append(f"EF {ef_val}% in the packet. The 2015 SCAI/ACC consensus names high-risk PCI (multivessel, left main, last conduit) with severely reduced EF but gives no EF cutoff (E10). Support devices on the shelf: {', '.join(sup) or 'none in the stock list'}. Chair to decide whether support is needed.")
    if pathway == "indeterminate" and lk:
        both = ["lower", "intermediate", "higher"].index(lk["band"]) >= ["lower", "intermediate", "higher"].index(P.get("stage_both_branches_from_band", "intermediate"))
        scope = "Stage Branch A and Branch B (band " + lk["band"] + ", proposed rule)" if both else "Stage Branch A and name what Branch B would need (band " + lk["band"] + ", proposed rule; a label, not a statement that PCI is unlikely)"
    else: scope = "Stage the devices named in the packet"
    classes = (("Guide catheters", ("guide",)), ("Diagnostic catheters", ("diagnostic",)), ("Wires", ("wire",)), ("Balloons", ("balloon",)), ("Stents (DES)", ("des ",)), ("Intravascular imaging", ("ivus", "oct")), ("Support devices", ("impella", "iabp"))); shelf = []
    for label, keys in classes:
        items = [(k, v) for k, v in (stock_all or {}).items() if any(w in (k + " ") for w in keys)]
        shelf.append((label, ", ".join(f"{names.get(k, k)} {n}" + (f" ({note})" if note else "") for k, (n, note) in items) or "none in the stock list"))
    for k, (n, note) in (stock_all or {}).items():  # timing: a stocked-out imaging device that arrives after the scheduled start
        eta = re.search(r"ETA (\d\d:\d\d)", note or "")
        if n == 0 and eta and any(w in k for w in ("ivus", "oct")) and eta.group(1) > case_time and any(pk.calc(l["calcium"]) or pk.is_lm(l["vessel"]) for l in findings):
            qs.append(f"Calcium or left main on {src}, and {names.get(k, k)} is 0 on hand with resupply ETA {eta.group(1)}, after the scheduled {case_time} start: chair to decide how to proceed.")
    return dict(shelf=shelf, scope=scope, out=out, questions=qs, status=("OUT: " + ", ".join(out)) if out else "all named devices in stock")

def briefs(text):
    out = {}
    for m in re.finditer(r"\*\*\[(\w+) — Case (\d)\]\*\*(.*?)(?=\*\*\[\w+ — Case \d\]\*\*|\Z)", text or "", re.S):
        out[m.group(1).lower()] = "**[" + m.group(1) + " — Case " + m.group(2) + "]**" + m.group(3).strip()
    return out

def build(case, btext, approved=False, th=None):
    if not re.fullmatch(r"[1-9]", str(case)): sys.exit("case must be a single digit 1-9")
    warn = []; f = packet(case); th = th or json.load(open(os.path.join(ROOT, "thresholds.json"))); b = briefs(btext); ls = lesions(f, warn); pathway = f.get("PATHWAY", "known").strip().lower() or "known"; pre = precath(f)
    if pathway not in ("known", "indeterminate"): warn.append(f"PATHWAY '{pathway}' not recognised, treated as known"); pathway = "known"
    tr = triggers(ls); stage = "pre-cath" if pathway == "indeterminate" else ""; lk = likelihood(pre, th) if stage == "pre-cath" else None
    labs = f.get("LABS", ""); egfr = re.search(r"eGFR\s*[:=]?\s*([<>~]?)\s*(\d+)", labs, re.I); cm = re.search(r"est\.?\s*contrast\s*[:=]?\s*(\d+)\s*mL", f.get("PLAN", ""), re.I)
    ratio_raw = int(cm.group(1)) / int(egfr.group(2)) if egfr and cm and int(egfr.group(2)) > 0 else None; ratio = round(ratio_raw, 1) if ratio_raw is not None else None
    if "contrast" in f.get("PLAN", "").lower() and ratio is None: warn.append("contrast and eGFR were not both read, so the contrast ratio rule did NOT run")
    if egfr and egfr.group(1): warn.append(f"eGFR is given as '{egfr.group(1)}{egfr.group(2)}': the ratio uses {egfr.group(2)}, a bound, not a measurement")
    angio_missing = pathway != "indeterminate" and ((not ls) or "MISSING: ANGIO" in b.get("imaging", ""))
    cap = th.get("contrast_ratio_cap"); rules = []; contrast_hit = False
    if ratio is not None and cap is None: rules.append(f"Contrast ratio {ratio}: cap NOT SET, chair to supply.")
    elif ratio is not None and ratio_raw > cap:
        contrast_hit = True; rules.append(f"Contrast ratio above published cutoffs: {ratio} ({cm.group(1)} mL ÷ eGFR {egfr.group(2)}) is above {cap}, a cutoff that discriminated early creatinine rise in Laskey 2007 (E2), and above 3, where risk was clearest in Gurm 2011 (E1). Observational cutoffs, not a limit; both used creatinine clearance, not eGFR. Chair to decide whether to stage.")
    elif ratio is not None and ratio_raw >= 3:
        rules.append(f"Contrast ratio {ratio} is at or above 3, where risk was clearest in the Gurm 2011 registry (E1; creatinine clearance, not eGFR), and below {cap} (Laskey 2007, E2). Chair to decide.")
    elif ratio is not None and th.get("contrast_ratio_watch") is not None and ratio_raw >= th["contrast_ratio_watch"]:
        rules.append(f"Contrast ratio {ratio} is at or above {th['contrast_ratio_watch']}, where risk began to rise in the Gurm 2011 registry (E1; creatinine clearance, not eGFR). Chair to decide.")
    ht = th.get("heart_team", {}); ef = pre["ef"] if pre and pre["ef"] is not None else pk.ef(f.get("HISTORY", ""))
    fam = pk.family
    factors = []
    if any(pk.is_lm(l["vessel"]) and (pk.pct(l["pct"]) or 0) >= ht.get("left_main_percent", 50) for l in ls): factors.append("left main disease")
    if len({fam(l["vessel"]) for l in ls if (pk.pct(l["pct"]) or 0) >= 70 and fam(l["vessel"]) in ("lad", "lcx", "rca")}) >= 2 and ef is not None and ef <= ht.get("low_ef_percent", 35): factors.append(f"multivessel disease with EF {ef}%")
    if lk: rules.append(f"Likelihood band (proposed rule, {lk['score']} points): {lk['band']}. A label from a points rule, not a probability. Chair to decide; equipment is staged for both branches below.")
    if angio_missing: rules.append("Angio data missing: complexity and staging were not assessed. Nothing here is a clearance.")
    elif stage == "pre-cath": pass
    elif factors: rules.append(f"Heart Team factors present (2021 ACC/AHA/SCAI; E7, E8): {'; '.join(factors)}. SYNTAX score is not computed here. Chair to decide on Heart Team review.")
    if not rules or (stage == "pre-cath" and not lk): rules.append("No rule fired. The rules are proposed, and no rule firing is not clearance.")
    pt = re.search(r"CASE \d — (.*?) — scheduled (\S+) — (.*)", f["_head"])
    missing = [a for a in AGENTS if a not in b]
    flags = {a: [l.strip() for l in b.get(a, "").splitlines() if l.strip().startswith("🚩")] for a in AGENTS}
    notes = {a: [l.strip() for l in b.get(a, "").splitlines() if l.strip().startswith("MISSING:")] for a in AGENTS}
    needs = [l.strip() for a in AGENTS for l in b.get(a, "").splitlines() if l.strip().startswith("➡️")]
    s1 = [l for l in ls if l["vessel"].lower() in pt.group(3).lower()]; s2 = [l for l in ls if l not in s1]
    rec_dir = os.environ.get("RECORDS_DIR") or os.path.join(ROOT, "briefs"); ruling = records.rulings(rec_dir).get(str(case), {}).get("text")
    appr = [a for a in records.approvals(rec_dir) if re.search(rf"\bcase {case}\b", a["what"], re.I)]
    return dict(prov=provenance(case), warn=warn, prep=prep(ls, manifest_groups(f), lk, pre, th, pathway, stock(f), pt.group(2), stock_names(f), ef), pathway=pathway, stage=stage, pre=pre, lk=lk, groups=manifest_groups(f), ruling=ruling, appr=appr, case=case, pt=pt.group(1), time=pt.group(2), proc=pt.group(3), lesions=ls, triggers=tr, ratio=ratio, cap=cap, rules=rules, manifest=manifest(f),
                flags=flags, notes=notes, needs=needs, s1=s1, s2=s2, staged=contrast_hit and bool(s1), devices=f.get("DEVICES", ""), missing=missing, approved=approved, th=th,
                angio_missing=angio_missing, unreliable="unreliable" in labs, report=f.get("CATH REPORT", "not in packet"), stamp=time.strftime("%Y-%m-%d %H:%M"))

def md(p):
    L = [f"# CATH PLAN · Case {p['case']} · {'APPROVED' if p['approved'] else 'DRAFT'}", f"_{SIGNED if p['approved'] else DRAFT}_", "", f"**{p['pt']} · {p['time']} · {p['proc']}**", ""]
    if p["warn"]: L += ["> PARSE WARNINGS: " + " | ".join(p["warn"]), ""]
    if p["missing"]: L += [f"> INCOMPLETE: no brief from {', '.join(p['missing'])}", ""]
    if p["angio_missing"]: L += ["> ANGIO DATA MISSING: complexity and staging were not assessed.", ""]
    if p["pre"]:
        L += ["## Pre-cath findings (indeterminate pathway)", f"- Stress: {p['pre']['stress_text'] or 'n/a'}", f"- EF: {str(p['pre']['ef']) + '%' if p['pre']['ef'] is not None else 'n/a'}", f"- Symptoms: {p['pre']['symptoms_text'] or 'n/a'}"] + [f"- CCTA {c['id']} {c['vessel']} {c['pct']} · {c['calcium']}" for c in p["pre"]["cta"]]
        if p["lk"]: L += [f"- Likelihood band (proposed points rule): {p['lk']['band']} ({p['lk']['score']} points; not a probability)"] + [f"  - {d} (+{pt})" for d, pt in p["lk"]["drivers"]]
        L += [""]
    L += ["## Lesion map", "| Lesion | Vessel | Stenosis | TIMI | Calcium | Flag |", "|---|---|---|---|---|---|"] + [f"| {l['id']} | {l['vessel']} | {l['pct']} | {l['timi']} | {l['calcium']} | {l['flag']} |" for l in p["lesions"]]
    L += ["", "Angio findings flagged: " + ("not assessed" if p["angio_missing"] else f"{len(p['triggers'])} of 4" + (" (" + "; ".join(p["triggers"]) + ")" if p["triggers"] else "")), "", "## Rules that fired"] + [f"- {r}" for r in p["rules"]]
    if p["staged"]:
        L += ["", "## If the chair stages (illustration from the packet, not a recommendation)", f"- Stage 1: {', '.join(l['id'] + ' ' + l['vessel'] for l in p['s1'])} (the procedure named in the packet)",
              f"- Stage 2: {', '.join(l['id'] + ' ' + l['vessel'] for l in p['s2']) or 'none'}: devices not listed in the packet, Equipment to confirm"]
    L += ["", "## Equipment manifest"]
    for label, rows in p["groups"]: L += ([f"**{label}**"] if label else []) + ["| Item | Stock |", "|---|---|"] + [f"| {a} | {b} |" for a, b in rows]
    L += ["", "## Prep check", f"- Scope: {p['prep']['scope']}", f"- Stock: {p['prep']['status']}"] + [f"- On the shelf · {a}: {b}" for a, b in p["prep"]["shelf"]] + [f"- Question for the chair: {q}" for q in p["prep"]["questions"]]
    L += ["", "## Flags from the agents"]
    for a in AGENTS: L += [f"**{a.title()}**"] + ((p["flags"][a] + p["notes"][a]) or ["✅ none"])
    if p["needs"]: L += ["", "## Open requests"] + p["needs"]
    L += ["", "## Summary and approvals", f"- Ruling recorded: {p['ruling'] or 'none yet'}", "- Flags: " + " · ".join(f"{a.title()} {len(p['flags'][a])}" for a in AGENTS)]
    L += [f"- Approval {a['request']}: {a['decision']} by {a['by']} at {records.when(a['ts'])}" for a in p["appr"]]
    if p["approved"]: L += [f"- This plan: Allow once by the chair on the Switch card, {p['stamp']}"]
    L += ["", f"Contrast ratio: {p['ratio'] if p['ratio'] is not None else 'n/a'} (proposed cap {p['cap']}; contrast mL ÷ eGFR)" + (" · eGFR flagged unreliable in the packet" if p["unreliable"] else ""),
          f"Thresholds: {p['th']['status_text'] if not p['th']['verified'] else 'verified by the chair'} · {'template logic verified' if p['th'].get('logic_verified') else LOGIC}", "",
          "**Status: " + ("APPROVED by the chair" if p["approved"] else "AWAITING CHAIR RULING") + "**", f"_Provenance: template {p['prov']['template']} · thresholds {p['prov']['thresholds']} · plan.py {p['prov']['plan']} · {p['prov']['day']} · packet id {p['prov']['packet']}_"]
    return "\n".join(L) + "\n"

CSS = """@page{size:Letter;margin:0.45in 0.55in 0.6in;@bottom-left{content:'Synthetic demo · not clinical advice · not a medical device';font:8pt Helvetica;color:#444}@bottom-right{content:'Page ' counter(page) ' of ' counter(pages);font:8pt Helvetica;color:#444}}
*{box-sizing:border-box}html{width:7.4in}body{width:7.4in;font:10pt/1.45 -apple-system,Helvetica,Arial,sans-serif;color:#1d2330;margin:0}
.band{background:#14325c;color:#fff;padding:14px 18px;border-radius:8px}.band h1{margin:0;font-size:19pt;letter-spacing:.3px}.band .sub{opacity:.9;font-size:10pt;margin-top:3px}
.strip{background:#fff4d6;border:1px solid #e8c766;color:#5c4200;padding:5px 12px;border-radius:6px;margin:7px 0;font-size:9pt;font-weight:600}
.warn{background:#fde8e8;border:1px solid #e3a3a3;color:#8a1c1c}.cards{display:flex;gap:8px;margin:8px 0 2px}.card{flex:1;border:1px solid #d5dbe6;border-radius:8px;padding:8px 10px;background:#f7f9fc}
.card b{display:block;font-size:17pt;color:#14325c}.card span{font-size:8.5pt;color:#445}h2{font-size:11.5pt;color:#14325c;border-bottom:2px solid #14325c;padding-bottom:2px;margin:11px 0 5px}
table{border-collapse:collapse;width:100%;font-size:9.2pt}th{background:#e8eef7;text-align:left;padding:4px 7px;border:1px solid #cdd6e4}td{padding:3px 7px;border:1px solid #dbe1ec}tr:nth-child(even) td{background:#fafbfd}
.out{color:#9a1c1c;font-weight:700}.ok{color:#1c6b3a}ul{margin:4px 0 4px 18px;padding:0}li{margin:2px 0}.ag{margin:6px 0;display:flex;align-items:flex-start;break-inside:avoid}.ag>b{width:78px;flex:none;padding-top:2px}.ag>div,.ag>span.none{flex:1}
.flag{background:#fff7f7;border-left:4px solid #d64545;padding:2px 8px;margin:2px 0;border-radius:3px;font-size:9.3pt}.note{background:#fff4d6;border-left:4px solid #e0a020;padding:2px 8px;margin:2px 0;border-radius:3px;font-size:9.3pt}
.none{color:#1c6b3a;display:block}.sig{margin-top:18px;border:2px solid #14325c;border-radius:8px;padding:10px 14px;display:flex;justify-content:space-between;align-items:center}
.dec div{margin:5px 0;font-size:10pt}.bx{display:inline-block;width:12px;height:12px;border:1.5px solid #14325c;border-radius:2px;margin-right:8px;vertical-align:-2px}
.stamp{border:3px solid #1c6b3a;color:#1c6b3a;padding:4px 12px;font-weight:800;border-radius:6px;transform:rotate(-3deg)}.stamp.pend{border-color:#8a5a00;color:#8a5a00}tr,.card,.flag{break-inside:avoid}h2{break-after:avoid}
.def{font-size:8.5pt;color:#334;margin:2px 0 0}.fig{margin:4px 0 8px}.fig svg{height:auto}.lc{border:1px solid #cdd6e4;border-left:5px solid #14325c;border-radius:4px;padding:5px 10px;margin:5px 0;font-size:9.5pt;background:#f7f9fc}.lc span{color:#445;font-size:9pt}"""

# Synthetic coronary tree in the AHA 15-segment scheme (right-dominant, anterior schematic; patient's right on the viewer's left). Not an image of any patient, not to scale.
# Each segment is one cubic Bezier (P0, P1, P2, P3), a width and its AHA number, so a lesion can be drawn ON its segment with the lumen narrowed to the stated %.
SEG = {  # name: (AHA no., points, width)
    "lm": ("5", ((200, 38), (200, 52), (200, 66), (200, 80)), 8.5),
    "lad1": ("6", ((200, 80), (206, 100), (216, 120), (214, 152)), 7.0), "lad2": ("7", ((214, 152), (212, 176), (210, 204), (206, 232)), 6.2), "lad3": ("8", ((206, 232), (202, 256), (194, 286), (184, 312)), 5.0),
    "lcx1": ("11", ((200, 80), (222, 80), (246, 90), (262, 108)), 6.4), "lcx2": ("13", ((262, 108), (282, 122), (302, 142), (302, 180)), 5.6), "lcx3": ("13", ((302, 180), (303, 214), (302, 236), (296, 258)), 4.4),
    "rca1": ("1", ((178, 36), (150, 42), (124, 58), (112, 76)), 7.2), "rca2": ("2", ((112, 76), (102, 98), (94, 126), (94, 162)), 6.6), "rca3": ("3", ((94, 162), (94, 196), (100, 226), (112, 248)), 5.8),
    "pda": ("4", ((112, 248), (128, 266), (146, 288), (160, 306)), 3.8), "plv": ("16", ((112, 248), (100, 264), (90, 278), (82, 296)), 3.6),
    "om1": ("12", ((262, 108), (294, 124), (316, 150), (320, 190)), 4.2), "om1b": ("12", ((320, 190), (324, 214), (324, 232), (320, 246)), 3.4), "om2": ("14", ((302, 196), (326, 208), (338, 236), (332, 272)), 3.2),
    "d1": ("9", ((214, 134), (250, 136), (282, 166), (292, 216)), 3.8), "d2": ("10", ((209, 196), (238, 200), (262, 224), (268, 272)), 3.4),
    "am1": ("", ((106, 90), (82, 108), (68, 138), (64, 172)), 2.8), "am2": ("", ((94, 202), (74, 216), (66, 240), (72, 264)), 2.6),
    "sep1": ("", ((213, 156), (196, 164), (186, 178), (181, 198)), 2.2), "sep2": ("", ((208, 218), (194, 226), (186, 240), (183, 258)), 2.0)}
MAIN = ("lm", "lad1", "lad2", "lad3", "lcx1", "lcx2", "lcx3", "rca1", "rca2", "rca3")
PLACE = {"lm": ("lm", .6), "lm bifurcation": ("lm", .9), "prox-lad": ("lad1", .55), "mid-lad": ("lad2", .5), "distal-lad": ("lad3", .45), "lad": ("lad2", .5), "d1": ("d1", .55), "d2": ("d2", .55),
         "prox-lcx": ("lcx1", .55), "mid-lcx": ("lcx2", .6), "distal-lcx": ("lcx3", .5), "lcx": ("lcx2", .6), "om1": ("om1", .55), "om2": ("om2", .5),
         "prox rca": ("rca1", .55), "mid-rca": ("rca2", .5), "distal rca": ("rca3", .5), "rca": ("rca2", .5), "pda": ("pda", .5), "plv": ("plv", .5)}
def bez(pts, t_):
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = pts; u = 1 - t_
    return (u**3 * x0 + 3 * u * u * t_ * x1 + 3 * u * t_ * t_ * x2 + t_**3 * x3, u**3 * y0 + 3 * u * u * t_ * y1 + 3 * u * t_ * t_ * y2 + t_**3 * y3)
def pathd(pts): return "M{} {} C {} {}, {} {}, {} {}".format(*[c for p in pts for c in p])
def tree(ls):
    """Draws every lesion on its AHA segment: the lumen narrows to the stated stenosis; red solid ring = 70% or more, amber dashed ring = under 70%; yellow dots = calcium moderate or severe."""
    e = html.escape; vessels = ""
    for name, (no, pts, w) in SEG.items(): vessels += f"<path d='{pathd(pts)}' fill='none' stroke='{'#d3ddee' if name in MAIN or name in ('pda', 'plv', 'om1', 'om1b') else '#a6b6cf'}' stroke-width='{w}' stroke-linecap='round'/>"
    nums = "".join(f"<text x='{x}' y='{y}' font-size='9' fill='#8497b8'>{n}</text>" for n, x, y in (("5", 186, 62), ("6", 222, 122), ("7", 220, 200), ("8", 190, 272), ("11", 232, 82), ("13", 308, 150), ("1", 134, 50), ("2", 78, 124), ("3", 78, 214), ("12", 300, 112), ("9", 270, 150), ("4", 142, 280)))
    names = "".join(f"<text x='{x}' y='{y}' font-size='11.5' font-weight='600' fill='#c5d2e6'>{n}</text>" for n, x, y in (("LM", 210, 56), ("LAD", 160, 326), ("LCx", 292, 282), ("RCA", 40, 150), ("OM1", 330, 130), ("D1", 292, 202), ("PDA", 168, 316), ("Ao", 170, 18)))
    marks = ""; ring_labels = ""
    for l in ls:
        v = l["vessel"].lower().strip(); key = v if v in PLACE else (v.replace(" bifurcation", "") if v.replace(" bifurcation", "") in PLACE else next((k for k in sorted(PLACE, key=len, reverse=True) if k in v), None))
        if not key: continue
        seg, tt = PLACE[key]; no, pts, w = SEG[seg]; n = int(re.search(r"\d+", l["pct"]).group()); sev = n >= 70; col = "#e53935" if sev else "#f0a020"
        run = [bez(pts, min(1, max(0, tt + d))) for d in [i / 20 for i in range(-3, 4)]]; line = " ".join(f"{x:.1f},{y:.1f}" for x, y in run); x, y = bez(pts, tt)
        narrow = max(1.0, w * (1 - n / 100))  # lumen drawn at the stated % narrowing
        marks += f"<polyline points='{line}' fill='none' stroke='#0d1420' stroke-width='{w + 3}' stroke-linecap='butt'/><polyline points='{line}' fill='none' stroke='#d3ddee' stroke-width='{narrow:.1f}' stroke-linecap='round'/>"
        if re.search(r"moderate|severe", l["calcium"]): marks += "".join(f"<circle cx='{x + dx:.1f}' cy='{y + dy:.1f}' r='2.2' fill='#ffe066'/>" for dx, dy in ((-9, -8), (-11, 0), (-9, 8)))
        marks += f"<circle cx='{x:.1f}' cy='{y:.1f}' r='13' fill='none' stroke='{col}' stroke-width='2.8'{'' if sev else ' stroke-dasharray=\"3 2\"'}/>"
        left = key.startswith(("lm", "prox rca", "mid-rca", "distal rca", "rca", "pda", "plv")); lx = x - 19 if left else x + 19
        ring_labels += f"<text x='{lx:.1f}' y='{y + 4:.1f}' font-size='12.5' font-weight='700' fill='#ffffff' stroke='#0d1420' stroke-width='3.2' paint-order='stroke' text-anchor='{'end' if left else 'start'}'>{e(l['id'])} {e(l['pct'])}</text>"
    return ("<svg role='img' aria-label='Synthetic coronary tree with AHA segment numbers and the angio lesions marked; not an image of any patient' viewBox='0 0 380 336' width='300' height='265' "
            "style='background:#0d1420;border-radius:8px'><ellipse cx='188' cy='26' rx='36' ry='9' fill='none' stroke='#5d6f8d' stroke-width='2'/>" + vessels + nums + names + marks + ring_labels + "</svg>")


def figure_html(p):
    """Full-page angiographic findings: the synthetic figure plus one card per lesion (AHA segment, stenosis, TIMI, calcium)."""
    ls = p["lesions"] or (p["pre"]["cta"] if p["pre"] else [])
    if not ls: return ""
    e = html.escape; cards = ""; cta = not p["lesions"]
    for l in ls:
        k = angio.key_for(l["vessel"]); seg = angio.SEG[angio.PLACE[k][0]][0] if k else "not placed"; timi = pk.timi(l["timi"]); timi = 3 if timi is None else timi
        if cta: cards += f"<div class=lc><b>{e(l['id'])} · {e(l['vessel'])}</b> <span>({'AHA segment ' + e(seg) if k else 'not drawn on the figure: vessel not recognised'})</span><br>CCTA estimate {e(l['pct'])} · {e(l['calcium'])} · not yet confirmed by angiography</div>"; continue
        note = "normal filling" if timi == 3 else ("slow filling: the distal vessel is drawn fainter" if timi == 2 else "poor filling: the distal vessel is drawn very faint")
        cards += (f"<div class=lc><b>{e(l['id'])} · {e(l['vessel'])}</b> <span>({'AHA segment ' + e(seg) if k else 'not drawn on the figure: vessel not recognised'})</span><br>{e(l['pct'])} stenosis · {e(l['timi'])} ({note}) · calcium {e(l['calcium'].replace('calcium ', ''))} · flag {e(l['flag'])}</div>")
    return (f"<section style='break-before:page'><h2>{'Pre-cath CCTA findings (synthetic, not yet confirmed by angiography)' if cta else 'Angiographic findings (synthetic)'}</h2><div class=fig>{angio.svg(ls)}</div>{cards}"
            "<p class=def>Drawn from the angio lines in the packet by tools/angio.py: right-dominant tree, anterior view, AHA segment numbers, lumen narrowed to the stated percentage, calcium shown as bright specks, "
            "distal filling dimmed when TIMI flow is below 3. Solid red ring = stenosis of 70% or more; dashed amber ring = under 70%, or a CCTA estimate not yet confirmed. A Medina 1,1,1 flag is drawn as a narrowing of about half the proximal LAD and LCx. A teaching diagram, not an image of any patient and not to scale.</p></section>")

def htm(p):
    e = html.escape; B = lambda s: re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", e(s)); th = p["th"]
    strip = lambda x: re.sub(r"^🚩\s*(\*\*FLAG:\*\*)?\s*", "", x)
    rows = "".join(f"<tr><td>{e(l['id'])}</td><td>{e(l['vessel'])}</td><td>{e(l['pct'])}</td><td>{e(l['timi'])}</td><td>{e(l['calcium'])}</td><td>{e(l['flag'])}</td></tr>" for l in p["lesions"]) or ("<tr><td colspan=6>Angiography not yet performed: this is a pre-cath plan</td></tr>" if p["stage"] == "pre-cath" else "<tr><td colspan=6>No angio block in the packet</td></tr>")
    man = "".join(f"<tr><td>{e(a)}</td><td class='{'out' if b.startswith('OUT') else 'ok' if 'on hand' in b else ''}'>{e(b)}</td></tr>" for a, b in p["manifest"])
    fl = "".join(f"<div class=ag><b>{a.title()}</b>" + ("<div>" + "".join(f"<div class=flag>{B(strip(x))}</div>" for x in p["flags"][a]) + "".join(f"<div class=note>⚠ {B(x)}</div>" for x in p["notes"][a]) + "</div>" if (p["flags"][a] or p["notes"][a]) else "<span class=none>✅ nothing flagged</span>") + "</div>" for a in AGENTS)
    mtab = "".join("<table style='margin-bottom:6px'>" + (f"<tr><th colspan=2>{e(label)}</th></tr>" if label else "") + "<tr><th>Item (from the packet)</th><th>Stock</th></tr>" + "".join(f"<tr><td>{e(a)}</td><td class='{'out' if b.startswith('OUT') else 'ok' if 'on hand' in b else ''}'>{e(b)}</td></tr>" for a, b in rows) + "</table>" for label, rows in p["groups"])
    shelf = "".join(f"<tr><td style='width:150px'>{e(a)}</td><td>{e(b)}</td></tr>" for a, b in p["prep"]["shelf"])
    pq = "".join(f"<li>{e(q)}</li>" for q in p["prep"]["questions"]) or "<li>None: every check passed.</li>"
    prept = (f"<div style='break-inside:avoid'><h2>Prep check (devices against findings)</h2><table><tr><th style='width:110px'>Scope</th><td>{e(p['prep']['scope'])}</td></tr>"
             f"<tr><th>Stock</th><td class='{'out' if p['prep']['out'] else 'ok'}'>{e(p['prep']['status'])}</td></tr></table><table style='margin-top:6px'><tr><th colspan=2>On the shelf, by class (from the STOCK line)</th></tr>{shelf}</table><p class=def style='margin-top:6px'><b>Questions for the chair</b> (the plan asks, it does not choose a device):</p><ul>{pq}</ul></div>")
    nf = sum(len(v) for v in p["flags"].values()); ratio = f"{p['ratio']}" if p["ratio"] is not None else "n/a"
    names = lambda ls_: ", ".join(e(l["id"] + " " + l["vessel"] + " " + l["pct"]) for l in ls_) or "none"
    stg = (f"<h2>If the chair stages (illustration from the packet, not a recommendation)</h2><table><tr><th>Stage</th><th>Lesions</th><th>Devices</th></tr>"
           f"<tr><td><b>Stage 1</b></td><td>{names(p['s1'])} (the procedure named in the packet)</td><td>{e(p['devices'])}</td></tr>"
           f"<tr><td><b>Stage 2</b></td><td>{names(p['s2'])}</td><td class=out>not listed in the packet: Equipment to confirm</td></tr></table>") if p["staged"] else ""
    its = []
    if p["lk"]: its += ["The likelihood points rule is proposed: the chair verifies it.", "Equipment is staged for both branches: confirm stock for the branch actually taken."]
    if not th["verified"]: its.append("Thresholds in thresholds.json are proposed: the chair verifies them before this plan is used.")
    if not th.get("logic_verified"): its.append("Template logic (likelihood weights and bands, prep rules, Imaging triggers, Heart Team factors, stage assignment, Labs' eGFR cutoff) is unreviewed.")
    if p["angio_missing"]: its.append("Angio data is missing for this case: no conclusion about complexity or staging.")
    if p["staged"] and p["s2"]: its.append("Stage 2 devices are not listed in the packet: Equipment to confirm.")
    its += p["needs"] + [f"No brief yet from {a.title()}." for a in p["missing"]]
    items = "".join(f"<li>{B(strip(x))}</li>" for x in its) or "<li>None.</li>"
    trig = ("Angio findings: not assessed (angiography not yet performed)." if p["stage"] == "pre-cath" else "Angio findings: not assessed (no angio data)." if p["angio_missing"] else ("Triggers: " + e("; ".join(p["triggers"])) + "." if p["triggers"] else "No complexity trigger."))
    plabel = "indeterminate, pre-cath plan" if p["stage"] == "pre-cath" else "known intervention"
    third = "n/a" if p["angio_missing"] else f"{len(p['triggers'])} / 4"
    third_label = "angio findings flagged (calcium, flow, bifurcation, multivessel)"
    if p["lk"]: third, third_label = p["lk"]["band"], f"likelihood band ({p['lk']['score']} pts, proposed rule)"
    precard = ""
    if p["pre"]:
        pre = p["pre"]; cr = "".join(f"<tr><td>{e(c['id'])}</td><td>{e(c['vessel'])}</td><td>{e(c['pct'])}</td><td>{e(c['calcium'])}</td></tr>" for c in pre["cta"])
        dr = "".join(f"<tr><td>{e(d)}</td><td>+{pt}</td></tr>" for d, pt in (p["lk"]["drivers"] if p["lk"] else [])) + (f"<tr><th>Total · band: {e(p['lk']['band'])}</th><th>{p['lk']['score']}</th></tr>" if p["lk"] else "")
        precard = (f"<h2>Pre-cath findings (CCTA, stress, symptoms)</h2><table><tr><th>CCTA lesion</th><th>Vessel</th><th>Stenosis</th><th>Calcium</th></tr>{cr}</table>"
                   f"<p class=def>Stress test: {e(pre['stress_text'] or 'n/a')} · EF: {e(str(pre['ef']) + '%' if pre['ef'] is not None else 'n/a')} · Symptoms: {e(pre['symptoms_text'] or 'n/a')}</p>"
                   f"<table style='margin-top:6px'><tr><th>Likelihood driver (proposed points rule)</th><th style='width:60px'>Points</th></tr>{dr}</table>"
                   "<p class=def>A label from a points rule, not a probability. The chair decides whether to go on to PCI.</p>")
    decide = (f"<div class=dec><div>✔ Chair ruling recorded: approved on the Switch card, {e(p['stamp'])}.</div></div>" if p["approved"] else
              "<p class=def>For the chair's use: print and mark.</p><div class=dec><div><span class=bx></span> Approve as drafted</div><div><span class=bx></span> Chair changes the plan (record the change)</div><div><span class=bx></span> Equipment issue noted</div></div>")
    fcount = " · ".join(f"{a.title()} {len(p['flags'][a])}" for a in AGENTS); arows = "".join(f"<tr><td>{e(records.when(x['ts']))}</td><td>{e(x['request'])}</td><td class='{'ok' if x['decision'].startswith('Allow') else 'out'}'>{e(x['decision'])}</td><td>{e(x['by'])}</td></tr>" for x in p["appr"])
    if p["approved"]: arows += f"<tr><td>{e(p['stamp'][-5:])}</td><td>this plan</td><td class=ok>Allow once</td><td>the chair, on the Switch card</td></tr>"
    atable = f"<table><tr><th>Time</th><th>Request</th><th>Decision</th><th>By</th></tr>{arows}</table>" if arows else "<p class=def>No approval decisions recorded yet.</p>"
    summ = (f"<table><tr><th style='width:120px'>Ruling recorded</th><td>{e(p['ruling'] or 'none yet')}</td></tr>" + (f"<tr><th>Status</th><td>✔ Chair ruling recorded: approved on the Switch card, {e(p['stamp'])}.</td></tr>" if p["approved"] else "") + f"<tr><th>Flags</th><td>{e(fcount)}</td></tr>"
            f"<tr><th>Rules that fired</th><td>{' '.join(e(r) for r in p['rules'])}</td></tr></table><p class=def style='margin-top:6px'><b>For the chair to decide / check</b> (the agents only flag):</p><ul>{items}</ul><p class=def><b>Approvals</b></p>{atable}"
            + ("" if p["approved"] else "<p class=def>For the chair's use: print and mark.</p><div class=dec><div><span class=bx></span> Approve as drafted</div><div><span class=bx></span> Chair changes the plan (record the change)</div><div><span class=bx></span> Equipment issue noted</div></div>"))
    sigtxt = "Approved by the chair on the Switch card." if p["approved"] else "This draft is not approved until the chair presses Allow once on the Switch card."
    caveat = " The packet flags this eGFR as unreliable while creatinine is changing." if p["unreliable"] else ""
    return f"""<!doctype html><html><head><meta charset=utf-8><title>Cath Plan Case {e(str(p['case']))}</title><style>{CSS}</style></head><body>
<div class=band><h1>CATH PLAN · Case {e(str(p['case']))}</h1><div class=sub>{e(p['pt'])} · scheduled {e(p['time'])} · {e(p['proc'])} · pathway: {e(plabel)}</div></div>
<div class=strip>{SIGNED if p['approved'] else DRAFT}</div>
{"<div class='strip warn'>PARSE WARNINGS: " + e(" | ".join(p['warn'])) + "</div>" if p['warn'] else ""}
{"<div class='strip warn'>INCOMPLETE: no brief from " + e(", ".join(p['missing'])) + "</div>" if p['missing'] else ""}
{"<div class='strip warn'>ANGIO DATA MISSING: complexity and staging were not assessed. Nothing on this page is a clearance.</div>" if p['angio_missing'] else ""}
{"<div class='strip'>PRE-CATH PLAN: angiography has not been done. The likelihood is a label from a proposed points rule, not a probability, and equipment is staged for both branches.</div>" if p['stage'] == 'pre-cath' else ""}
{"" if (th['verified'] and th.get('logic_verified')) else "<div class='strip warn'>" + e(("Thresholds: " + th['status_text'] + ". ") if not th['verified'] else "") + e(("" if th.get('logic_verified') else LOGIC_SHORT)) + "</div>"}
<div class=cards><div class=card><b>{nf}</b><span>flags from 4 agents</span></div><div class=card><b>{ratio}</b><span>contrast ratio (proposed cap {p['cap']})</span></div><div class=card><b>{third}</b><span>{e(third_label)}</span></div><div class=card><b>{sum(1 for _, s in p['manifest'] if s.startswith('OUT'))}</b><span>devices out of stock</span></div></div>
<p class=def>Contrast ratio = planned contrast (mL) ÷ eGFR. {e(th.get('contrast_ratio_basis', ''))}{e(caveat)}</p>{precard}
<h2>Lesion map (Imaging)</h2><table><tr><th>Lesion</th><th>Vessel</th><th>Stenosis</th><th>TIMI</th><th>Calcium</th><th>Flag</th></tr>{rows}</table>
<p style="font-size:9.5pt;color:#334">{trig} · Cath report: {e(p['report'])}</p>
<h2>Rules that fired</h2><ul>{"".join(f"<li>{e(r)}</li>" for r in p['rules'])}</ul>
{stg}{figure_html(p)}<div style="break-inside:avoid;{'break-before:page' if (p['lesions'] or (p['pre'] and p['pre']['cta'])) else ''}"><h2>Equipment manifest</h2>{mtab}</div>{prept}
<div style="break-inside:avoid"><h2>Flags from the agents</h2>{fl}<p class=def>Relay: Imaging → Equipment, Labs → Meds.</p></div><div style="break-inside:avoid"><h2>Summary and approvals</h2>{summ}
<div class=sig><div><b>Status</b><br><span style="font-size:9pt;color:#334">{sigtxt}</span></div><div class="stamp{'' if p['approved'] else ' pend'}">{'APPROVED BY CHAIR' if p['approved'] else 'AWAITING CHAIR'}</div></div></div>
<p style="font-size:8.5pt;color:#444;margin-top:10px">Sources: packet ({e(p['prov']['day'])}) · briefs from Imaging, Labs, Meds, Equipment · thresholds.json · evidence table docs/EVIDENCE.md (E1 to E16, mostly secondary summaries, chair verifies). Generated {e(p['stamp'])} by plan.py (template, no model).<br>Provenance: template {e(p['prov']['template'])} · thresholds {e(p['prov']['thresholds'])} · plan.py {e(p['prov']['plan'])} · packet id {e(p['prov']['packet'])}. "ref:" on a flag names a published criterion; it is not an instruction.</p></body></html>"""

def render_pdf(html_path, pdf_path):
    if not os.path.exists(CHROME): return f"Chrome not found at {CHROME} (set CHROME=/path/to/chrome); the .md and .html were written"
    r = subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", f"--print-to-pdf={pdf_path}", "file://" + os.path.abspath(html_path)], capture_output=True, timeout=90)
    return None if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 1000 else f"Chrome produced no PDF (rc={r.returncode}): {r.stderr.decode()[-120:]}"

def atomic(path, text):
    open(path + ".tmp", "w").write(text); os.replace(path + ".tmp", path)

def write(case, btext, out, pdf=False, approved=False):
    p = build(case, btext, approved); os.makedirs(out, exist_ok=True); base = os.path.join(out, f"plan-case-{case}")
    for ext in (".md", ".html", ".pdf"):  # never leave an older plan behind as if it were this one
        if os.path.exists(base + ext): os.remove(base + ext)
    atomic(base + ".md", md(p)); atomic(base + ".html", htm(p)); res = [base + ".md", base + ".html"]; err = None
    if pdf:
        t0 = time.time() - 2; err = render_pdf(base + ".html", base + ".pdf")
        if not err and os.path.getmtime(base + ".pdf") < t0: err = "the PDF on disk is older than this run"
        if not err: res.append(base + ".pdf")
    return p, res, err

def read_dir(d, now=None):
    """Briefs from the room recorder's folder; returns (text, problems). Problems make the plan INCOMPLETE."""
    now = now or time.time(); files = sorted(glob.glob(os.path.join(d, "*.md"))); probs = []
    if not files: return "", ["no briefs recorded for this case"]
    ages = [now - os.path.getmtime(f) for f in files]
    if min(ages) > MAX_AGE_MIN * 60: probs.append(f"briefs are older than {MAX_AGE_MIN} min")
    if (max(ages) - min(ages)) > MAX_SPREAD_MIN * 60: probs.append(f"briefs come from different runs ({int((max(ages) - min(ages)) / 60)} min apart)")
    hb = os.path.join(os.path.dirname(os.path.abspath(d)), "_heartbeat")
    if not os.path.exists(hb) or now - os.path.getmtime(hb) > HEARTBEAT_S: probs.append("the room recorder is not running, so these briefs may be stale")
    for f in files:  # each file must be one brief whose header names the file's agent and this folder's case
        t = open(f).read(); h = re.findall(r"\*\*\[(\w+) — Case (\d)\]\*\*", t); name = os.path.basename(f)[:-3]; case = os.path.basename(os.path.abspath(d)).replace("case-", "")
        if name in AGENTS and (len(h) != 1 or h[0][0].lower() != name or h[0][1] != case): probs.append(f"{name}.md does not hold exactly one {name} brief for case {case}")
    read_dir.newest = max(os.path.getmtime(f) for f in files)
    return "\n".join(open(f).read() for f in files), probs

def selftest():
    b = "**[IMAGING — Case 2]** 74M\n🚩 **FLAG:** calcium moderate · L1\n**[LABS — Case 2]** x\n🚩 **FLAG:** Cr 2.7\n**[MEDS — Case 2]** x\n✅\n**[EQUIPMENT — Case 2]** x\n✅"
    th = dict(verified=False, logic_verified=False, status_text="PROPOSED", contrast_ratio_cap=3.7, contrast_ratio_basis="basis", heart_team_min_triggers=3)
    p = build("2", b, th=th); p5 = build("5", "**[IMAGING — Case 5]** x\nMISSING: ANGIO block", th=th); p1 = build("1", b, th=th); pa = build("2", b, approved=True, th=th); ok = True
    r3 = " ".join(build("3", b, th=th)["rules"]); nb = "not clearance" in r3 and "No rule fired" in r3
    for name, cond in [("ratio 7.1", p["ratio"] == 7.1), ("contrast rule says chair decides", any("Chair to decide whether to stage" in r for r in p["rules"])), ("2 lesions", len(p["lesions"]) == 2),
                       ("3 triggers", len(p["triggers"]) == 3), ("Heart Team factors fire for EF 30% with three vessels", any("Heart Team factors" in r and "multivessel disease with EF 30%" in r for r in build("5", b, th=th)["rules"])), ("complete", not p["missing"]),
                       ("missing detected", build("2", "", th=th)["missing"] == list(AGENTS)), ("null cap", any("NOT SET" in r for r in build("2", b, th=dict(th, contrast_ratio_cap=None))["rules"])),
                       ("no angio case", build("4", b, th=th)["lesions"] == []), ("angio missing is not a clearance", p5["angio_missing"] and any("not assessed" in r for r in p5["rules"]) and "not clearance" not in " ".join(p5["rules"]) and "ANGIO DATA MISSING" in htm(p5)),
                       ("no-rule wording says not clearance", nb), ("left main case: Heart Team factor named, no endorsement wording", "left main disease" in " ".join(p1["rules"]) and "single-stage" not in " ".join(p1["rules"]).lower()),
                       ("approved html drops the DRAFT strip", "DRAFT for the chair" not in htm(pa) and "APPROVED BY CHAIR" in htm(pa) and "Chair ruling recorded" in htm(pa)),
                       ("draft html keeps the DRAFT strip and boxes", "DRAFT for the chair" in htm(p) and "class=bx" in htm(p)), ("logic strip while unverified", "also unreviewed" in htm(p)),
                       ("eGFR caveat carried", "unreliable" in htm(p) and p["unreliable"]), ("stock note clean", all("(on hand" not in s for _, s in build("1", b, th=th)["manifest"])), ("md has no 'None' contrast", "Contrast ratio: n/a" in md(build("4", b, th=th)))]:
        print("PASS" if cond else "FAIL", name); ok &= cond
    w = []; ls = lesions({"ANGIO": "L1 | LMCA | total occlusion | TIMI III | Calcium Severe | - ; L2 | ramus | x% | ? | none | none ; bad"}, w)
    pc = [("packet reader: occlusion=100, TIMI III=3, '-' is no flag", pk.pct(ls[0]["pct"]) == 100 and pk.timi(ls[0]["timi"]) == 3 and not pk.has_flag(ls[0]["flag"])),
          ("packet reader: LMCA is left main, ramus is LCx family, triggers read them", pk.is_lm("LMCA") and pk.family("ramus") == "lcx" and "bifurcation, ostial or left main" in triggers(ls)),
          ("packet reader: unreadable values and short rows warn instead of crashing", len(w) == 3), ("packet reader: EF takes the latest value", pk.ef("prior EF 55%, now EF 30%") == 30 and pk.ef("LVEF 35-40%") == 35)]
    for name, cond in pc: print("PASS" if cond else "FAIL", name); ok &= cond
    import tempfile
    with tempfile.TemporaryDirectory() as td:  # pre-check: a missing brief and a brief older than the packet are named before the card is raised
        cd = os.path.join(td, "case-2"); os.makedirs(cd); now = time.time(); open(os.path.join(td, "_heartbeat"), "w").write("x")
        for i, ag in enumerate(AGENTS[:3]): open(os.path.join(cd, ag + ".md"), "w").write(f"**[{ag.upper()} — Case 2]** x\n")
        c4 = any("no brief from equipment" in x for x in check("2", cd))
        open(os.path.join(cd, "equipment.md"), "w").write("**[EQUIPMENT — Case 2]** x\n"); c5 = check("2", cd) == []
        json.dump({"id": "abcdef123456", "ts": now + 600}, open(os.path.join(td, "packet-2.json"), "w")); c6 = any("older than the chair's latest packet" in x for x in check("2", cd))
        open(os.path.join(cd, "labs.md"), "w").write("**[IMAGING — Case 2]** x\n"); c7 = any("labs.md does not hold" in x for x in check("2", cd))
        for name, cond in (("pre-check names a missing brief", c4), ("pre-check passes a complete fresh set", c5), ("pre-check refuses briefs older than the packet", c6), ("pre-check refuses a brief filed under the wrong agent", c7)): print("PASS" if cond else "FAIL", name); ok &= cond
    pv = provenance("2"); c8 = all(len(pv[k]) >= 3 for k in ("template", "thresholds", "plan", "day")) and "Provenance" in md(build("2", b, th=th)) and "Provenance:" in htm(build("2", b, th=th))
    print("PASS" if c8 else "FAIL", "provenance carried in md and html"); ok &= c8
    with tempfile.TemporaryDirectory() as td:  # signing needs a real, newer, matching Allow
        j = lambda *r: open(os.path.join(td, "approvals.jsonl"), "w").write("\n".join(json.dumps(x) for x in r) + "\nnot json\n")
        A = lambda dec, ts, what="Run plan tool for case 2": dict(id=str(ts), ts=ts, request="A1", decision=dec, what=what, by="chair")
        j(A("Allow once", 100)); c1 = bool(records.signed(td, r"\bcase 2\b", 50)) and not records.signed(td, r"\bcase 2\b", 150) and not records.signed(td, r"\bcase 3\b", 50)
        j(A("Allow once", 100), A("Decline", 200)); c2 = not records.signed(td, r"\bcase 2\b", 50)
        j(A("Decline", 100), A("Allow once", 200)); c3 = bool(records.signed(td, r"\bcase 2\b", 50))
        for name, cond in (("signing: Allow newer than briefs counts, older or other case does not", c1), ("signing: a later Decline cancels", c2), ("signing: later Allow after Decline counts, bad JSONL line tolerated", c3)): print("PASS" if cond else "FAIL", name); ok &= cond
    for bad in ("0", "10", "a", "1;rm"):
        try: build(bad, b, th=th); print("FAIL case validation", bad); ok = False
        except SystemExit: pass
    print("PASS case validation"); print("SELFTEST", "OK" if ok else "FAILED"); return 0 if ok else 1

if __name__ == "__main__":
    a = sys.argv[1:]
    if "--selftest" in a: sys.exit(selftest())
    if not a: sys.exit(__doc__)
    arg = lambda k, d=None: a[a.index(k) + 1] if k in a else d
    bt = arg("--briefs"); probs = []
    if "--check" in a and bt and os.path.isdir(bt):
        pr = check(a[0], bt); print("PLAN CHECK " + ("OK: ready to sign" if not pr else "WOULD REFUSE: " + "; ".join(pr))); sys.exit(1 if pr else 0)
    if bt and os.path.isdir(bt): bt, probs = read_dir(bt)
    else: bt = sys.stdin.read() if bt == "-" else (open(bt).read() if bt else "")
    if probs and "--force" not in a: print("PLAN INCOMPLETE: " + "; ".join(probs)); sys.exit(3)
    if "--approved" in a:  # a stamp needs a real Allow: briefs from the recorder's folder, an Allow decided after the newest brief, and no --force
        if "--force" in a: print("PLAN INCOMPLETE: --approved cannot be combined with --force"); sys.exit(3)
        rd = os.path.join(ROOT, "briefs")
        if not os.path.isdir(arg("--briefs") or ""): print("PLAN INCOMPLETE: signing needs the recorder's briefs folder"); sys.exit(3)
        if not records.signed(rd, rf"\bcase {a[0]}\b", getattr(read_dir, "newest", 0)):
            last = (records.approvals(rd) or [{}])[-1]; print(f"PLAN INCOMPLETE: no Allow once recorded for this plan after its newest brief (last card: {last.get('decision', 'none')} {last.get('what', '')[:50]}); not signing"); sys.exit(3)
    p, files, err = write(a[0], bt, arg("--out", os.path.join(ROOT, "plans")), "--pdf" in a, "--approved" in a)
    print("\n".join(files))
    if err: print("PLAN INCOMPLETE: " + err); sys.exit(2)
    sys.exit(1 if p["missing"] else 0)
