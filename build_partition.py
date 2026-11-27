#!/usr/bin/env python3
"""Build partition.json: reading notes on a staff (🎼 Partition).

One card = one note drawn on a staff (inline SVG, currentColor so it follows
the light / dark theme); you type its name (do, ré, mi…, « fa dièse »).
Levels are numbered decks (« Niveau 1 »…), so each one opens once 80 % of
the one before is learnt, like the other bundled decks.

Clef and accidental outlines come from GNU FreeSerif (GPL with the font
exception: embedding glyphs in a document is allowed). Run:
    python3 build_partition.py            (needs fonttools)
"""
import json
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen

FONT = "/usr/share/fonts/truetype/freefont/FreeSerif.ttf"
_f = TTFont(FONT)
_gs, _cmap = _f.getGlyphSet(), _f.getBestCmap()


def glyph(ch):
    pen = SVGPathPen(_gs)
    _gs[_cmap[ord(ch)]].draw(pen)
    return pen.getCommands()


G_CLEF, F_CLEF = glyph("\U0001D11E"), glyph("\U0001D122")
SHARP, FLAT = glyph("♯"), glyph("♭")

LETTERS = "CDEFGAB"
FR = {"C": "do", "D": "ré", "E": "mi", "F": "fa", "G": "sol", "A": "la", "B": "si"}
ACC_FR = {"#": "dièse", "b": "bémol"}
ACC_SIGN = {"#": "♯", "b": "♭"}

# Staff: 5 lines, 10 units apart, bottom line at y = 80; one step = 5.
TOP, BOTTOM, STEP = 40, 80, 5
CLEFS = {
    # bottom line, clef outline, scale, origin (x, y) of the glyph
    "sol": {"bottom": "E4", "path": G_CLEF, "k": 0.0663, "x": -3, "y": 76.7, "name": "clé de sol"},
    "fa": {"bottom": "G2", "path": F_CLEF, "k": 0.0575, "x": 2, "y": 82.5, "name": "clé de fa"},
}


def diat(n):  # "E4" → diatonic index
    return int(n[-1]) * 7 + LETTERS.index(n[0])


def pos(note, clef):  # steps above the bottom line (0 = on it)
    return diat(note) - diat(CLEFS[clef]["bottom"])


def where(p):
    """Plain French: where the note sits."""
    if 0 <= p <= 8:
        return ("%de ligne" % (p // 2 + 1) if p % 2 == 0 else "%de interligne" % (p // 2 + 1)).replace("1e", "1re")
    if p == -1:
        return "sous la portée"
    if p == 9:
        return "au-dessus de la portée"
    if p < 0:
        n = (-p) // 2
        return ("%de ligne supplémentaire en dessous" % n if p % 2 == 0 else "sous la %de ligne supplémentaire" % n).replace("1e", "1re")
    n = (p - 8) // 2
    return ("%de ligne supplémentaire au-dessus" % n if p % 2 == 0 else "sur la %de ligne supplémentaire" % n).replace("1e", "1re")


def oval(rx, ry, deg, n=24):
    import math
    a = math.radians(deg)
    pts = []
    for i in range(n):
        t = 2 * math.pi * i / n
        x, y = rx * math.cos(t), ry * math.sin(t)
        pts.append("%.2f %.2f" % (x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a)))
    return "M" + "L".join(pts) + "Z"


def svg(note, clef, acc=""):
    c = CLEFS[clef]
    p = pos(note, clef)
    y = BOTTOM - p * STEP
    nx = 78
    parts = ['<svg class="pt-staff" viewBox="0 8 120 102" width="300" height="255" role="img" aria-label="note">']
    for i in range(5):
        ly = TOP + i * 10
        parts.append('<line x1="4" x2="116" y1="%d" y2="%d"/>' % (ly, ly))
    # ledger lines
    for lp in range(-2, p - 1, -2) if p <= -2 else range(10, p + 1, 2) if p >= 10 else []:
        ly = BOTTOM - lp * STEP
        parts.append('<line class="pt-ledger" x1="%g" x2="%g" y1="%g" y2="%g"/>' % (nx - 11, nx + 11, ly, ly))
    parts.append('<path class="pt-glyph" transform="translate(%g %g) scale(%g %g)" d="%s"/>' % (c["x"], c["y"], c["k"], -c["k"], c["path"]))
    if acc:
        k = 0.03
        d = SHARP if acc == "#" else FLAT
        oy = y + (6.5 if acc == "#" else 4)  # glyph baseline: the sharp centred, the flat's bowl on the note
        parts.append('<path class="pt-glyph" transform="translate(%g %g) scale(%g %g)" d="%s"/>' % (nx - 20, oy, k, -k, d))
    # whole note: an oval ring (outer oval tilted a little, the hole tilted more)
    parts.append('<g class="pt-glyph" transform="translate(%g %g)"><path fill-rule="evenodd" d="%s %s"/></g>' % (nx, y, oval(7, 5, -12), oval(3.4, 3.6, -50)))
    parts.append("</svg>")
    return "".join(parts)


STYLE = ("<style>.pt{display:flex;flex-direction:column;align-items:center;gap:4px}"
         ".pt-staff{max-width:100%;max-height:30vh;width:auto;height:auto;color:inherit}"
         ".pt-staff line{stroke:currentColor;stroke-width:1}"
         ".pt-staff .pt-ledger{stroke-width:1.2}"
         ".pt-staff .pt-glyph{fill:currentColor}"
         ".pt-q{font-size:15px;opacity:.6}</style>")


def card(cid, note, clef, tags, acc=""):
    name = FR[note[0]] + (" " + ACC_FR[acc] if acc else "")
    words = name.split()
    eng = note[0] + ACC_SIGN.get(acc, "") + note[-1]
    p = pos(note, clef)
    info = "%s · %s · %s (%s)" % (name, eng, where(p), CLEFS[clef]["name"])
    if note == "C4":
        info += " — le do du milieu du piano"
    c = {"id": str(cid), "question": STYLE + '<div class="pt">' + svg(note, clef, acc) + '</div>',
         "answer": name, "words": words, "tags": tags, "info": info}
    c["wheel"] = 1  # answered on a wheel of notes (#283)
    if acc:
        c["alt"] = [FR[note[0]] + ACC_SIGN[acc], FR[note[0]] + acc]
        c["wheelAcc"] = 1  # ♯ / ♭ in the middle of the wheel
    return c


def notes(lo, hi):
    out = []
    for d in range(diat(lo), diat(hi) + 1):
        out.append(LETTERS[d % 7] + str(d // 7))
    return out


LEVELS = [
    ("Niveau 1", "Clé de sol, sur la portée", "sol", notes("D4", "G5"), ["clé de sol", "portée"], ""),
    ("Niveau 2", "Clé de sol, lignes supplémentaires", "sol", notes("A3", "C4") + notes("A5", "D6"), ["clé de sol", "lignes supplémentaires"], ""),
    ("Niveau 3", "Clé de fa, sur la portée", "fa", notes("F2", "B3"), ["clé de fa", "portée"], ""),
    ("Niveau 4", "Clé de fa, lignes supplémentaires", "fa", notes("C2", "E2") + notes("C4", "E4"), ["clé de fa", "lignes supplémentaires"], ""),
]
# Level 5: sharps and flats, clé de sol on the staff (the usual ones of the keys)
ACC_NOTES = [("F4", "#"), ("C5", "#"), ("G4", "#"), ("D5", "#"), ("A4", "#"), ("F5", "#"),
             ("B4", "b"), ("E4", "b"), ("A4", "b"), ("D5", "b"), ("G4", "b"), ("E5", "b")]


def build():
    decks, n = [], 0
    for i, (lvl, title, clef, ns, tags, _) in enumerate(LEVELS, 1):
        cards = []
        for note in ns:
            n += 1
            cards.append(card(2611000000000 + n, note, clef, tags + ["niveau %d" % i]))
        decks.append({"id": "partition-%d" % i, "name": "🎼 Partition::" + lvl, "cards": cards})
    cards = []
    for note, acc in ACC_NOTES:
        n += 1
        cards.append(card(2611000000000 + n, note, "sol", ["clé de sol", "altérations", "niveau 5"], acc))
    decks.append({"id": "partition-5", "name": "🎼 Partition::Niveau 5", "cards": cards})
    return {"version": 1, "source": "🎼 Partition", "decks": decks}


if __name__ == "__main__":
    data = build()
    with open("partition.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(sum(len(d["cards"]) for d in data["decks"]), "cartes,", len(data["decks"]), "niveaux")
