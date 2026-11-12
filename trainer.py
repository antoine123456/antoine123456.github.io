#!/usr/bin/env python3
"""
trainer.py — the trainer in a terminal (#215): the front of the card, you
type the back. Minimal on purpose: no sound, no pictures, plain text.

Progress is the same as the web app's: read from and written to Firestore
(users/<name>/sources/<deck>, field srs.<card id>), card after card, with the
same scheduler (Anki's: learning steps 1m / 10m, then days). Card content
comes from the deck JSON files of this folder (and from Firestore for decks
you made yourself, like 📝 Vocabulaire perso). The first time, you pick who
you are among the app's names (kept in ~/.config/espanol-trainer/trainer.json).

    python3 trainer.py              # list the decks, pick one
    python3 trainer.py vocab        # the first deck whose name has « vocab »
    python3 trainer.py vocab -d "Niveau 2"   # only the sub-decks with « Niveau 2 »
    python3 trainer.py vocab -n 10  # at most 10 new cards today (default 20)
    python3 trainer.py --dry        # write nothing (try it out)
    python3 trainer.py --user       # pick the name again

During a card: type the answer, Entrée. Right = Correct, next card; wrong =
try again, three tries, then the answer and À revoir. Formulas and turned-over
cards: Entrée turns it over, then Entrée = knew it, n = didn't. Pictures
aren't shown (a card with only a picture isn't asked). q (or Ctrl-D) stops:
what's done is already saved.
The web app picks these reviews up when it reloads (the most recent review
of a card wins); reload its tab after a terminal session.
"""
import argparse
import html
import json
import os
import random
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request

try:
    import readline  # noqa: F401 — arrow keys and history in input()
except ImportError:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
API_KEY = "AIzaSyDMn9fYdjo3rpo2k1Q89pQ2dsIi12c0kJk"  # public, same as index.html
BASE = "https://firestore.googleapis.com/v1/projects/type-in-anki/databases/(default)/documents"
USER = None  # chosen at first use (setup())
CONFIG = os.path.expanduser("~/.config/espanol-trainer/trainer.json")
HIDDEN_USERS = {"fantome"}  # the app's ghost (read-only view)
DAY = 86400000
TODAY = int(time.time() * 1000) // DAY  # same day number as the app's dayStamp()

# ── Firestore REST ──────────────────────────────────────────────

def from_fs(v):
    if "mapValue" in v:
        return {k: from_fs(x) for k, x in (v["mapValue"].get("fields") or {}).items()}
    if "arrayValue" in v:
        return [from_fs(x) for x in v["arrayValue"].get("values") or []]
    if "integerValue" in v:
        return int(v["integerValue"])
    if "doubleValue" in v:
        return v["doubleValue"]
    if "nullValue" in v:
        return None
    for k in ("stringValue", "booleanValue", "timestampValue"):
        if k in v:
            return v[k]
    return None


def to_fs(x):
    if x is None:
        return {"nullValue": None}
    if isinstance(x, bool):
        return {"booleanValue": x}
    if isinstance(x, int):
        return {"integerValue": str(x)}
    if isinstance(x, float):
        return {"integerValue": str(int(x))} if x.is_integer() else {"doubleValue": x}
    if isinstance(x, str):
        return {"stringValue": x}
    if isinstance(x, (list, tuple)):
        return {"arrayValue": {"values": [to_fs(y) for y in x]}}
    return {"mapValue": {"fields": {k: to_fs(y) for k, y in x.items()}}}


def fs(method, path, params=(), body=None):
    q = urllib.parse.urlencode([("key", API_KEY)] + list(params))
    url = BASE + "/" + "/".join(urllib.parse.quote(p, safe="") for p in path.split("/")) + "?" + q
    req = urllib.request.Request(url, method=method, headers={"Content-Type": "application/json"},
                                 data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def get_doc(path):
    d = fs("GET", path)
    return from_fs({"mapValue": d}) if d else {}


def field_path(*parts):
    """srs.`1100000000011` — card ids are digits, quoted to be safe."""
    return ".".join(p if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", p)
                    else "`" + p.replace("\\", "\\\\").replace("`", "\\`") + "`" for p in parts)


def save_review(sid, cid, s, new_count, dry):
    if dry:
        return
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    body = {"fields": {"srs": to_fs({cid: s}), "newCount": to_fs(new_count), "updatedAt": {"timestampValue": now}}}
    mask = [("updateMask.fieldPaths", field_path("srs", cid)), ("updateMask.fieldPaths", "newCount"),
            ("updateMask.fieldPaths", "updatedAt")]
    fs("PATCH", "users/%s/sources/%s" % (USER, sid), mask, body)

# ── cards ───────────────────────────────────────────────────────

def bundled_files():
    """Deck id → JSON file, read from index.html's EXTRA_BUNDLED (+ default)."""
    src = open(os.path.join(HERE, "index.html"), encoding="utf-8").read()
    m = re.search(r"var EXTRA_BUNDLED = \[(.*?)\];", src, re.S)
    out = {"default": "default.json"}
    for url, id_ in re.findall(r'url:\s*"([^"]+)",\s*id:\s*"([^"]+)"', m.group(1) if m else ""):
        out[id_] = url
    return out


def load_cards(sid, files):
    """{deck id: [cards]} and {deck id: name}."""
    if sid in files and os.path.exists(os.path.join(HERE, files[sid])):
        data = json.load(open(os.path.join(HERE, files[sid]), encoding="utf-8"))
        by, names = {}, {}
        for i, d in enumerate(data.get("decks") or []):
            did = str(d.get("id", i))
            by[did], names[did] = d.get("cards") or [], d.get("name", did)
        return by, names
    # a deck made in the app: its cards are in Firestore, in chunks
    chunks = fs("GET", "users/%s/sources/%s/cardChunks" % (USER, sid), [("pageSize", 300)]) or {}
    parts = sorted((from_fs({"mapValue": d}) for d in chunks.get("documents") or []), key=lambda c: c.get("index", 0))
    by = json.loads("".join(p.get("data", "") for p in parts) or "{}")
    return by, {did: did for did in by}


def plain(h):
    h = re.sub(r"(?is)<style.*?</style>|<script.*?</script>", "", str(h or ""))
    h = re.sub(r"(?is)<sup>(.*?)</sup>", lambda m: "^" + (m.group(1) if len(m.group(1)) == 1 else "(" + m.group(1) + ")"), h)
    h = re.sub(r"(?is)<sub>(.*?)</sub>", r"_\1", h)
    h = re.sub(r"(?i)<br\s*/?>|</(div|p|li|tr|h\d)>", "\n", h)
    h = html.unescape(re.sub(r"<[^>]+>", "", h))
    lines = [re.sub(r"[ \t ]+", " ", l).strip() for l in h.split("\n")]
    return "\n".join(l for l in lines if l)


def squash(s):
    """Letters and digits only, no accents — like the app's squashWord()."""
    s = unicodedata.normalize("NFD", str(s).lower())
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return re.sub(r"[\W_]+", "", s)


def natural(s):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]

# ── scheduler (same as applyRating() in index.html) ─────────────

def default_srs():
    return {"state": "new", "step": 0, "interval": 0, "ease": 2.5, "due": TODAY, "reps": 0, "lapses": 0, "easyCount": 0}


def apply_rating(srs, q):
    s, requeue = dict(srs), None
    s["reps"] = s.get("reps", 0) + 1
    if q == 4:
        s["easyCount"] = s.get("easyCount", 0) + 1
    if s["state"] == "new":
        s["state"] = "learning"
    if s["state"] == "learning":
        if q == 1:
            s["step"], requeue = 0, 1
        elif q == 2:
            s["step"], requeue = 1, 6
        elif q == 4:
            s["ease"] = min(4.0, s["ease"] + 0.15)
            s.update(state="review", step=0, interval=4, due=TODAY + 4)
        elif s.get("step", 0) == 0:
            s["step"], requeue = 1, 10
        else:
            s.update(state="review", step=0, interval=1, due=TODAY + 1)
    elif s["state"] == "relearning":
        if q == 1:
            s["ease"], requeue = max(1.3, s["ease"] - 0.2), 1
        elif q == 2:
            requeue = 6
        elif q == 3:
            s.update(state="review", interval=1, due=TODAY + 1)
        else:
            s["ease"] = min(4.0, s["ease"] + 0.15)
            s.update(state="review", interval=4, due=TODAY + 4)
    else:
        iv = s.get("interval", 1)
        if q == 1:
            s["lapses"] = s.get("lapses", 0) + 1
            s["ease"], s["state"], requeue = max(1.3, s["ease"] - 0.2), "relearning", 1
        elif q == 2:
            s["ease"] = max(1.3, s["ease"] - 0.15)
            s["interval"] = max(iv + 1, round(iv * 1.2))
        elif q == 3:
            s["interval"] = max(1, round(iv * s["ease"]))
        else:
            s["ease"] = min(4.0, s["ease"] + 0.15)
            s["interval"] = max(1, round(iv * s["ease"] * 1.5))
        if q > 1:
            s["due"] = TODAY + s["interval"]
    return s, requeue

# ── terminal ────────────────────────────────────────────────────

C = sys.stdout.isatty()
def col(code, t): return "\033[%sm%s\033[0m" % (code, t) if C else t
DIM, BOLD, GREEN, RED, CYAN = "2", "1", "32", "31", "36"


def ask(prompt):
    try:
        return input(prompt)
    except EOFError:
        print()
        return None


def setup(again=False):
    """Who are you? Asked the first time (or with --user), then remembered."""
    try:
        cfg = json.load(open(CONFIG))
    except Exception:
        cfg = {}
    if cfg.get("user") and not again:
        return cfg["user"]
    res = fs("GET", "users", [("pageSize", 100), ("mask.fieldPaths", "updatedAt")]) or {}
    names = sorted(d["name"].rsplit("/", 1)[-1] for d in res.get("documents") or [])
    names = [n for n in names if n not in HIDDEN_USERS]
    if not names:
        sys.exit("Personne dans Firestore : ouvrez d'abord l'app une fois.")
    print("Qui révise ?")
    for i, n in enumerate(names, 1):
        print("%2d  %s" % (i, n))
    a = ask("Numéro ? ")
    if not a or not a.strip().isdigit() or not 1 <= int(a) <= len(names):
        sys.exit()
    cfg["user"] = names[int(a) - 1]
    os.makedirs(os.path.dirname(CONFIG), exist_ok=True)
    json.dump(cfg, open(CONFIG, "w"))
    print(col(DIM, "→ %s (gardé dans %s ; --user pour changer)" % (cfg["user"], CONFIG)))
    return cfg["user"]


def build_queue(by, names, srs, flagged, deck_filter, new_left):
    dids = sorted((d for d in by if not deck_filter or deck_filter.lower() in names.get(d, d).lower()),
                  key=lambda d: natural(names.get(d, d)))
    cards = [c for d in dids for c in by[d] if str(c.get("id")) not in flagged
             and front_of(c)]  # a picture alone can't be shown here
    seen = lambda i: i in srs and srs[i].get("state") != "new"
    due, new = [], []
    for c in cards:
        s = srs.get(str(c["id"]))
        if not s or s.get("state") == "new":
            if all(seen(str(p)) for p in c.get("pre") or []):
                new.append(c)
        elif s["state"] in ("learning", "relearning") or s.get("due", 0) <= TODAY:
            due.append(c)
    random.shuffle(due)
    new = new[:new_left]
    random.shuffle(new)
    return due + new


def ind(t):
    """Indented by two spaces, every line: the question reads whole, away from the edge."""
    return "\n".join("  " + l for l in str(t).split("\n"))


def front_of(card):
    return plain(card.get("question")) or card.get("es") or ""


def review(card, s):
    """Shows one card, returns 3 (Correct) or 1 (À revoir), or None to stop.
    Three tries; a card that can't be typed (formula, turned over) is
    turned over and you say if you knew it."""
    raw = card.get("words") or []
    sep = set(card.get("sep") or [])
    shown = " ".join(("/ " if k in sep and k else "") + str(w) for k, w in enumerate(raw) if str(w).strip())
    words = [w for w in raw if str(w).strip()]
    # alternatives (« toi / à toi / te »): any one of them is right, or all of them
    groups, cur = [], []
    for k, w in enumerate(raw):
        if k in sep and cur:
            groups.append(cur)
            cur = []
        if str(w).strip():
            cur.append(str(w))
    groups.append(cur)
    right = {squash(" ".join(g)) for g in groups if g} | {squash(" ".join(words))}
    back = plain(card.get("answer")) or shown
    flip = card.get("flip") or card.get("eq") or not words
    print()
    print(col(BOLD, ind(front_of(card))))
    if flip:
        if ask(col(DIM, "  Entrée = retourner ")) is None:
            return None
        print(col(CYAN, ind(back)))
        r = ask(col(DIM, "  su ? Entrée = oui · n = non "))
        if r is None or r.strip() == "q":
            return None
        return 1 if r.strip().lower() in ("n", "non", "1") else 3
    k = 0
    while k < 3:
        a = ask("  › ")
        if a is None or a.strip() == "q":
            return None
        if not squash(a):
            continue  # Entrée alone doesn't use a try
        if squash(a) in right:
            print(col(GREEN, "  ✓ " + shown))
            return 3
        k += 1  # not accepted: just asked again (no ✗)
    print(col(CYAN, "  " + shown))
    if back and squash(back) != squash(" ".join(words)):
        print(col(DIM, ind(back)))
    # then wiped, scrollback too: the card comes back soon, the answer mustn't be there to copy
    if ask(col(DIM, "  Entrée ")) is None:
        return None
    if C:
        sys.stdout.write("\033[H\033[2J\033[3J")
        sys.stdout.flush()
    return 1


def main():
    ap = argparse.ArgumentParser(description="Réviser dans le terminal (même progression que l'app).")
    ap.add_argument("deck", nargs="?", help="un bout du nom du paquet (sinon : la liste)")
    ap.add_argument("-d", "--sub", help="seulement les sous-paquets dont le nom contient ce texte")
    ap.add_argument("-n", "--new", type=int, default=20, help="nouvelles cartes par jour (20)")
    ap.add_argument("--dry", action="store_true", help="ne rien écrire dans Firestore")
    ap.add_argument("--user", action="store_true", help="choisir à nouveau qui révise")
    args = ap.parse_args()
    global USER
    USER = setup(args.user)

    user = get_doc("users/" + USER)
    sources = [s for s in user.get("sources") or [] if s.get("id") != "test-transitions"]
    asleep = set((user.get("asleep") or {}).get("ids") or [])
    files = bundled_files()
    if not sources:
        sys.exit("Rien dans Firestore pour « %s »." % USER)
    if args.deck:
        pick = [s for s in sources if args.deck.lower() in s["name"].lower() or args.deck == s["id"]]
        if not pick:
            sys.exit("Aucun paquet ne contient « %s »." % args.deck)
        src = pick[0]
    else:
        for i, s in enumerate(sources, 1):
            print("%2d  %s%s" % (i, s["name"], col(DIM, "  💤") if s["id"] in asleep else ""))
        a = ask("Paquet ? ")
        if not a or not a.strip().isdigit() or not 1 <= int(a) <= len(sources):
            return
        src = sources[int(a) - 1]

    sid = src["id"]
    meta = get_doc("users/%s/sources/%s" % (USER, sid))
    srs = meta.get("srs") or {}
    flagged = set((meta.get("flagged") or {}).keys())
    nc = meta.get("newCount") or {}
    nc = nc if nc.get("day") == TODAY else {"day": TODAY, "count": 0}
    by, names = load_cards(sid, files)
    for cid, e in (meta.get("edits") or {}).items():  # cards changed in 📝 Relecture
        for cards in by.values():
            for c in cards:
                if str(c.get("id")) == cid:
                    c.update((e or {}).get("f") or {})
    queue = build_queue(by, names, srs, flagged, args.sub, max(0, args.new - nc["count"]))
    n_new = sum(1 for c in queue if str(c["id"]) not in srs or srs[str(c["id"])].get("state") == "new")
    print(col(BOLD, "%s" % src["name"]) + col(DIM, " — %d à revoir, %d nouvelles%s" % (
        len(queue) - n_new, n_new, " (essai : rien n'est écrit)" if args.dry else "")))
    if not queue:
        print("Rien à réviser aujourd'hui 🎉")
        return

    done, t_start = 0, time.time()
    while queue:
        card = queue.pop(0)
        cid = str(card["id"])
        before = srs.get(cid)
        t0 = time.time()
        q = review(card, before)
        if q is None:
            break
        was_new = before is None or before.get("state") == "new"
        s, requeue = apply_rating(before or default_srs(), q)
        s["lastReview"] = int(time.time() * 1000)  # the most recent review wins in the app's merge
        ms = min(60000, int((time.time() - t0) * 1000))
        s["ms"] = round(s["ms"] * 0.7 + ms * 0.3) if s.get("ms") else ms
        srs[cid] = s
        if was_new:
            nc["count"] += 1
        try:
            save_review(sid, cid, s, nc, args.dry)
        except Exception as e:  # keep going; say it
            print(col(RED, "  ⚠ pas enregistré : %s" % e))
        done += 1
        if requeue:  # learning step: back a few cards later (as in the app)
            queue.insert(min(len(queue), requeue), card)
    mins = (time.time() - t_start) / 60
    print()
    print(col(DIM, "%d carte(s) en %.0f min%s" % (done, mins, "" if args.dry else " — enregistré dans Firestore")))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
