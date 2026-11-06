"""Small shared packet readers: tolerant of spelling, never crash, return None when a value cannot be read (callers warn)."""
import re
NONE = {"", "none", "-", "—", "n/a", "na", "no", "nil"}
def pct(s):
    """'70%' -> 70, '60-70%' -> 70 (the higher end), 'total occlusion' / 'CTO' -> 100, unreadable -> None."""
    s = (s or "").lower()
    if re.search(r"occlu|\bcto\b", s): return 100
    n = [int(x) for x in re.findall(r"\d+", s)]
    return max(n) if n else None
def timi(s):
    """'TIMI 2' / 'TIMI III' / '2' -> 0..3, unreadable -> None."""
    s = (s or "").lower(); m = re.search(r"\b([0-3])\b", s)
    if m: return int(m.group(1))
    r = re.search(r"\b(iii|ii|i|0)\b", s)
    return {"iii": 3, "ii": 2, "i": 1, "0": 0}[r.group(1)] if r else None
def is_lm(v): return bool(re.search(r"\blm\b|\blmca\b|\blmain\b|left\s*main", (v or "").lower()))
def has_flag(f): return (f or "").strip().lower() not in NONE
def calc(c): return bool(re.search(r"moderate|severe", (c or "").lower()))
def family(v):
    """Vessel -> 'lm'|'lad'|'lcx'|'rca'|None, with branches mapped to their parent (diagonal/septal -> lad, ramus/OM/marginal/LPL -> lcx, PDA/PL/PLV/acute marginal -> rca)."""
    s = re.sub(r"[-_/]", " ", (v or "").lower())
    if is_lm(s): return "lm"
    for fam, pat in (("lad", r"\blad\b|\bd[1-3]\b|diagonal|septal"), ("lcx", r"\blcx\b|circumflex|\bom\d?\b|marginal|ramus|\blpl\b"), ("rca", r"\brca\b|\bpda\b|\bpl\b|\bplv\b|\bplb\b|posterior")): 
        if re.search(pat, s): return fam
    return None
def ef(text):
    """Last EF/LVEF % in a text (a later 'now' value beats an earlier 'prior' one), or None."""
    m = re.findall(r"(?:lv)?ef\s*[:=]?\s*(\d+)(?:\s*-\s*(\d+))?\s*%?", (text or "").lower())
    return min(int(a) for a in (m[-1][0], m[-1][1] or m[-1][0])) if m else None

def territories(lesions):
    """Distinct coronary territories among lesions (dicts with 'id' and 'vessel'): LAD (with diagonals, septals), LCx (with OM, ramus), RCA (with PDA, PLV) and the left main each count once; a vessel that cannot be read counts as its own. Two lesions in one territory are not multivessel disease."""
    return {pk_family(l["vessel"]) or l["id"] for l in lesions}
pk_family = family
