#!/usr/bin/env python3
"""
build_vocab.py — Paquet « Vocabulaire espagnol » façon Refold Mandarin (#71).

Une note par mot / expression du paquet espagnol (default.json), sans les
cartes-phrases, classées par fréquence d'usage (liste es_50k, comme le
« Refold 1k ») :
  - mot espagnol, sens français, nature / genre (enrich_es.py) ;
  - phrase d'exemple tirée des cartes-phrases du paquet + traduction ;
  - audio du mot et de la phrase : les enregistrements du paquet espagnol ;
  - image (noms communs) : l'image principale de l'objet sur Wikidata
    (propriété P18), en lien vers Wikimedia — rien à héberger ; sinon,
    comme Refold qui illustre la phrase, l'image d'un autre nom de la
    phrase d'exemple (« el cliente siempre tiene razón » → cliente).

Sorties :
  vocabulaire.json            paquet inclus dans l'appli (cartes compactes,
                              rendues à l'affichage)
  Vocabulaire espagnol.apkg   à importer dans Anki (mêmes ids de cartes que
                              l'appli, pour ankisync)
  .cache/images_review.html   planche des images pour les vérifier

Usage :
    trainervenv/bin/python build_vocab.py           (le paquet 'anki' sert à l'apkg)
Caches (.cache/, ignoré par git) : liste de fréquences, recherches Wikidata.
"""
import hashlib
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, ".cache")
FREQ_URL = "https://raw.githubusercontent.com/hermitdave/FrequencyWords/master/content/2018/es/es_50k.txt"
# Wikimedia demande un User-Agent qui permet de contacter l'auteur.
UA = {"User-Agent": "anki-trainer-vocab/1.0 (https://github.com/antoine123456/antoine123456.github.io)"}
DECK_NAME = "🇪🇸 Vocabulaire espagnol"
ID_BASE = 1_100_000_000_000  # ids déterministes, dans le passé (2004, avant Anki : ni futur refusé, ni collision)

sys.path.insert(0, HERE)
from enrich_es import ARTICLE, is_sentence, plain, pos_of, sides, toks  # noqa: E402


def get_json(url, tries=6):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                time.sleep(0.25)  # rester poli avec l'API
                return json.load(r)
        except urllib.error.HTTPError as e:
            wait = float(e.headers.get("Retry-After") or 5 * (i + 1)) if e.code == 429 else 2 * (i + 1)
            time.sleep(min(wait, 60))
        except Exception:
            time.sleep(2 * (i + 1))
    return None


def frequency_ranks():
    path = os.path.join(CACHE, "es_50k.txt")
    if not os.path.exists(path):
        os.makedirs(CACHE, exist_ok=True)
        urllib.request.urlretrieve(FREQ_URL, path)
    ranks = {}
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f):
            w = line.split(" ")[0]
            ranks.setdefault(w, i + 1)
    return ranks


# Pas d'image si la description montre que ce n'est pas l'objet (es / fr).
BAD_DESC = re.compile(r"desambigua|homonymie|apellido|nom de famille|nombre (propio|de pila)|prénom|"
                      r"película|film|álbum|album|canción|chanson|sencillo|single|localidad|municipio|"
                      r"commune|ciudad|ville|pueblo|village|río|rivière|periódico|journal|revista|"
                      r"banda|groupe|empresa|entreprise|marca|marque|serie|série|programa|émission|"
                      r"personaje|personnage|novela|roman|libro|livre|videojuego|jeu vidéo|equipo|"
                      r"équipe|club|relief|accidente geográfico|forme de relief", re.I)
FR_ARTICLE = re.compile(r"^(le|la|les|l'|un|une|des)\s*", re.I)


def wikidata_image(noun, fr):
    """Image P18 de l'objet désigné : cherché par son sens français, gardé
    seulement si son libellé espagnol est exactement `noun` (ex. « table » →
    mesa, pas le relief « mesa »). Nom commun uniquement. None sinon."""
    fr_noun = FR_ARTICLE.sub("", fr.split(",")[0].split(";")[0].strip())
    if not fr_noun:
        return None
    q = urllib.parse.urlencode({"action": "wbsearchentities", "search": fr_noun, "language": "fr",
                                "uselang": "fr", "type": "item", "limit": 7, "format": "json"})
    res = get_json("https://www.wikidata.org/w/api.php?" + q) or {}
    ids = [r["id"] for r in res.get("search", [])
           if (r.get("label") or "")[:1].islower() and not BAD_DESC.search(r.get("description") or "")]
    if not ids:
        return None
    q = urllib.parse.urlencode({"action": "wbgetentities", "ids": "|".join(ids), "props": "labels|claims",
                                "languages": "es", "format": "json"})
    ents = (get_json("https://www.wikidata.org/w/api.php?" + q) or {}).get("entities", {})
    for i in ids:
        ent = ents.get(i, {})
        label_es = ent.get("labels", {}).get("es", {}).get("value", "")
        if label_es.lower() != noun.lower():
            continue
        p18 = ent.get("claims", {}).get("P18")
        if p18:
            fn = p18[0]["mainsnak"].get("datavalue", {}).get("value")
            if fn:
                return {"qid": i, "file": fn,
                        "url": "https://commons.wikimedia.org/wiki/Special:FilePath/"
                               + urllib.parse.quote(fn.replace(" ", "_")) + "?width=500"}
    return None


def images_for(nouns):
    """nouns : {nom espagnol: sens français}."""
    path = os.path.join(CACHE, "images.json")
    cache = json.load(open(path)) if os.path.exists(path) else {}
    todo = [n for n in nouns if n not in cache]
    if todo:
        print(f"  Wikidata : {len(todo)} nom(s) à chercher…")
        for k, n in enumerate(todo, 1):  # une requête à la fois (limite de débit Wikidata)
            cache[n] = wikidata_image(n, nouns[n])
            if k % 50 == 0 or k == len(todo):
                with open(path, "w", encoding="utf-8") as f:  # reprise possible
                    json.dump(cache, f, ensure_ascii=False, indent=0)
                print(f"    {k}/{len(todo)}", flush=True)
    return cache


def main():
    with open(os.path.join(HERE, "default.json"), encoding="utf-8") as f:
        decks = json.load(f)["decks"]
    enrich = json.load(open(os.path.join(HERE, "enrich_es.json"), encoding="utf-8"))
    ranks = frequency_ranks()

    # Une entrée par texte espagnol : le sens, l'audio du mot, l'enrichissement.
    words = {}
    for deck in decks:
        for c in deck["cards"]:
            es, fr, audio = sides(c)
            if not es or not fr or is_sentence(es) or es.strip().lower() == fr.strip().lower():
                continue
            k = es.strip().lower()
            w = words.setdefault(k, {"es": es.strip(), "fr": fr.strip(), "audio": "", "e": {}})
            if audio and not w["audio"]:
                w["audio"] = audio[0]
            e = enrich.get(c["id"])
            if e and len(e) > len(w["e"]):
                w["e"] = e

    def rank(w):
        core = toks(ARTICLE.sub("", w["es"]))
        return max((ranks.get(t, 60000) for t in core), default=60000)

    items = sorted(words.values(), key=lambda w: (rank(w), w["es"].lower()))
    nouns = {}
    for w in items:
        core = toks(ARTICLE.sub("", w["es"]))
        if w["e"].get("pos", "").startswith("nom") and len(core) == 1:
            nouns.setdefault(core[0], w["fr"])
    imgs = images_for(nouns)

    def context_image(w, core):
        """Comme Refold, qui illustre la phrase : un mot sans image propre
        (abstrait, verbe…) prend l'image d'un autre nom illustré de sa phrase
        d'exemple — « el cliente siempre tiene razón » → l'image de cliente."""
        sentence = re.sub(r"<[^>]+>", "", w["e"].get("s", ""))
        for t in toks(sentence):
            if t not in core and imgs.get(t):
                return imgs[t], t
        return None, None

    cards, review = [], []  # review : (carte, nom de la phrase qui fournit l'image ou None)
    for i, w in enumerate(items, 1):
        e = w["e"]
        core = toks(ARTICLE.sub("", w["es"]))
        img = imgs.get(core[0]) if e.get("pos", "").startswith("nom") and len(core) == 1 else None
        via = None
        if not img:
            img, via = context_image(w, core)
        # « il est; elle est; c'est (permanent) » : shown with commas, and only
        # the first meaning (+ its note in brackets) is to type (#88).
        fr = re.sub(r"\s*;\s*", ", ", w["fr"])
        first = w["fr"].split(";")[0].strip()
        note = re.search(r"\([^)]*\)\s*$", w["fr"])
        if note and note.group(0).strip() not in first:
            first += " " + note.group(0).strip()
        card = {"id": str(ID_BASE + i * 10 + 1), "key": i, "es": w["es"], "fr": fr,
                "question": html.escape(w["es"]), "answer": html.escape(fr),
                # No punctuation to type (#90): « ? », « ... » alone are dropped, « (permanent) » → permanent.
                "words": [t for t in (re.sub(r"^[^\w]+|[^\w]+$", "", x) for x in first.split()) if t],
                "tags": ["vocabulaire"]}
        if e.get("pos"): card["pos"] = e["pos"]
        if e.get("s"): card["s"], card["sf"] = e["s"], e.get("sf", "")
        if w["audio"]: card["audioQuestion"] = [w["audio"]]
        if e.get("sa"): card["sa"] = e["sa"]
        if img: card["img"] = img["url"]
        cards.append(card)
        if img: review.append((card, via))

    out = {"version": 1, "source": "Vocabulaire espagnol",
           "decks": [{"id": "vocab-es", "name": DECK_NAME, "cards": cards}]}
    with open(os.path.join(HERE, "vocabulaire.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))

    write_review(review)

    n_s = sum(1 for c in cards if c.get("s"))
    n_i = sum(1 for c in cards if c.get("img"))
    n_a = sum(1 for c in cards if c.get("audioQuestion"))
    print(f"{len(cards)} mots · {n_a} avec audio · {n_s} avec phrase · {n_i} avec image → vocabulaire.json")
    build_apkg(cards)


# ── Planche de relecture des images ─────────────────────────────────────────
REVIEW_HEAD = """<!doctype html><meta charset=utf-8><title>Relecture des images</title>
<style>
body{font:13px -apple-system,sans-serif;margin:0;background:#f6f6f4;color:#222}
header{position:sticky;top:0;z-index:2;background:#fff;border-bottom:1px solid #ddd;padding:10px 16px;
  display:flex;flex-wrap:wrap;gap:10px;align-items:center}
header b{font-size:15px}#count{opacity:.7}#status{font-size:12px;color:#16a34a}
button,label.btn{font:inherit;border:1px solid #ccc;background:#fff;border-radius:16px;padding:5px 12px;cursor:pointer}
button.main{background:#2563eb;color:#fff;border-color:#2563eb}
main{display:flex;flex-wrap:wrap;gap:12px;padding:16px}
figure{margin:0;width:220px;background:#fff;border:1px solid #e3e3e3;border-radius:10px;padding:8px}
figure.done{border-color:#16a34a;background:#f3fbf5}
img{width:220px;height:150px;object-fit:cover;border-radius:6px;display:block}
.w{font-weight:600;margin-top:6px}.via{font-size:11px;color:#b45309}.s{font-size:11px;opacity:.7;margin:2px 0}
textarea{width:100%;box-sizing:border-box;margin-top:6px;font:12px sans-serif;min-height:38px;resize:vertical;
  border:1px solid #ddd;border-radius:6px;padding:4px}
body.hide-done figure.done{display:none}
</style>
<header><b>Relecture des images</b><span id=count></span>
<button class=main onclick="saveFile()">💾 Enregistrer</button>
<label class=btn>📂 Reprendre un fichier<input type=file accept=.json hidden onchange="loadFile(this.files[0])"></label>
<label><input type=checkbox onchange="document.body.classList.toggle('hide-done',this.checked)"> masquer les commentées</label>
<span id=status></span></header>
<main>"""
REVIEW_TAIL = """</main>
<script>
// Chaque commentaire est gardé dans le navigateur dès la frappe ; « Enregistrer »
// (ou ⌘S / Ctrl+S) télécharge images_review_comments.json pour Claude.
const KEY = "vocab_images_review_v1";
let notes = {};
try { notes = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) {}
const figs = [...document.querySelectorAll("figure")];
function persist() {
  try { localStorage.setItem(KEY, JSON.stringify(notes)); } catch (e) {}
  const n = figs.filter(f => notes[f.dataset.key]).length;
  document.getElementById("count").textContent = n + " / " + figs.length + " commentées";
}
function show(f) {
  const t = f.querySelector("textarea");
  t.value = notes[f.dataset.key] || "";
  f.classList.toggle("done", !!t.value.trim());
}
figs.forEach(f => {
  show(f);
  f.querySelector("textarea").addEventListener("input", e => {
    const v = e.target.value;
    if (v.trim()) notes[f.dataset.key] = v; else delete notes[f.dataset.key];
    f.classList.toggle("done", !!v.trim()); persist();
    document.getElementById("status").textContent = "gardé dans le navigateur";
  });
});
persist();
function saveFile() {
  const out = {};
  figs.forEach(f => { if (notes[f.dataset.key]) out[f.dataset.key] = {
    es: f.dataset.es, fr: f.dataset.fr, via: f.dataset.via || null,
    img: f.querySelector("img").src, comment: notes[f.dataset.key] }; });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([JSON.stringify({ saved: new Date().toISOString(), comments: out }, null, 1)],
    { type: "application/json" }));
  a.download = "images_review_comments.json"; a.click();
  document.getElementById("status").textContent = "enregistré à " + new Date().toLocaleTimeString().slice(0, 5)
    + " (Téléchargements)";
}
function loadFile(file) {
  if (!file) return;
  file.text().then(t => {
    const c = JSON.parse(t).comments || {};
    for (const k in c) notes[k] = c[k].comment;
    figs.forEach(show); persist();
    document.getElementById("status").textContent = Object.keys(c).length + " commentaire(s) repris";
  });
}
addEventListener("keydown", e => {
  if ((e.metaKey || e.ctrlKey) && e.key === "s") { e.preventDefault(); saveFile(); }
});
</script>"""


def write_review(review):
    figs = []
    for c, via in review:
        a = lambda v: html.escape(v, quote=True)
        sent = re.sub(r"<[^>]+>", "", c.get("s", ""))
        figs.append(
            f'<figure data-key="{c["key"]}" data-es="{a(c["es"])}" data-fr="{a(c["fr"])}" data-via="{a(via or "")}">'
            f'<img src="{a(c["img"])}" loading="lazy">'
            f'<div class="w">#{c["key"]} {a(c["es"])} — {a(c["fr"])}</div>'
            + (f'<div class="via">image de la phrase : {a(via)}</div><div class="s">{a(sent)}</div>' if via else "")
            + '<textarea placeholder="ton avis…"></textarea></figure>')
    with open(os.path.join(CACHE, "images_review.html"), "w", encoding="utf-8") as f:
        f.write(REVIEW_HEAD + "".join(figs) + REVIEW_TAIL)


# ── .apkg (Anki) ────────────────────────────────────────────────────────────
FRONT = """<div class="rf-word">{{Mot}}</div>
{{#Phrase}}<div class="rf-sent">{{Phrase}}</div>{{/Phrase}}
{{Audio}}"""
BACK = """{{FrontSide}}
<hr id=answer>
<div class="rf-mean">{{Sens}}</div>
{{#Nature}}<div class="rf-pos">{{Nature}}</div>{{/Nature}}
{{#Traduction}}<div class="rf-tr">{{Traduction}}</div>{{/Traduction}}
{{AudioPhrase}}
{{#Image}}<div class="rf-img">{{Image}}</div>{{/Image}}"""
CSS = """.card { font-family: -apple-system, "Segoe UI", sans-serif; text-align: center; font-size: 18px; }
.rf-word { font-size: 40px; font-weight: 600; margin: 4px 0 8px; }
.rf-sent { font-size: 19px; line-height: 1.5; }
.rf-sent b { color: #2563eb; }
.rf-mean { font-size: 24px; font-weight: 600; }
.rf-pos { font-size: 11px; opacity: .55; text-transform: uppercase; letter-spacing: .8px; margin: 4px 0 10px; }
.rf-tr { font-size: 15px; opacity: .7; font-style: italic; }
.rf-img img { max-height: 220px; border-radius: 10px; margin-top: 12px; }"""
FIELDS = ["Clé", "Mot", "Sens", "Nature", "Phrase", "Traduction", "Audio", "AudioPhrase", "Image"]


def build_apkg(cards):
    try:
        from anki.collection import Collection
        from anki.collection import ExportAnkiPackageOptions
    except ImportError:
        print("  (paquet 'anki' absent : pas de .apkg — lancer avec trainervenv/bin/python)")
        return
    import shutil
    import tempfile
    out_path = os.path.join(HERE, "Vocabulaire espagnol.apkg")
    with tempfile.TemporaryDirectory() as tmp:
        col = Collection(os.path.join(tmp, "collection.anki2"))
        try:
            mm = col.models
            m = mm.new("Vocabulaire espagnol (Refold)")
            for name in FIELDS:
                mm.add_field(m, mm.new_field(name))
            t = mm.new_template("Mot → sens")
            t["qfmt"], t["afmt"] = FRONT, BACK
            mm.add_template(m, t)
            m["css"] = CSS
            m["sortf"] = 0
            mm.add(m)
            m = mm.by_name("Vocabulaire espagnol (Refold)")
            did = col.decks.id(DECK_NAME)
            media = col.media.dir()
            for c in cards:
                n = col.new_note(m)
                n["Clé"] = str(c["key"])
                n["Mot"] = html.escape(c["es"])
                n["Sens"] = html.escape(c["fr"])
                n["Nature"] = c.get("pos", "")
                n["Phrase"] = c.get("s", "")
                n["Traduction"] = html.escape(c.get("sf", ""))
                for field, src in (("Audio", (c.get("audioQuestion") or [""])[0]), ("AudioPhrase", c.get("sa", ""))):
                    if src and os.path.exists(os.path.join(HERE, src)):
                        fn = os.path.basename(src)
                        shutil.copy(os.path.join(HERE, src), os.path.join(media, fn))
                        n[field] = f"[sound:{fn}]"
                if c.get("img"):
                    n["Image"] = f'<img src="{c["img"]}">'
                n.tags = ["vocabulaire"] + ([c["pos"].split()[0]] if c.get("pos") else [])
                col.add_note(n, did)
                # Mêmes ids que dans l'appli (ankisync fait le lien après import).
                cid = col.db.scalar("select id from cards where nid = ?", n.id)
                col.db.execute("update cards set id = ? where id = ?", int(c["id"]), cid)
                col.db.execute("update notes set id = ? where id = ?", int(c["id"]) - 1, n.id)
                col.db.execute("update cards set nid = ? where nid = ?", int(c["id"]) - 1, n.id)
            opts = ExportAnkiPackageOptions(with_scheduling=False, with_deck_configs=False,
                                            with_media=True, legacy=False)
            from anki.collection import DeckIdLimit
            col.export_anki_package(out_path=out_path, options=opts, limit=DeckIdLimit(did))
        finally:
            col.close()
    print(f"  → {out_path} ({os.path.getsize(out_path) // 1024} Ko)")


if __name__ == "__main__":
    main()
