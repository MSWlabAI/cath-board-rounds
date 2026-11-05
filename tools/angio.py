#!/usr/bin/env python3
"""Synthetic angiographic figure for one case, drawn from the packet's ANGIO lines (never an image of a patient).
Film-style render: tapering lumen polygons, a smooth hourglass narrowing at each lesion (depth = the stated %), calcium speckle, faded distal filling when TIMI is below 3,
a guide catheter and aortic root, AHA segment numbers. Right-dominant tree, anterior schematic, not to scale. Layers are named groups (film, vessels, lesions, labels) so an illustrator can restyle the file.
usage: angio.py CASE [OUT.svg]      (library use: svg(lesions) -> str)"""
import html, math, os, random, re, sys
sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
W, H = 760, 720
SEG = {  # name: (AHA no., Bezier points in a 380x336 design space, base width)
    "lm": ("5", ((200, 38), (200, 52), (200, 66), (200, 80)), 8.8),
    "lad1": ("6", ((200, 80), (206, 100), (216, 120), (214, 152)), 7.4), "lad2": ("7", ((214, 152), (212, 176), (210, 204), (206, 232)), 6.6), "lad3": ("8", ((206, 232), (202, 256), (194, 286), (184, 312)), 5.4),
    "lcx1": ("11", ((200, 80), (222, 80), (246, 90), (262, 108)), 6.8), "lcx2": ("13", ((262, 108), (282, 122), (302, 142), (302, 180)), 6.0), "lcx3": ("13", ((302, 180), (303, 214), (302, 236), (296, 258)), 4.8),
    "rca1": ("1", ((178, 36), (150, 42), (124, 58), (112, 76)), 7.6), "rca2": ("2", ((112, 76), (102, 98), (94, 126), (94, 162)), 7.0), "rca3": ("3", ((94, 162), (94, 196), (100, 226), (112, 248)), 6.2),
    "pda": ("4", ((112, 248), (128, 266), (146, 288), (160, 306)), 4.2), "plv": ("16", ((112, 248), (100, 264), (90, 278), (82, 296)), 4.0),
    "om1": ("12", ((262, 108), (294, 124), (316, 150), (320, 190)), 4.6), "om1b": ("12", ((320, 190), (324, 214), (324, 232), (320, 246)), 3.6), "om2": ("14", ((302, 196), (326, 208), (338, 236), (332, 272)), 3.4),
    "d1": ("9", ((214, 134), (250, 136), (282, 166), (292, 216)), 4.2), "d2": ("10", ((209, 196), (238, 200), (262, 224), (268, 272)), 3.6),
    "am1": ("", ((106, 90), (82, 108), (68, 138), (64, 172)), 3.0), "am2": ("", ((94, 202), (74, 216), (66, 240), (72, 264)), 2.8),
    "sep1": ("", ((213, 156), (196, 164), (186, 178), (181, 198)), 2.4), "sep2": ("", ((208, 218), (194, 226), (186, 240), (183, 258)), 2.2)}
PLACE = {"lm": ("lm", .6), "lm bifurcation": ("lm", .9), "prox-lad": ("lad1", .55), "mid-lad": ("lad2", .5), "distal-lad": ("lad3", .45), "lad": ("lad2", .5), "d1": ("d1", .55), "d2": ("d2", .55),
         "prox-lcx": ("lcx1", .55), "mid-lcx": ("lcx2", .6), "distal-lcx": ("lcx3", .5), "lcx": ("lcx2", .6), "om1": ("om1", .55), "om2": ("om2", .5),
         "prox rca": ("rca1", .55), "mid-rca": ("rca2", .5), "distal rca": ("rca3", .5), "rca": ("rca2", .5), "pda": ("pda", .5), "plv": ("plv", .5)}
DOWNSTREAM = {"lm": ("lad1", "lad2", "lad3", "d1", "d2", "sep1", "sep2", "lcx1", "lcx2", "lcx3", "om1", "om1b", "om2"), "lad1": ("lad2", "lad3", "d1", "d2", "sep1", "sep2"), "lad2": ("lad3", "d2", "sep2"), "lad3": (),
              "lcx1": ("lcx2", "lcx3", "om1", "om1b", "om2"), "lcx2": ("lcx3", "om2"), "lcx3": (), "rca1": ("rca2", "rca3", "pda", "plv", "am1", "am2"), "rca2": ("rca3", "pda", "plv", "am2"), "rca3": ("pda", "plv"),
              "d1": (), "d2": (), "om1": ("om1b",), "om2": (), "pda": (), "plv": ()}
def X(x): return 36 + 1.9 * x
def Y(y): return 22 + 1.9 * (y - 18)
def bez(pts, t):
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = pts; u = 1 - t
    return (u**3 * x0 + 3 * u * u * t * x1 + 3 * u * t * t * x2 + t**3 * x3, u**3 * y0 + 3 * u * u * t * y1 + 3 * u * t * t * y2 + t**3 * y3)
def centre(pts, n=48): return [(X(x), Y(y)) for x, y in (bez(pts, i / n) for i in range(n + 1))]
def outline(pts, w0, dips, taper=.16, n=48):
    """Polygon of a vessel segment: width tapers along the segment and dips smoothly at each lesion (t0, depth, sigma)."""
    c = centre(pts, n); L, R = [], []
    for i, (x, y) in enumerate(c):
        a, b = c[max(0, i - 1)], c[min(n, i + 1)]; dx, dy = b[0] - a[0], b[1] - a[1]; d = math.hypot(dx, dy) or 1; nx, ny = -dy / d, dx / d; t = i / n
        w = w0 * 1.9 * 0.5 * (1 - taper * t);
        for t0, depth, sg in dips: w *= 1 - depth * math.exp(-((t - t0) / sg) ** 2)
        w = max(w, 0.7); L.append((x + nx * w, y + ny * w)); R.append((x - nx * w, y - ny * w))
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in L + R[::-1])

def norm_vessel(v):
    """Any spelling of a vessel ('distal RCA', 'RCA distal', 'proximal LAD', 'mid-LCx', 'OM1', 'LM bifurcation') -> an angio.PLACE key, or None."""
    s = re.sub(r"[-_/]", " ", v.lower()); s = s.replace("proximal", "prox").replace("left main", "lm")
    fam = next((f for f in ("lm", "lad", "lcx", "rca", "om1", "om2", "d1", "d2", "pda", "plv") if re.search(rf"\b{f}\b", s)), None)
    if not fam: return None
    if fam == "lm": return "lm bifurcation" if "bifurc" in s else "lm"
    seg = next((x for x in ("prox", "mid", "distal") if x in s), "")
    key = ("mid-rca" if seg == "mid" else f"{seg} rca".strip()) if fam == "rca" else (f"{seg}-{fam}" if seg and fam in ("lad", "lcx") else fam)
    return key if key in PLACE else (fam if fam in PLACE else None)

def key_for(vessel):
    n = norm_vessel(vessel)
    if n: return n
    v = vessel.lower().strip(); k = v.replace(" bifurcation", "")
    return v if v in PLACE else (k if k in PLACE else next((x for x in sorted(PLACE, key=len, reverse=True) if x in v), None))

def svg(ls, title=True):
    e = html.escape; rnd = random.Random(7); dips = {}; faded = {}; spots = []; badges = []
    for l in ls:
        key = key_for(l["vessel"])
        if not key: continue
        seg, t0 = PLACE[key]; n = int(re.search(r"\d+", l["pct"]).group()); dips.setdefault(seg, []).append((t0, min(.93, n / 100), .075))
        if "Medina 1,1,1" in l["flag"]:  # true bifurcation: disease runs into the proximal LAD and LCx
            dips.setdefault("lad1", []).append((.12, .5, .12)); dips.setdefault("lcx1", []).append((.12, .5, .12))
        tm = re.search(r"\d", l["timi"]); timi = int(tm.group()) if tm else 3
        if timi < 3: [faded.__setitem__(s, min(faded.get(s, 1), .62 if timi == 2 else .35)) for s in DOWNSTREAM.get(seg, ())]
        no, pts, w = SEG[seg]; x, y = [(X(a), Y(b)) for a, b in [bez(pts, t0)]][0]; badges.append((l, x, y, seg))
        if re.search(r"moderate|severe", l["calcium"]):
            for _ in range(15 if "severe" in l["calcium"] else 7):
                tt = min(1, max(0, t0 + rnd.uniform(-.1, .1))); px, py = [(X(a), Y(b)) for a, b in [bez(pts, tt)]][0]; ang = rnd.uniform(0, 6.28); r = w * .95 + rnd.uniform(1, 4); spots.append((px + r * math.cos(ang), py + r * math.sin(ang), rnd.uniform(1.8, 3.4)))
    glow = vess = ""
    for name, (no, pts, w) in SEG.items():
        poly = outline(pts, w, dips.get(name, []), .5 if name in ("am1", "am2", "sep1", "sep2", "d1", "d2", "om2") else .16); op = faded.get(name, 1)
        glow += f"<polygon points='{poly}' fill='#cfe0ff' opacity='{.5 * op:.2f}'/>"; vess += f"<polygon points='{poly}' fill='url(#lumen)' opacity='{op:.2f}'/>"
    nums = "".join(f"<text x='{X(x):.0f}' y='{Y(y):.0f}'>{n}</text>" for n, x, y in (("5", 184, 62), ("6", 224, 122), ("7", 196, 172), ("8", 192, 272), ("11", 232, 82), ("13", 284, 184), ("1", 134, 50), ("2", 76, 124), ("3", 76, 214), ("12", 300, 112), ("9", 270, 150), ("4", 142, 282), ("10", 252, 238), ("14", 338, 226), ("16", 74, 282)))
    names = "".join(f"<text x='{X(x):.0f}' y='{Y(y):.0f}'>{n}</text>" for n, x, y in (("LM", 212, 54), ("LAD", 190, 332), ("LCx", 292, 284), ("RCA", 42, 150), ("OM1", 330, 128), ("D1", 292, 206), ("PDA", 118, 316), ("Ao", 162, 14)))
    ca = "".join(f"<circle cx='{x:.1f}' cy='{y:.1f}' r='{r:.1f}'/>" for x, y, r in spots)
    les = ""
    for l, x, y, seg in badges:
        sev = int(re.search(r"\d+", l["pct"]).group()) >= 70; col = "#ff5252" if sev else "#ffb300"; cta = l.get("cta")
        left = seg in ("lm", "rca1", "rca2", "rca3", "pda", "plv"); lx = x - 38 if left else x + 38
        les += (f"<circle cx='{x:.1f}' cy='{y:.1f}' r='26' fill='none' stroke='{col}' stroke-width='2.2'{'' if (sev and not cta) else ' stroke-dasharray=\"5 4\"'}/>"
                f"<line x1='{x + (-26 if left else 26):.1f}' y1='{y:.1f}' x2='{lx + (6 if left else -6):.1f}' y2='{y:.1f}' stroke='{col}' stroke-width='1.6'/>"
                f"<text x='{lx:.1f}' y='{y + 5:.1f}' text-anchor='{'end' if left else 'start'}' font-size='17' font-weight='700' fill='#fff'>{'CTA ' if cta else ''}{e(l['id'])} {e(l['pct'])}</text>")
    cath = f"M{X(262):.0f} -8 C {X(262):.0f} 40, {X(238):.0f} 44, {X(210):.0f} {Y(36):.0f} L {X(200):.0f} {Y(40):.0f}"
    return (f"<svg xmlns='http://www.w3.org/2000/svg' role='img' aria-label='Synthetic angiographic figure with the case lesions marked; not an image of any patient' viewBox='0 0 {W} {H}' width='100%' style='display:block;border-radius:10px;background:#07090d'>"
            "<defs><radialGradient id='bg' cx='50%' cy='42%' r='75%'><stop offset='0' stop-color='#2a313c'/><stop offset='.65' stop-color='#141922'/><stop offset='1' stop-color='#07090d'/></radialGradient>"
            "<linearGradient id='lumen' x1='0' x2='1'><stop offset='0' stop-color='#9fb0c6'/><stop offset='.5' stop-color='#f4f8ff'/><stop offset='1' stop-color='#9fb0c6'/></linearGradient>"
            "<filter id='b3'><feGaussianBlur stdDeviation='3.2'/></filter><filter id='b16'><feGaussianBlur stdDeviation='16'/></filter><filter id='b1'><feGaussianBlur stdDeviation='.8'/></filter>"
            "<filter id='grain'><feTurbulence type='fractalNoise' baseFrequency='.85' numOctaves='2' seed='3'/><feColorMatrix values='0 0 0 0 1 0 0 0 0 1 0 0 0 0 1 0 0 0 .07 0'/></filter></defs>"
            f"<g id='film'><rect width='{W}' height='{H}' fill='url(#bg)'/><ellipse cx='380' cy='360' rx='300' ry='330' transform='rotate(-14 380 360)' fill='#ffffff' opacity='.05' filter='url(#b16)'/>"
            f"<ellipse cx='{X(188):.0f}' cy='{Y(30):.0f}' rx='78' ry='26' fill='#cfe0ff' opacity='.22' filter='url(#b3)'/></g>"
            f"<g id='vessels'><g filter='url(#b3)'>{glow}</g><path d='{cath}' fill='none' stroke='#dfe6f2' stroke-width='5' opacity='.85' filter='url(#b1)'/><g filter='url(#b1)'>{vess}</g><g fill='#fff8d6' opacity='.95'>{ca}</g></g>"
            f"<g id='labels' font-family='Helvetica,Arial,sans-serif'><g font-size='12' fill='#8fa1bf'>{nums}</g><g font-size='15' font-weight='600' fill='#cdd9ee'>{names}</g></g>"
            f"<g id='lesions' font-family='Helvetica,Arial,sans-serif'>{les}</g>"
            + ("<text x='16' y='704' font-family='Helvetica,Arial,sans-serif' font-size='12' fill='#8fa1bf'>Synthetic diagram · AHA segment numbers · right-dominant · anterior view · not to scale · not an image of any patient</text>" if title else "") + "</svg>")

if __name__ == "__main__":
    import plan
    if len(sys.argv) < 2: sys.exit(__doc__)
    s = svg(plan.lesions(plan.packet(sys.argv[1])))
    if len(sys.argv) > 2: open(sys.argv[2], "w").write(s); print(sys.argv[2])
    else: print(s)
