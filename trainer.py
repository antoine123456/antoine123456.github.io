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


def ask(prompt):
    global LINES
    try:
        a = input(prompt)
    except EOFError:
        print()
        return None
    LINES += rows(prompt + a + "\n")  # the echoed answer and Entrée
    return a


def out_of_sight(at):
    """Has what was written at line `at` left the window?"""
    return LINES - at >= shutil.get_terminal_size((80, 24)).lines


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
    return due + new


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
  :h  :i     cette aide
  :q  q      arrêter
  Entrée deux fois : la carte
  à nouveau.

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
            "dump": ("d", "dump"), "save": ("save",), "quit": ("q", "quit"), "answer": ("?",)}
PLAIN = {"help": ("h", "help", "i", "info", "aide"), "tab": ("t", "tab"), "stats": ("stats", "temps"),
         "dump": ("dump",), "save": ("save",), "quit": ("q",), "answer": ("?",)}
SLOW_S = 30  # ⚙ « trop lent » of the app (slowSeconds), read in main


def keyword(a):
    a = a.strip().lower()
    table, a = (KEYWORDS, a[1:]) if a.startswith(":") else (PLAIN, a)
    return next((k for k, ws in table.items() if a in ws), None)


def day_start_ms():
    t = time.localtime()
    return int(time.mktime((t.tm_year, t.tm_mon, t.tm_mday, 0, 0, 0, 0, 0, -1)) * 1000)


def review(card, s, on_dump=None, on_add=None, on_stats=None, on_tab=None, on_prev=None):
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
    # « après-midi » is masculine or feminine: « cette après-midi » too (#230), as in the app
    right |= {x.replace(squash("cet après-midi"), squash("cette après-midi")) for x in right}
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
        sure = ask(col(DIM, "  ajouter « %s » ? Entrée = oui · n = non " % extra))
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
        if w == "answer":
            break  # « ? »: the answer now, the card À revoir
        if w == "dump" and on_dump:
            on_dump()  # doesn't use a try
            continue
        if a.strip().startswith("+") and on_prev and not last:
            # nothing tried here yet: « + » is for the card missed just before (#253)
            if on_prev(a.strip()[1:].strip()) is None:
                return None
            continue
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
            spent, usual = time.time() - t0, ((s or {}).get("ms") or 0) / 1000
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
            print(col(colour, "  ✓ " + shown) + col(DIM, "  " + label + " : " + why))
            return q
        last = a.strip()
        k += 1  # not accepted: just asked again (no ✗)
    card["_last"] = last  # « + » on the next card can still add it (#253)
    # in red, as the learning count shown after it: the card goes back there
    print(col(RED, "  → " + shown + "".join(" / " + x for x in card.get("alt") or [])) + col(DIM, "  À revoir"))
    if back and squash(back) != squash(" ".join(words)):
        print(col(DIM, ind(back)))
    # your meaning was right but not in the list (#227): « + » adds it, the card counts as Correct;
    # « tab » still shows the table here (#261)
    offer = ["Entrée = suivante"]
    if last and on_add:
        offer.append("+ = ajouter « %s »" % last)
    if on_tab and conj_key(card):
        offer.append("tab = tableau")
    while True:
        r = ask(col(DIM, "  " + " · ".join(offer) + " "))
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

def main():
    ap = argparse.ArgumentParser(description="Réviser dans le terminal (même progression que l'app).")
    ap.add_argument("deck", nargs="?", help="un bout du nom du paquet (sinon : la liste)")
    ap.add_argument("-d", "--sub", help="seulement les sous-paquets dont le nom contient ce texte")
    ap.add_argument("-n", "--new", type=int, help="nouvelles cartes par jour (défaut : le réglage ⚙ de l'app, sinon 20)")
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
        src = sources[int(a) - 1]
    cfg = load_cfg()
    cfg.setdefault("last", {})[USER] = src["id"]
    save_cfg(cfg)

    sid = src["id"]
    meta = get_doc("users/%s/sources/%s" % (USER, sid))
    srs = meta.get("srs") or {}
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
    queue = [c for c in queue if front_of(c)]  # a picture alone can't be shown here (after the draw: same order)
    n_new = sum(1 for c in queue if str(c["id"]) not in srs or srs[str(c["id"])].get("state") == "new")
    print(col(BOLD, "%s" % src["name"]) + col(DIM, " — %d à revoir, %d nouvelles%s" % (
        len(queue) - n_new, n_new, " (essai : rien n'est écrit)" if args.dry else "")) + col(DIM, "  · info = aide"))
    if not queue:
        print("Rien à réviser aujourd'hui 🎉")
        return

    done, t_start = 0, time.time()
    missed_at = {}  # card id → line count when its answer was shown (#242)
    prev = None  # the card just missed: « + » on the next one adds a meaning to it (#253)

    def add_to_prev(text):
        """« + » (or « + sens ») typed first on a card: that meaning goes to the card
        missed just before, which is then rated Correct instead of À revoir.
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
    active = 0.0  # seconds really spent: a card counts 60 s at most (#261)

    def shown_at(c):
        """When this card's answer was last on screen: missed, or in a table."""
        k = conj_key(c)
        return max(missed_at.get(str(c["id"]), -10**9), table_at.get(k, -10**9) if k else -10**9)

    def tab_for(c):
        t = conj_table(c, [x for cs in by.values() for x in cs])
        if t:
            table_at[conj_key(c)] = LINES + rows(t + "\n")  # its forms wait until it's out of sight
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
        q = review(card, before, on_dump=lambda: dump([card] + queue, srs),
                   on_stats=lambda: counts_line([card] + queue, srs),
                   on_tab=lambda: tab_for(card),
                   on_add=lambda text: add_answer(sid, card, text, edits, args.dry),
                   on_prev=add_to_prev if prev else None)
        if q is None:
            break
        active += min(60, time.time() - t0)
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
        prev = {"card": card, "before": before, "last": card.get("_last", "")} if q == 1 else None
        if q == 1:
            missed_at[cid] = LINES
            if queue:  # missed: what's left
                print(counts_line(queue, srs))
    mins = active / 60  # not the wall clock: a session left open doesn't count (#261)
    print()
    print(col(DIM, "%d carte(s) en %.0f min%s" % (done, mins, "" if args.dry else " — enregistré dans Firestore")))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
