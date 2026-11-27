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

The deck reviewed last (in the app or here) is the default in the list: Entrée takes it.
During a card: type the answer, Entrée (« ? » = show the answer, À revoir;
« dump » = the whole list left, cards and answers; « stats » = the cards
left; « save » = saved (it already is, card after card); « info » = the
keywords and a short guide). After a miss, « + » adds
what you typed to the card's answers (or « + another meaning »): the card
counts as Correct, and that answer is accepted from then on, on every device. After a missed card, the
cards left are shown on top: new · learning · review (blue · red · green). Right = Correct, next card; wrong =
try again, three tries, then the answer and À revoir. Formulas and turned-over
cards: Entrée turns it over, then Entrée = knew it, n = didn't. Pictures
aren't shown (a card with only a picture isn't asked). q (or Ctrl-D) stops:
what's done is already saved.
The web app picks these reviews up when it reloads (the most recent review
of a card wins); reload its tab after a terminal session.
"""
import argparse
import builtins
import calendar
import html
import json
import os
import re
import shutil
import sys
import time
import unicodedata
import urllib.parse
import urllib.request

try:
    import readline  # noqa: F401 — arrow keys and history in input()
except ImportError:
    pass

HERE = os.path.dirname(os.path.realpath(__file__))  # through the ankiterm link too
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
DIM, BOLD, GREEN, RED, CYAN, BLUE, YELLOW = "2", "1", "32", "31", "36", "34", "33"


# Lines written so far (#242): a missed card comes back only once its answer
# has scrolled out of the window, instead of the screen being wiped.
LINES = 0
ANSI = re.compile(r"\033\[[0-9;]*m")


def rows(text):
    """Terminal rows taken by the finished lines of text (long ones wrap)."""
    cols = max(20, shutil.get_terminal_size((80, 24)).columns)
    return sum(max(1, -(-len(ANSI.sub("", l)) // cols)) for l in text.split("\n")[:-1])


def print(*a, sep=" ", end="\n", **k):  # the built-in one, counting the rows
    global LINES
    builtins.print(*a, sep=sep, end=end, **k)
    if k.get("file") in (None, sys.stdout):
        LINES += rows(sep.join(map(str, a)) + end)


# Time really spent on the card (#263): each wait for an answer counts 60 s at most —
# a break while the card is up doesn't count — and nothing during « :p » (pause).
SPENT, IDLE_CAP = 0.0, 60


def ask(prompt, counted=True):
    global LINES, SPENT
    t = time.time()
    try:
        a = input(prompt)
    except EOFError:
        print()
        return None
    if counted:
        SPENT += min(IDLE_CAP, time.time() - t)
    LINES += rows(prompt + a + "\n")  # the echoed answer and Entrée
    return a


def out_of_sight(at):
    """Has what was written at line `at` left the window?"""
    return LINES - at >= shutil.get_terminal_size((80, 24)).lines


# A log of every card answered here (#263): ~/.config/espanol-trainer/log.tsv —
# when, deck, card, front, rating, when it comes back, seconds. « :log » shows
# today's cards, those seen several times first.
LOG = os.path.join(os.path.dirname(CONFIG), "log.tsv")
LOG_HEAD = "quand\tpaquet\tid\trecto\tnote\trevient\tsecondes\tavant\n"


def write_log(sid, card, q, s, requeue, spent, dry, before=None):
    if dry:
        return  # a try (--dry) writes nothing, not even here
    try:
        new = not os.path.exists(LOG)
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            if new:
                f.write(LOG_HEAD)
            back = "<%dm" % requeue if requeue else "%dj" % s.get("interval", 1)
            f.write("\t".join([time.strftime("%Y-%m-%d %H:%M:%S"), sid, str(card["id"]),
                                front_of(card).split("\n")[0][:60], {1: "À revoir", 2: "Difficile", 3: "Correct", 4: "Facile"}[q],
                                back, "%.0f" % spent,
                                # where it stood before (#273): nouvelle, apprentissage, or its interval « 4j »
                                {"new": "nouvelle", "learn": "apprentissage"}.get(state_of(before), "%dj" % (before or {}).get("interval", 0))]) + "\n")
    except OSError:
        pass


def log_today(sid):
    """Today's cards of this deck in the log, those seen several times first."""
    today, seen = time.strftime("%Y-%m-%d"), {}
    try:
        for line in open(LOG, encoding="utf-8").read().splitlines()[1:]:
            f = line.split("\t")
            if len(f) >= 6 and f[0].startswith(today) and f[1].split(" ")[0] == sid:
                seen.setdefault(f[2], [f[3], []])[1].append(f[4])
    except OSError:
        return col(DIM, "  pas encore de journal")
    if not seen:
        return col(DIM, "  rien aujourd'hui dans ce paquet")
    rows_ = sorted(seen.values(), key=lambda v: -len(v[1]))
    out = [col(DIM, "  aujourd'hui : %d cartes, %d réponses — %s" % (len(seen), sum(len(v[1]) for v in rows_), LOG))]
    for front, notes in rows_[:15]:
        out.append("  %2d×  %-34s %s" % (len(notes), front[:34], col(DIM, " · ".join(notes))))
    return "\n".join(out)


def journal(days=14):
    """ankiterm --journal (P8, #273): day by day, from the terminal's log, to check the
    algorithm — answers and cards, new ones, how often a card came back the same day,
    the cards known before answered right the first time (Anki aims at 85–90 %), and
    the intervals given; then the cards due in the coming days, from Firestore."""
    try:
        rows_ = [l.split("\t") for l in open(LOG, encoding="utf-8").read().splitlines()[1:]]
    except OSError:
        return col(DIM, "pas encore de journal (%s) : il se remplit en révisant ici" % LOG)
    by_day = {}
    for f in rows_:
        if len(f) >= 7:
            by_day.setdefault(f[0][:10], []).append(f)
    bucket = lambda b: ("<1j" if b.startswith("<") else "1-3j" if int(b[:-1]) <= 3 else "4-10j" if int(b[:-1]) <= 10
                        else "11-30j" if int(b[:-1]) <= 30 else ">30j")
    out = [col(BOLD, "jour        réponses cartes nouv. ×/carte  1er coup  min   intervalles donnés (<1j 1-3j 4-10j 11-30j >30j)")]
    for day in sorted(by_day)[-days:]:
        fs_ = by_day[day]
        first, cards = {}, {}
        for f in fs_:
            first.setdefault(f[2], f)
            cards[f[2]] = cards.get(f[2], 0) + 1
        new = sum(1 for f in first.values() if len(f) > 7 and f[7] == "nouvelle")
        # known before: an interval in « avant » (lines from before #273 have none: every first answer)
        known = [f for f in first.values() if len(f) <= 7 or f[7].endswith("j")]
        ok = sum(1 for f in known if f[4] != "À revoir")
        ivs = [0] * 5
        for f in fs_:
            if re.match(r"^(<\d+m|\d+j)$", f[5]):
                ivs[("<1j", "1-3j", "4-10j", "11-30j", ">30j").index(bucket(f[5]))] += 1
        mins = sum(min(60, float(f[6] or 0)) for f in fs_) / 60
        out.append("%s  %8d %6d %5s %7.1f  %7s  %4.0f   %s" % (
            day, len(fs_), len(cards), new if any(len(f) > 7 for f in fs_) else "–", len(fs_) / len(cards),
            "%d %%" % round(100 * ok / len(known)) if known else "–", mins, "  ".join("%4d" % n for n in ivs)))
    out.append(col(DIM, "×/carte : réponses par carte (une carte ratée revient le jour même) · 1er coup : cartes déjà connues "
                        "trouvées à leur 1re réponse du jour, Anki vise 85–90 %% · le journal : %s" % LOG))
    return "\n".join(out)


def due_ahead(srs, days=14):
    """Cards due on each of the coming days (review cards), from today's progress."""
    n = [0] * days
    for x in srs.values():
        if isinstance(x, dict) and x.get("state") == "review":
            d = max(0, int(x.get("due", TODAY)) - TODAY)
            if d < days:
                n[d] += 1
    return "à venir (vocabulaire, cartes dues) : " + " ".join(
        "%s %d" % ("auj." if i == 0 else "+%d" % i, k) for i, k in enumerate(n))


def load_cfg():
    try:
        return json.load(open(CONFIG))
    except Exception:
        return {}


def save_cfg(cfg):
    os.makedirs(os.path.dirname(CONFIG), exist_ok=True)
    json.dump(cfg, open(CONFIG, "w"))


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
    save_cfg(cfg)
    print(col(DIM, "→ %s (gardé dans %s ; --user pour changer)" % (cfg["user"], CONFIG)))
    return cfg["user"]


# ── same order as the app (#224) ───────────────────────────────
# startStudy() in index.html: due cards sorted by id then shuffled, new ones
# taken in deck order and shuffled, both with a seed drawn from the day and
# the deck. The same draw here, so the card the app shows is the one the
# terminal shows: start on one, finish on the other.
M32 = 0xFFFFFFFF


def imul(a, b):
    return (a * b) & M32


def day_seed(key):
    """daySeed(): FNV-1a over the UTF-16 code units of « TODAY|key »."""
    h = 2166136261
    b = (str(TODAY) + "|" + key).encode("utf-16-le")
    for i in range(0, len(b), 2):
        h = imul(h ^ (b[i] | b[i + 1] << 8), 16777619)
    return h


def seeded_shuffle(a, seed):
    """shuffle(a, seed): Fisher–Yates with the app's mulberry32."""
    x = seed & M32

    def rnd():
        nonlocal x
        x = (x + 0x6D2B79F5) & M32
        t = imul(x ^ (x >> 15), x | 1)
        t ^= (t + imul(t ^ (t >> 7), t | 61)) & M32
        return ((t ^ (t >> 14)) & M32) / 4294967296

    for i in range(len(a) - 1, 0, -1):
        j = int(rnd() * (i + 1))
        a[i], a[j] = a[j], a[i]
    return a


STAGE_UNLOCK_RATIO = 0.8


def locked_new_ids(by, names, srs, flagged):
    """lockedNewIds(): the new cards of a later stage (« Espagnol 3 » after
    « Espagnol 2 », or the tag etapeN) wait until 80 % of the stage before is known."""
    chains, groups, deck_stage = {}, {}, {}
    for did, name in names.items():
        k = name.rfind("::")
        if k < 0:
            continue
        m = re.match(r"^(.*?)\s*(\d+)$", name[k + 2:])
        if not m or not m.group(1):
            continue
        groups.setdefault(name[:k] + "::" + m.group(1), []).append((did, int(m.group(2))))
    for key, xs in groups.items():
        if len(xs) >= 2:
            for did, n in xs:
                deck_stage[did] = (key, n)
    for did, cards in by.items():
        for c in cards:
            cid = str(c.get("id"))
            if cid in flagged or c.get("rev"):
                continue
            m = re.search(r"(?:^| )etape(\d+)(?= |$)", " ".join(c.get("tags") or []), re.I)
            chain, n = ("#etape", int(m.group(1))) if m else deck_stage.get(did, (None, None))
            if chain is None:
                continue
            st = chains.setdefault(chain, {}).setdefault(n, {"done": 0, "total": 0, "fresh": []})
            x = srs.get(cid)
            st["total"] += 1
            if x and x.get("state") == "review":
                st["done"] += 1
            if not x or x.get("state") == "new":
                st["fresh"].append(cid)
    locked = set()
    for stages in chains.values():
        nums = sorted(stages)
        open_upto = nums[0]
        for n in nums:
            if n > open_upto:
                break
            if n == open_upto and stages[n]["done"] >= STAGE_UNLOCK_RATIO * stages[n]["total"]:
                open_upto += 1
        for n in nums:
            if n > open_upto:
                locked.update(stages[n]["fresh"])
    return locked


def js_natural_key(name):
    """naturalCompare(): localeCompare, numeric, case and accents ignored."""
    return [(0, int(t), "") if t.isdigit() else (1, 0, squash_keep(t)) for t in re.split(r"(\d+)", name)]


def squash_keep(t):
    t = unicodedata.normalize("NFD", t.lower())
    return "".join(ch for ch in t if unicodedata.category(ch) != "Mn")


def study_deck(names, deck_filter):
    """The deck the app starts from its home page: the top of the tree (or,
    with -d, the shortest deck path holding that text) — part of the seed."""
    paths = set()
    for n in names.values():
        parts = n.split("::")
        paths.update("::".join(parts[:i]) for i in range(1, len(parts) + 1))
    if deck_filter:
        hits = sorted((p for p in paths if deck_filter.lower() in p.lower()), key=len)
        return hits[0] if hits else None
    roots = {n.split("::")[0] for n in names.values()}
    return roots.pop() if len(roots) == 1 else None


def live_flags(fl):
    """The 🚩 cards still out: dropFixed() — a mark older than the card's fix
    (fixed.json, #200) no longer counts."""
    try:
        fixed = json.load(open(os.path.join(HERE, "fixed.json"), encoding="utf-8")).get("cards") or {}
    except Exception:
        fixed = {}
    out = set()
    for cid, v in fl.items():
        o = v if isinstance(v, dict) else {}
        f = fixed.get(cid)
        if f and not o.get("drop"):
            fixed_ms = calendar.timegm(time.strptime(f, "%Y-%m-%dT%H:%M:%SZ")) * 1000
            if (o.get("at") or 0) < fixed_ms:
                continue
        out.add(cid)
    return out


def last_reviewed(sources):
    """The deck with the most recent review (srs.lastReview), app or terminal."""
    from concurrent.futures import ThreadPoolExecutor

    def latest(src):
        try:
            srs = get_doc("users/%s/sources/%s" % (USER, src["id"])).get("srs") or {}
        except Exception:
            return 0, src["id"]
        return max(((v or {}).get("lastReview") or 0 for v in srs.values()), default=0), src["id"]
    with ThreadPoolExecutor(8) as ex:
        t, sid = max(ex.map(latest, sources), default=(0, None))
    return sid if t else None


def add_answer(sid, card, text, edits, dry):
    """Another accepted answer for this card (card.alt), saved as an edit like
    the app's 📝 Relecture ones (edits.<id> = {f, at}: the latest one wins), so
    every device has it."""
    cid = str(card["id"])
    f = dict((edits.get(cid) or {}).get("f") or {})
    f["alt"] = list(f.get("alt") or []) + [text]
    edits[cid] = {"f": f, "at": int(time.time() * 1000)}
    card["alt"] = f["alt"]
    if dry:
        return
    try:
        fs("PATCH", "users/%s/sources/%s" % (USER, sid), [("updateMask.fieldPaths", field_path("edits", cid))],
           {"fields": {"edits": to_fs({cid: edits[cid]})}})
    except Exception as e:
        print(col(RED, "  ⚠ pas enregistré : %s" % e))


def new_left(asked, introduced):
    """New cards still allowed today, as the app counts them (#239): its ⚙
    setting, synced in users/<user>.settings — by count, minus the ones
    already introduced today; in time mode, the number it worked out from the
    time left (newNow, today only). -n wins."""
    if asked is not None:
        return max(0, asked - introduced)
    st = get_doc("users/%s" % USER).get("settings") or {}
    global SLOW_S
    SLOW_S = int(st.get("slowSeconds", 30) or 0)  # ⚙ « trop lent », as in the app (#261)
    now = st.get("newNow") or {}
    if st.get("measure") == "time" and now.get("day") == TODAY:
        return max(0, int(now.get("n", 0)))
    return max(0, int(st.get("newPerDay", 20)) - introduced)


def twins(cards):
    """A card and its other direction (#269): the FR → ES card (rev) and the
    one it waits for (pre), both ways."""
    t = {}
    for c in cards:
        if c.get("rev") and len(c.get("pre") or []) == 1:
            t[str(c["id"])] = str(c["pre"][0])
            t[str(c["pre"][0])] = str(c["id"])
    return t


def resting(s):
    """New or day-scheduled: a card that can wait until tomorrow (#269) — not
    one in learning steps, which comes back in a few minutes anyway."""
    return not s or s.get("state", "new") in ("new", "review")


def bury_twins(queue, srs, twin):
    """As Anki buries siblings (#269): a card whose other direction was
    answered today, or is earlier in the queue, waits until tomorrow — « así
    que » then « donc » a minute later shows the answer of the other."""
    start, taken, out = day_start_ms(), set(), []
    for c in queue:
        i, t = str(c["id"]), twin.get(str(c["id"]))
        ts = srs.get(t) or {}
        today = ts.get("state", "new") != "new" and (ts.get("lastReview") or 0) >= start
        if t and resting(srs.get(i)) and (today or t in taken):
            continue
        taken.add(i)
        out.append(c)
    return out


def build_queue(by, names, srs, flagged, deck_name, new_left, sid):
    is_child = lambda n: deck_name is None or n == deck_name or n.startswith(deck_name + "::")
    dids = sorted((d for d in by if is_child(names.get(d, d))), key=lambda d: js_natural_key(names.get(d, d)))
    locked = locked_new_ids(by, names, srs, flagged)
    cards = [c for d in dids for c in by[d] if str(c.get("id")) not in flagged and str(c.get("id")) not in locked]
    seen = lambda i: i in srs and srs[i].get("state") != "new"
    due, new = [], []
    for c in cards:
        s = srs.get(str(c["id"]))
        if not s or s.get("state") == "new":
            if all(seen(str(p)) for p in c.get("pre") or []):
                new.append(c)
        elif s["state"] in ("learning", "relearning") or s.get("due", 0) <= TODAY:
            due.append(c)
    seed = day_seed(sid + "|" + (deck_name or "") + "|")
    due.sort(key=lambda c: str(c["id"]))  # JS string order (ids are digits, same length)
    seeded_shuffle(due, seed)
    # FR → ES cards (#221) every other place, as in the app
    fwd, rev = [c for c in new if not c.get("rev")], [c for c in new if c.get("rev")]
    new = [c for pair in zip(fwd, rev) for c in pair] + fwd[len(rev):] + rev[len(fwd):]
    new = seeded_shuffle(new[:new_left], seed + 1)
    return bury_twins(due + new, srs, twins(cards))


def ind(t):
    """Indented by two spaces, every line: the question reads whole, away from the edge."""
    return "\n".join("  " + l for l in str(t).split("\n"))


def front_of(card):
    return plain(card.get("question")) or card.get("es") or ""


def state_of(s):
    st = (s or {}).get("state", "new")
    return "new" if st == "new" else "learn" if st in ("learning", "relearning") else "review"


def time_left(queue, srs):
    """Minutes left, from each card's usual time (s.ms): a new card counts
    with its repeats (×3), a learning one ×1.5; no time yet = the median."""
    known = sorted(v["ms"] for v in srs.values() if isinstance(v, dict) and v.get("ms"))
    mid = known[len(known) // 2] if known else 15000
    tot = 0
    for c in queue:
        s = srs.get(str(c["id"])) or {}
        st = state_of(s)
        ms = mid if st == "new" else (s.get("ms") or mid)
        tot += ms * (3 if st == "new" else 1.5 if st == "learn" else 1)
    return tot / 60000


def counts_line(queue, srs):
    """New · learning · review left, blue · red · green, as under the app's
    cards, and the time left (« temps »)."""
    n = {"new": 0, "learn": 0, "review": 0}
    for c in queue:
        n[state_of(srs.get(str(c["id"])))] += 1
    m = time_left(queue, srs)
    t = "< 1 min" if m < 1 else "≈ %d min" % round(m)
    return "  " + " ".join(col(code, str(n[k])) for k, code in (("new", BLUE), ("learn", RED), ("review", GREEN))) + col(DIM, "  · " + t)


def answer_of(card):
    if card.get("flip"):  # turned over: what the back says, not the key words
        return plain(card.get("answer")).split("\n")[0]
    sep = set(card.get("sep") or [])
    return " ".join(("/ " if k in sep and k else "") + str(w) for k, w in enumerate(card.get("words") or []) if str(w).strip()) \
        or plain(card.get("answer")).replace("\n", " · ")


def dump(cards, srs):
    """« dump »: the whole review list left, card and answer."""
    for i, c in enumerate(cards, 1):
        st = state_of(srs.get(str(c["id"])))
        print(col(DIM, "  %3d " % i) + col({"new": BLUE, "learn": RED, "review": GREEN}[st], "●") + " "
              + front_of(c).replace("\n", " · ") + col(DIM, " → " + answer_of(c)))


INFO = """
  Réponds, puis Entrée.
  3 essais, puis la réponse.
  Notes comme dans l'app :
  du 1er coup (carte déjà vue)
  = Facile, juste = Correct,
  2 erreurs ou lent = Difficile,
  tableau ou réponse = À revoir.

  Mots-clés : « :mot » ou sa
  1re lettre (:t, :h…), pour
  ne pas les prendre pour une
  réponse ; les mots seuls
  marchent aussi.
  ?          la réponse
  +          après une erreur :
             mon sens était bon
             (+ autre sens : celui-là)
             en 1er sur la carte
             suivante : pour la
             carte ratée d'avant
  :t  tab    tableau du verbe
             (Grammaire ; la carte
             passe « à revoir »)
  :s  stats  cartes et temps
  :ti temps  restants
  :d  dump   toute la liste
  :p  pause  arrête le chrono
             (Entrée pour reprendre)
  :v mot     les détails d'un
             mot (sens, exemple, ≠,
             veo → ver, où il en est)
  :e [mot]   petit explorateur
             (Vocabulaire, Grammaire)
  :l  log    les cartes du jour
             (vues plusieurs fois
             en premier)
  :h  :i     cette aide
  :q  q      arrêter
  Entrée deux fois : la carte
  à nouveau.

  Défi : ankiterm --defi verbe
  (une minute, le plus de verbes).

  Ordre partagé avec l'app.
"""


# Conjugation table (#241), as F1 in the app (#53): the cards of the same verb
# and tense (tag « conjugaison », front « <b>verbe</b> … <i>personne</i> »),
# the stem they share plain, the ending in colour, this card's person marked.
CONJ_PERSONS = ["yo", "tú", "él / ella / usted", "nosotros", "vosotros", "ellos / ellas / ustedes"]


def conj_key(c):
    tags = c.get("tags") or []
    if "conjugaison" not in tags:
        return None
    q = str(c.get("question") or "")
    verb = (re.search(r"<b>([^<]+)</b>", q) or [None, None])[1]
    tense = next((t for t in tags if t not in ("conjugaison", verb) and not re.match(r"etape", t, re.I)), None)
    person = (re.search(r"<i>([^<]+)</i>", q) or [None, None])[1]
    return (verb, tense, person.strip()) if verb and tense and person else None


def conj_table(card, cards):
    k = conj_key(card)
    if not k:
        return None
    forms, label, meaning = {}, "", ""
    for c in cards:
        x = conj_key(c)
        if not x or x[:2] != k[:2]:
            continue
        forms[x[2]] = plain(c.get("answer")) or " ".join(c.get("words") or [])
        if not label:
            q = str(c.get("question"))
            label = plain(re.sub(r"·.*$", "", re.sub(r"^.*<br>", "", q, flags=re.S), flags=re.S)).strip()
            meaning = (re.search(r"\(([^)]+)\)", q) or [None, ""])[1]
    persons = [p for p in CONJ_PERSONS if p in forms]
    if len(persons) < 2:
        return None
    stem = forms[persons[0]]
    for f in (forms[p] for p in persons[1:]):
        i = 0
        while i < len(stem) and i < len(f) and stem[i].lower() == f[i].lower():
            i += 1
        stem = stem[:i]
    if len(stem) < 2:
        stem = ""
    out = ["  " + col(BOLD, k[0]) + (" (%s)" % meaning if meaning else "") + " · " + label]
    w = max(len(p) for p in persons)
    for p in persons:
        f = forms[p]
        line = "  %s  %s%s" % (p.ljust(w), f[:len(stem)], col(GREEN, f[len(stem):]))
        out.append(col(YELLOW, "› ") + line[2:] if p == k[2] else line)
    return "\n".join(out)


# Keywords (#261): « :mot » or its first letters can't be taken for an answer —
# :h :i :help :info = aide, :t :tab = tableau, :ti :temps / :s :stats = what's left,
# :d :dump, :q = stop. The plain words still work (and i, h, t, ? alone).
KEYWORDS = {"help": ("h", "help", "i", "info", "aide"), "tab": ("t", "tab"), "stats": ("s", "stats", "ti", "temps"),
            "dump": ("d", "dump"), "save": ("save",), "quit": ("q", "quit"), "answer": ("?",),
            "pause": ("p", "pause", "b"), "log": ("l", "log")}
PLAIN = {"help": ("h", "help", "i", "info", "aide"), "tab": ("t", "tab"), "stats": ("stats", "temps"),
         "dump": ("dump",), "save": ("save",), "quit": ("q",), "answer": ("?",), "pause": ("pause",), "log": ("log",)}
SLOW_S = 30  # ⚙ « trop lent » of the app (slowSeconds), read in main
OFFERED = False  # « Entrée = suivante · + · tab » shown once a session (#265)


def keyword(a):
    a = a.strip().lower()
    table, a = (KEYWORDS, a[1:]) if a.startswith(":") else (PLAIN, a)
    return next((k for k, ws in table.items() if a in ws), None)


_LOOK = {}


def load_look():
    """The Vocabulaire and the Grammaire, read once, for :v and :e."""
    for sid in ("vocabulaire", "grammaire"):
        if sid not in _LOOK:
            d = json.load(open(os.path.join(HERE, bundled_files()[sid]), encoding="utf-8"))
            _LOOK[sid] = [c for dk in d.get("decks") or [] for c in dk.get("cards") or []]


def look(word, srs_of=None):
    """« :v mot » / ankiterm --voir mot (P7, #272): what the decks say about a word —
    the Vocabulaire card (meanings, word class, sentence, the ≠ note and the words
    it's mixed up with, where it stands), and the verb a form comes from (veo →
    ver, presente, yo). srs_of(source id) → its progress, or None."""
    w = squash(word)
    if not w:
        return col(DIM, "  :v suivi d'un mot (espagnol ou français)")
    load_look()
    bare = lambda t: squash(re.sub(r"^(el|la|los|las|un|una)\s+", "", t, flags=re.I))
    vocab = [c for c in _LOOK["vocabulaire"] if not c.get("rev")]
    hits = [c for c in vocab if w in (squash(c["es"]), bare(c["es"]))]
    hits += [c for c in vocab if c not in hits and w in {squash(x) for x in re.split(r"\s*[,;/]\s*", c.get("fr") or "")}]
    forms = []
    for c in _LOOK["grammaire"]:
        k = conj_key(c)
        if k and squash(" ".join(str(x) for x in c.get("words") or [])) == w and k not in forms:
            forms.append(k)
    out = []
    for verb, tense, person in forms:
        out.append(col(BOLD, "  %s" % word.strip()) + " = " + col(BOLD, verb) + col(DIM, " · %s · %s" % (tense, person)))
        hits += [c for c in vocab if c not in hits and squash(c["es"]) == squash(verb)]
    if not hits and not forms:  # a form no card has: its verb, guessed from the ending (veo → ver, miro → mirar)
        verbs = {squash(c["es"]): c for c in vocab if (c.get("pos") or "").startswith("verbe")}
        ends = sorted(("o", "as", "a", "amos", "áis", "an", "es", "e", "emos", "éis", "en", "imos", "ís", "é", "aste",
                       "ó", "aron", "í", "iste", "ió", "ieron", "aba", "ía", "ando", "iendo", "ado", "ido"), key=len, reverse=True)
        for e in ends:
            if w.endswith(squash(e)) and len(w) > len(e) + 1:
                stem = w[:len(w) - len(squash(e))]
                for inf in (stem + "ar", stem + "er", stem + "ir", stem + "r"):
                    if inf in verbs and verbs[inf] not in hits:
                        hits.append(verbs[inf])
                        out.append(col(DIM, "  « %s » : sans doute une forme de " % word.strip()) + col(BOLD, verbs[inf]["es"]))
    srs = (srs_of("vocabulaire") if srs_of else None) or {}
    for c in hits[:4]:
        out.append(col(BOLD, "  " + c["es"]) + " — " + c.get("fr", "") + (col(DIM, "  (%s)" % c["pos"]) if c.get("pos") else ""))
        if c.get("s"):
            out.append(col(DIM, "    " + plain(c["s"]) + (" — " + c["sf"] if c.get("sf") else "")))
        if c.get("n"):
            out.append(col(BLUE, "    " + c["n"]))
        if c.get("cf"):
            out.append(col(DIM, "    ≠ " + " · ".join(c["cf"])))
        for cid, way in ((str(c["id"]), "es→fr"), (str(int(c["id"]) + 1), "fr→es")):
            x = srs.get(cid)
            if x and x.get("state", "new") != "new":
                due = x.get("due", TODAY) - TODAY
                out.append(col(DIM, "    %s : %s, revient %s · %d oubli(s)" % (
                    way, seen_ago(x), "aujourd'hui" if due <= 0 or x.get("state") != "review" else "dans %d j" % due,
                    x.get("lapses", 0))))
    if not out:
        near = sorted({c["es"] for c in vocab if squash(c["es"]).startswith(w[:4])}, key=len)[:6]
        return col(DIM, "  rien pour « %s »%s" % (word.strip(), " — peut-être : " + ", ".join(near) if near else ""))
    return "\n".join(out)


def explore(first=None, srs_of=None):
    """« :e » / ankiterm --dico (#278): a very small explorer of the Vocabulaire and the
    Grammaire, straight on a search — a bit of a word, Spanish or French, accents
    ignored; the exact word first. A number shows that word's details (as :v),
    another text searches again, Entrée alone (or q) goes back."""
    load_look()
    vocab = [c for c in _LOOK["vocabulaire"] if not c.get("rev")]
    gram = [c for c in _LOOK["grammaire"] if c.get("words")]
    q, hits = first, []
    while True:
        if q is None:
            q = ask(col(CYAN, "  🔍 "), counted=False)
            if q is None or q.strip().lower() in ("", "q", ":q"):
                return
        q = q.strip()
        if q.isdigit() and hits:
            if 1 <= int(q) <= len(hits):
                kind, c = hits[int(q) - 1]
                if kind == "v":
                    print(look(c["es"], srs_of))
                else:
                    print(col(BOLD, "  " + plain(c.get("question") or "")) + "\n" + col(GREEN, "  " + " ".join(map(str, c["words"]))))
            q = None
            continue
        w = squash(q)
        found = []
        for c in vocab:
            es, fr = squash(c["es"]), squash(c.get("fr") or "")
            if w in es or w in fr:
                exact = w in (es, re.sub(r"^(el|la|los|las|un|una) ", "", es)) or w in {squash(x) for x in re.split(r"\s*[,;/]\s*", c.get("fr") or "")}
                found.append((0 if exact else 1 if es.startswith(w) else 2, len(c["es"]), "v", c))
        for c in gram:
            ans = " ".join(map(str, c["words"]))
            if w in squash(ans):
                found.append((0 if squash(ans) == w else 3, len(ans), "g", c))
        found.sort(key=lambda x: x[:2])
        hits = [(k, c) for _, _, k, c in found[:15]]
        if not hits:
            print(col(DIM, "  rien pour « %s »" % q))
        for i, (k, c) in enumerate(hits, 1):
            if k == "v":
                left, right = c["es"], c.get("fr") or ""
            else:
                left, right = " ".join(map(str, c["words"])), "Grammaire : " + plain(c.get("question") or "").replace("\n", " ")
            print(col(DIM, "  %2d " % i) + col(BOLD, "%-26s" % left[:26]) + " " + right[:70])
        if len(found) > 15:
            print(col(DIM, "  … %d de plus : précise" % (len(found) - 15)))
        if hits:
            print(col(DIM, "  un numéro = le détail · un autre mot · Entrée = retour"))
        q = None


def seen_ago(s):
    """How long since this card was last answered, next to it (#267): « nouvelle »,
    « vue il y a 12 min », « il y a 3 j »…"""
    t = (s or {}).get("lastReview")
    if not t or (s or {}).get("state", "new") == "new":
        return "nouvelle"
    m = max(0, (time.time() * 1000 - t) / 60000)
    if m < 60:
        return "vue il y a %d min" % max(1, m)
    if m < 24 * 60:
        return "vue il y a %d h" % (m // 60)
    d = m // (24 * 60)
    return "vue il y a %d j" % d if d < 60 else "vue il y a %d mois" % (d // 30)


def back_in(s, q):
    """When the card comes back after this rating, as Anki shows it above its
    buttons (#263): « <1m », « <10m », « 4j »…"""
    s2, rq = apply_rating(s or default_srs(), q)
    return "<%dm" % rq if rq else "%dj" % s2.get("interval", 1)


def day_start_ms():
    t = time.localtime()
    return int(time.mktime((t.tm_year, t.tm_mon, t.tm_mday, 0, 0, 0, 0, 0, -1)) * 1000)


def review(card, s, on_dump=None, on_add=None, on_stats=None, on_tab=None, on_prev=None, on_log=None, on_look=None):
    """Shows one card, returns its rating 1–4 (as the app, #261), or None to stop.
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
    right |= {squash(x) for x in card.get("alt") or []}  # meanings added after a miss (#227)
    # every meaning written on the card is right, not only the first one typed (#88):
    # « je te tiens au courant » for te aviso, « quelque » for algún (#265)
    if card.get("fr") and not card.get("rev"):
        right |= {squash(re.sub(r"\(.*?\)", "", m)) for m in re.split(r"[;,]", card["fr"]) if squash(re.sub(r"\(.*?\)", "", m))}
    # « après-midi » is masculine or feminine: « cette après-midi » too (#230), as in the app
    right |= {x.replace(squash("cet après-midi"), squash("cette après-midi")) for x in right}
    back = plain(card.get("answer")) or shown
    flip = card.get("flip") or card.get("eq") or not words
    print()
    print(col(BOLD, ind(front_of(card))) + col(DIM, "  · " + seen_ago(s)))
    if flip:
        if ask(col(DIM, "  Entrée = retourner ")) is None:
            return None
        print(col(CYAN, ind(back)))
        r = ask(col(DIM, "  su ? Entrée = oui · n = non "))
        if r is None or r.strip() == "q":
            return None
        return 1 if r.strip().lower() in ("n", "non", "1") else 3
    # « A mí me ___ el chocolate » (#261): « me gusta » is right too, as « gusta »
    gap = plain(card.get("question") or "").split("\n")[0]
    if "___" in gap:
        pre, post = gap.split("___", 1)
        pre_w, post_w = (pre.split() or [""])[-1], (post.split() or [""])[0]
        right |= {squash(pre_w + " " + g) for g in list(right)} | {squash(g + " " + post_w) for g in list(right)}
    k, last, helped, empties, t0 = 0, "", False, 0, time.time()

    def add(r):
        """« + » (#227), « + autre sens »: confirmed (#232), then the card counts as Correct.
        True = added, False = not, None = stop."""
        extra = r.strip()[1:].strip() or last
        if not extra:
            return False
        # the card named (#270): « + » typed on the card after the one it was meant for
        sure = ask(col(DIM, "  ajouter « %s » à « %s » ? Entrée = oui · n = non " % (extra, front_of(card))))
        if sure is None:
            return None
        if sure.strip().lower() in ("", "o", "oui", "y", "yes"):
            on_add(extra)
            print(col(GREEN, "  ✓ « %s » ajouté" % extra))
            return True
        return False

    def show_tab():
        t = on_tab() if on_tab else None
        print(t if t else col(DIM, "  pas de tableau pour cette carte"))
        return bool(t)

    while k < 3:
        a = ask("  › ")
        if a is None:
            return None
        w = keyword(a)
        if w == "quit":
            return None
        m = re.match(r"^:(?:e|dico)(?:\s+(.+))?$", a.strip(), re.I)
        if m:  # the explorer (#278), straight on a search: doesn't use a try
            explore(m.group(1), on_look)
            print(col(BOLD, ind(front_of(card))))
            continue
        m = re.match(r"^:(?:v|voir)\s+(.+)$", a.strip(), re.I)
        if m:  # a word's details (P7, #272): doesn't use a try
            print(look(m.group(1), on_look))
            continue
        if w == "answer":
            break  # « ? »: the answer now, the card À revoir
        if w == "dump" and on_dump:
            on_dump()  # doesn't use a try
            continue
        if a.strip().startswith("+") and on_prev and not last:
            # nothing tried here yet: « + » is for the card missed just before (#253)
            r = on_prev(a.strip()[1:].strip())
            if r is None:
                return None
            if r is not False or not on_add or not a.strip()[1:].strip():
                continue
            # « n »: not for that card — then maybe for this one (#270)
        if a.strip().startswith("+") and on_add:
            ok = add(a)  # from the first miss on, without using up the tries
            if ok is None:
                return None
            if ok:
                return 3
            continue
        if w == "stats" and on_stats:
            print(on_stats())  # cards left: new · learning · review, and the time left
            continue
        if w == "save":
            # each card is already saved when answered: nothing left to send
            print(col(GREEN, "  ✓ enregistré"))
            continue
        if w == "tab":
            helped = show_tab() or helped  # the table shows the answer: « À revoir », as F1 in the app
            continue
        if w == "help":
            print(col(DIM, INFO))
            continue
        if w == "pause":
            # the clock stops until Entrée (#263)
            if ask(col(DIM, "  ⏸ pause — Entrée pour reprendre "), counted=False) is None:
                return None
            print(col(BOLD, ind(front_of(card))))
            continue
        if w == "log" and on_log:
            print(on_log())
            continue
        if not squash(a):
            # Entrée twice with nothing typed: the card again, if it has gone up (#261)
            empties += 1
            if empties >= 2:
                print(col(BOLD, ind(front_of(card))))
                empties = 0
            continue  # Entrée alone doesn't use a try
        empties = 0
        if squash(a) in right:
            # the same ratings as the app (#249, #261): the answer seen = À revoir; found with
            # effort (2 misses, far slower than usual) = Difficile; at once, on a card seen
            # before today = Facile; else Correct
            spent, usual = SPENT, ((s or {}).get("ms") or 0) / 1000
            slow = spent > max(SLOW_S, 3 * usual) if SLOW_S else False
            seen = (s or {}).get("state", "new") != "new" and (s or {}).get("lastReview", 0) < day_start_ms()
            if helped:
                q, why = 1, "avec le tableau"
            elif k >= 2:
                q, why = 2, "%d erreurs" % k
            elif slow:
                q, why = 2, "trop lent"
            elif k == 0 and seen:
                q, why = 4, "du premier coup"
            else:
                q, why = 3, "1 erreur" if k else "sans aide"
            colour, label = {1: (RED, "À revoir"), 2: (YELLOW, "Difficile"), 3: (GREEN, "Correct"), 4: (BLUE, "Facile")}[q]
            every = card["fr"] if card.get("fr") and not card.get("rev") and squash(card["fr"]) != squash(shown) else shown
            print(col(colour, "  ✓ " + every) + col(DIM, "  %s (%s) : %s" % (label, back_in(s, q), why)))
            card["_last"] = last  # a try not taken: « + » on the next card can add it (#270)
            return q
        last = a.strip()
        k += 1  # not accepted: just asked again (no ✗)
    card["_last"] = last  # « + » on the next card can still add it (#253)
    # in red, as the learning count shown after it: the card goes back there
    print(col(RED, "  → " + shown + "".join(" / " + x for x in card.get("alt") or [])) + col(DIM, "  À revoir (%s)" % back_in(s, 1)))
    if back and squash(back) != squash(" ".join(words)):
        print(col(DIM, ind(back)))
    # your meaning was right but not in the list (#227): « + » adds it, the card counts as Correct;
    # « tab » still shows the table here (#261)
    # the whole line once a session, then just ↵ — it was on every miss (#265)
    global OFFERED
    offer = ["Entrée = suivante"]
    if last and on_add:
        offer.append("+ = ajouter « %s »" % last)
    if on_tab and conj_key(card):
        offer.append("tab = tableau")
    line = "  " + " · ".join(offer) + " " if not OFFERED else "  ↵ "
    OFFERED = True
    while True:
        r = ask(col(DIM, line))
        if r is None:
            return None
        w = keyword(r)
        if w == "tab":
            show_tab()
            continue
        if w == "help":
            print(col(DIM, INFO))
            continue
        if w == "quit":
            return None
        break
    if r.strip().startswith("+") and on_add:
        ok = add(r)
        if ok is None:
            return None
        if ok:
            return 3
    # no wipe (#242): the card waits until its answer has scrolled out of sight (main)
    return 1

# ── Défi (#266): one minute, as many Spanish words of a tag as you can think of ──
DEFI_S = 60
ARTICLE = re.compile(r"^(el|la|los|las|un|una|lo)\s+", re.I)


def defi(tag):
    """Free recall: words typed from memory, checked against the Vocabulaire's
    cards of that tag; the best score per tag is kept."""
    data = json.load(open(os.path.join(HERE, "vocabulaire.json"), encoding="utf-8"))
    cards = [c for d in data["decks"] for c in d["cards"] if not c.get("rev")]
    count = {}
    for c in cards:
        for t in c.get("tags") or []:
            if t not in ("vocabulaire", "es→fr", "fr→es", "transparent"):
                count[t] = count.get(t, 0) + 1
    tags = sorted(count, key=lambda t: -count[t])
    if tag not in count:
        print(col(BOLD, "Défi : une minute, le plus de mots espagnols d'un tag."))
        for i, t in enumerate(tags[:24], 1):
            print("  %2d  %-22s %s" % (i, t, col(DIM, str(count[t]))))
        a = ask("Tag ? (numéro ou nom) ")
        if a is None:
            return
        a = a.strip()
        tag = tags[int(a) - 1] if a.isdigit() and 1 <= int(a) <= len(tags) else a
        if tag not in count:
            print("pas de tag « %s »" % tag)
            return
    # Spanish word (without its article, its « (feminine) ») → its card, for the tag and for all
    def keys(es):
        base = re.sub(r"\s*\(.*?\)", "", es).strip()
        return {squash(base), squash(ARTICLE.sub("", base))} | {squash(x) for x in re.split(r"[/,]", base) if x.strip()}
    of_tag, anywhere = {}, {}
    for c in cards:
        for k in keys(c["es"]):
            anywhere.setdefault(k, c)
            if tag in (c.get("tags") or []):
                of_tag.setdefault(k, c)
    cfg = load_cfg()
    best = (cfg.get("defi") or {}).get(tag, 0)
    print(col(BOLD, "\n%s — %d s, le plus de mots possible" % (tag, DEFI_S)) + col(DIM, "  (record : %d) · Entrée pour commencer" % best))
    if ask("") is None:
        return
    start, found = time.time(), []
    while True:
        left = DEFI_S - (time.time() - start)
        if left <= 0:
            break
        a = ask(col(DIM, "  %2d s " % left) + "› ")
        if a is None:
            break
        if time.time() - start > DEFI_S:
            print(col(DIM, "  (trop tard)"))
            break
        k = squash(ARTICLE.sub("", a.strip()))
        if not k:
            continue
        c = of_tag.get(k)
        if c and c["id"] in {x["id"] for x in found}:
            print(col(DIM, "  déjà dit"))
        elif c:
            found.append(c)
            print(col(GREEN, "  ✓ %s" % c["es"]) + col(DIM, "  " + c["fr"]))
        elif k in anywhere:
            print(col(YELLOW, "  ✗ %s : pas « %s »" % (anywhere[k]["es"], tag)) + col(DIM, "  " + anywhere[k]["fr"]))
        else:
            print(col(RED, "  ✗ pas dans le Vocabulaire"))
    n = len(found)
    print(col(BOLD, "\n%d mot(s) en %d s" % (n, DEFI_S)) + (col(BLUE, "  — record !") if n > best else col(DIM, "  (record : %d)" % best)))
    if n > best:
        cfg.setdefault("defi", {})[tag] = n
        save_cfg(cfg)
    # the most frequent words of the tag not given: the deck is in frequency order
    seen_ids = {c["id"] for c in found}
    miss = [c for c in cards if tag in (c.get("tags") or []) and c["id"] not in seen_ids][:8]
    if miss:
        print(col(DIM, "à retenir : ") + " · ".join("%s (%s)" % (c["es"], c["fr"].split(",")[0]) for c in miss))


def main():
    ap = argparse.ArgumentParser(description="Réviser dans le terminal (même progression que l'app).")
    ap.add_argument("deck", nargs="?", help="un bout du nom du paquet (sinon : la liste)")
    ap.add_argument("-d", "--sub", help="seulement les sous-paquets dont le nom contient ce texte")
    ap.add_argument("-n", "--new", type=int, help="nouvelles cartes par jour (défaut : le réglage ⚙ de l'app, sinon 20)")
    ap.add_argument("-l", "--liste", action="store_true", help="la liste des paquets pour en choisir un (sinon : tous ceux du jour, à la suite)")
    ap.add_argument("--dry", action="store_true", help="ne rien écrire dans Firestore")
    ap.add_argument("--user", action="store_true", help="choisir à nouveau qui révise")
    ap.add_argument("--journal", action="store_true", help="jour par jour : réponses, cartes, nouvelles, taux du 1er coup, intervalles donnés, cartes à venir")
    ap.add_argument("--dico", nargs="?", const="", metavar="MOT", help="petit explorateur du Vocabulaire et de la Grammaire, qui démarre sur une recherche")
    ap.add_argument("--voir", metavar="MOT", help="les détails d'un mot : sens, exemple, ≠, verbe d'une forme (veo → ver), où il en est")
    ap.add_argument("--defi", nargs="?", const="", metavar="TAG",
                    help="défi : en une minute, le plus de mots espagnols de ce tag (verbe, adjectif…)")
    args = ap.parse_args()
    global USER
    if args.defi is not None:
        return defi(args.defi)  # no progress involved: no user needed
    USER = setup(args.user)
    if args.dico is not None:
        return explore(args.dico or None, lambda x: get_doc("users/%s/sources/%s" % (USER, x)).get("srs") or {})
    if args.journal:
        print(journal())
        try:
            print(col(DIM, due_ahead(get_doc("users/%s/sources/vocabulaire" % USER).get("srs") or {})))
        except Exception:
            pass
        return
    if args.voir:
        return print(look(args.voir, lambda x: get_doc("users/%s/sources/%s" % (USER, x)).get("srs") or {}))

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
        srcs, auto = pick[:1], False
    elif not args.liste:
        # P6 (#271): straight to the decks with cards today, the one reviewed last first;
        # not the 💤 ones (asleep in the app)
        last = last_reviewed(sources) or (load_cfg().get("last") or {}).get(USER)
        srcs = sorted((s for s in sources if s["id"] not in asleep), key=lambda s: s["id"] != last)
        auto = True
    else:
        # the deck reviewed last — in the app or here — is the default: Entrée takes it
        last = last_reviewed(sources) or (load_cfg().get("last") or {}).get(USER)
        dflt = next((i for i, s in enumerate(sources, 1) if s["id"] == last), None)
        for i, s in enumerate(sources, 1):
            line = "%2d  %s%s" % (i, s["name"], col(DIM, "  💤") if s["id"] in asleep else "")
            print(col(BOLD, line + "  ←") if i == dflt else line)
        a = ask("Paquet ? " + ("[%d] " % dflt if dflt else ""))
        if a is None:
            return
        a = a.strip() or (str(dflt) if dflt else "")
        if not a.isdigit() or not 1 <= int(a) <= len(sources):
            return
        srcs, auto = [sources[int(a) - 1]], False
    def session(src):
        """One deck: its cards today, until done or « q ». « empty »: nothing today."""
        cfg = load_cfg()
        cfg.setdefault("last", {})[USER] = src["id"]
        save_cfg(cfg)

        sid = src["id"]
        meta = get_doc("users/%s/sources/%s" % (USER, sid))
        srs = meta.get("srs") or {}
        # answers kept on disk when Firestore was out of reach (#276): the newer ones win
        kept = {k: v for k, v in (((load_cfg().get("unsaved") or {}).get(USER) or {}).get(sid) or {}).items()
                if (v.get("lastReview") or 0) > ((srs.get(k) or {}).get("lastReview") or 0)}
        srs.update(kept)
        flagged = live_flags(meta.get("flagged") or {})
        nc = meta.get("newCount") or {}
        nc = nc if nc.get("day") == TODAY else {"day": TODAY, "count": 0}
        by, names = load_cards(sid, files)
        edits = meta.get("edits") or {}
        for cid, e in edits.items():  # cards changed in 📝 Relecture (and meanings added here)
            for cards in by.values():
                for c in cards:
                    if str(c.get("id")) == cid:
                        c.update((e or {}).get("f") or {})
        deck_name = study_deck(names, args.sub)
        queue = build_queue(by, names, srs, flagged, deck_name, new_left(args.new, nc["count"]), sid)
        twin = twins(queue)  # each card and its other direction (#269)
        queue = [c for c in queue if front_of(c)]  # a picture alone can't be shown here (after the draw: same order)
        n_new = sum(1 for c in queue if str(c["id"]) not in srs or srs[str(c["id"])].get("state") == "new")
        print(col(BOLD, "%s" % src["name"]) + col(DIM, " — %d à revoir, %d nouvelles%s" % (
            len(queue) - n_new, n_new, " (essai : rien n'est écrit)" if args.dry else "")) + col(DIM, "  · info = aide"))
        if not queue:
            for k in list(kept):  # answers kept from an offline session (#276): sent all the same
                try:
                    save_review(sid, k, kept.pop(k), nc, args.dry)
                except Exception:
                    break
            if not kept:
                cfg = load_cfg()
                ((cfg.get("unsaved") or {}).get(USER) or {}).pop(sid, None)
                save_cfg(cfg)
            if not auto:
                print("Rien à réviser aujourd'hui 🎉")
            return "empty"

        done, t_start, stopped = 0, time.time(), False
        seen_ids, unsaved = set(), {}  # cards answered; reviews Firestore didn't take yet (#264)

        def retry_unsaved(last=False):
            for k in list(unsaved):
                try:
                    save_review(sid, k, srs.get(k, unsaved[k]), nc, args.dry)
                    unsaved.pop(k)
                    print(col(DIM, "  ✓ enregistré après coup"))
                except Exception:
                    if not last:
                        return  # still offline: later

        def keep_unsaved():
            """What Firestore didn't take stays on disk, sent at the next start (#276)."""
            cfg = load_cfg()
            mine = cfg.setdefault("unsaved", {}).setdefault(USER, {})
            if unsaved and not args.dry:
                mine[sid] = {k: srs.get(k, v) for k, v in unsaved.items()}
            else:
                mine.pop(sid, None)
            save_cfg(cfg)

        if kept:
            unsaved.update(kept)
            retry_unsaved(last=True)
            print(col(DIM, "  ✓ %d réponse(s) d'une séance hors ligne envoyée(s)" % (len(kept) - len(unsaved))
                      + (", %d pas encore" % len(unsaved) if unsaved else "")))
            keep_unsaved()
        missed_at = {}  # card id → line count when its answer was shown (#242)
        prev = None  # the card just missed: « + » on the next one adds a meaning to it (#253)

        def add_to_prev(text):
            """« + » (or « + sens ») typed first on a card: that meaning goes to the card
            just before, if one of its tries wasn't taken — rated Correct instead of
            À revoir when it was missed (#253), else its rating stays (#270).
            True = added, False = not, None = stop."""
            nonlocal prev
            if not prev:
                print(col(DIM, "  pas de carte ratée juste avant"))
                return False
            pc, extra = prev["card"], text or prev["last"]
            if not extra:
                print(col(DIM, "  rien à ajouter : + suivi du sens"))
                return False
            sure = ask(col(DIM, "  ajouter « %s » à « %s » ? Entrée = oui · n = non " % (extra, front_of(pc))))
            if sure is None:
                return None
            if sure.strip().lower() not in ("", "o", "oui", "y", "yes"):
                return False
            add_answer(sid, pc, extra, edits, args.dry)
            pid = str(pc["id"])
            if prev.get("q", 1) != 1:  # found in the end: only the meaning is added
                print(col(GREEN, "  ✓ « %s » ajouté à « %s »" % (extra, front_of(pc))))
                prev = None
                return True
            s2, req2 = apply_rating(prev["before"] or default_srs(), 3)  # Correct after all
            s2["lastReview"] = int(time.time() * 1000)
            if srs.get(pid, {}).get("ms"):
                s2["ms"] = srs[pid]["ms"]
            srs[pid] = s2
            try:
                save_review(sid, pid, s2, nc, args.dry)
            except Exception as e:
                print(col(RED, "  ⚠ pas enregistré : %s" % e))
            queue[:] = [c for c in queue if str(c["id"]) != pid]  # no more « à repasser » for it
            if req2:
                queue.insert(min(len(queue), req2), pc)
            missed_at.pop(pid, None)
            print(col(GREEN, "  ✓ « %s » ajouté à « %s » : comptée Correct" % (extra, front_of(pc))))
            prev = None
            return True
        table_at = {}  # (verb, tense) → line count when its table was shown (#261)
        answer_at = {}  # an answer → line count when it was last on screen (#263)
        akey = lambda c: squash(" ".join(str(w) for w in (c.get("words") or []) if str(w).strip()))
        active = 0.0  # seconds really spent: a card counts 60 s at most (#261)

        def shown_at(c):
            """When this card's answer was last on screen: missed, or in a table."""
            k = conj_key(c)
            # the same answer just shown on another card (« han » for haber and for the gap
            # sentence) waits too (#263)
            return max(missed_at.get(str(c["id"]), -10**9), table_at.get(k, -10**9) if k else -10**9,
                       answer_at.get(akey(c), -10**9))

        def tab_for(c):
            t = conj_table(c, [x for cs in by.values() for x in cs])
            if t:
                table_at[conj_key(c)] = LINES + rows(t + "\n")  # its forms wait until it's out of sight
                for x in (y for cs in by.values() for y in cs):
                    if conj_key(x) and conj_key(x)[:2] == conj_key(c)[:2]:
                        answer_at[akey(x)] = table_at[conj_key(c)]
            return t

        while queue:
            # a missed card — or one whose form is in a table still on screen — waits until
            # its answer is out of sight: the next one goes first
            i = next((i for i, c in enumerate(queue) if out_of_sight(shown_at(c))), None)
            if i is None:  # nothing else to show: push the answer up and out
                print("\n" * max(0, shutil.get_terminal_size((80, 24)).lines - (LINES - shown_at(queue[0]))), end="")
                i = 0
            card = queue.pop(i)
            cid = str(card["id"])
            before = srs.get(cid)
            t0 = time.time()
            global SPENT
            SPENT = 0.0
            q = review(card, before, on_dump=lambda: dump([card] + queue, srs),
                       on_stats=lambda: counts_line([card] + queue, srs),
                       on_tab=lambda: tab_for(card),
                       # « + » adds a meaning: vocabulary only — a conjugation or a gap has one right answer (#264)
                       on_add=(lambda text: add_answer(sid, card, text, edits, args.dry)) if card.get("es") else None,
                       on_prev=add_to_prev if prev else None,
                       on_log=lambda: log_today(sid),
                       on_look=lambda x: srs if x == sid else (get_doc("users/%s/sources/%s" % (USER, x)).get("srs") or {}))
            if q is None:
                stopped = True
                break
            active += SPENT
            was_new = before is None or before.get("state") == "new"
            s, requeue = apply_rating(before or default_srs(), q)
            s["lastReview"] = int(time.time() * 1000)  # the most recent review wins in the app's merge
            ms = min(60000, int(SPENT * 1000))
            s["ms"] = round(s["ms"] * 0.7 + ms * 0.3) if s.get("ms") else ms
            srs[cid] = s
            if was_new:
                nc["count"] += 1
            try:
                save_review(sid, cid, s, nc, args.dry)
                unsaved.pop(cid, None)
            except Exception as e:  # keep going; it is tried again after the next cards (#264)
                unsaved[cid] = s
                print(col(RED, "  ⚠ pas encore enregistré (%s) : nouvel essai plus tard" % e))
            retry_unsaved()
            done += 1
            seen_ids.add(cid)
            # its other direction, if still to come today, waits until tomorrow (#269)
            queue[:] = [x for x in queue if not (str(x["id"]) == twin.get(cid) and resting(srs.get(twin[cid])))]
            if requeue:  # learning step: back a few cards later (as in the app)
                queue.insert(min(len(queue), requeue), card)
            # missed, or a try not taken before the right answer (#270): « + » on the next card is for it
            prev = ({"card": card, "before": before, "last": card.get("_last", ""), "q": q}
                    if card.get("es") and (q == 1 or card.get("_last")) else None)
            write_log(sid, card, q, s, requeue, SPENT, args.dry, before)
            if q == 1:
                missed_at[cid] = LINES
                answer_at[akey(card)] = LINES
                if queue:  # missed: what's left
                    print(counts_line(queue, srs))
        mins = active / 60  # not the wall clock: a session left open doesn't count (#261)
        print()
        for _ in range(3):  # last tries before leaving (#264)
            if not unsaved:
                break
            retry_unsaved(last=True)
            if unsaved:
                time.sleep(2)
        if unsaved:
            print(col(RED, "⚠ %d révision(s) pas encore dans Firestore (réseau) : gardées ici, envoyées au prochain lancement" % len(unsaved)))
        keep_unsaved()
        # answers, not cards: a card missed comes back (#264)
        print(col(DIM, "%d réponse(s), %d carte(s), en %.0f min%s" % (done, len(seen_ids), mins,
                                                                   "" if args.dry or unsaved else " — enregistré dans Firestore")))
        return "quit" if stopped else "done"

    # P6 (#271): with no deck named, every deck with cards today, one after the other —
    # the one reviewed last first; « --liste » shows the list to pick one, as before
    results = []
    for src in srcs:
        if results and results[-1] != "empty":
            print()
        results.append(session(src))
        if results[-1] == "quit":
            return
    if auto and all(r == "empty" for r in results):
        print("Rien à réviser aujourd'hui 🎉")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
