#!/usr/bin/env python3
"""
img_themes.py — images pour les animaux et les parties du corps du
Vocabulaire (#199), là où build_vocab.py n'en a pas trouvé (Wikidata veut un
libellé espagnol identique au mot : « gato » ≠ « Felis catus »).

L'image est celle de l'article Wikipédia en français du premier sens
(le chat → « Chat »), sauf page d'homonymie. Les choix faits à la main sont
dans FIX (un nom de fichier Wikimedia, ou None = pas d'image). Seulement
pour les cartes taguées « animaux » ou « corps » (tag_vocab.py) sans image ;
le Vocabolario italien reçoit les mêmes (même mot espagnol).

Appelé par build_vocab.py après tag_vocab.py ; se lance aussi seul :
    python3 img_themes.py            # écrit les deux JSON
    python3 img_themes.py --review   # + .cache/themes_review.html pour vérifier
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, ".cache", "theme_images.json")
THEMES = ("animaux", "corps")
UA = {"User-Agent": "espanol-trainer/1.0 (https://github.com/antoine123456/antoine123456.github.io; vocabulary images)"}
FR_ART = re.compile(r"^(le |la |les |l'|un |une |des )", re.I)

# mot espagnol → fichier Wikimedia choisi à la main, ou None (pas d'image :
# l'article Wikipédia montre autre chose que le mot)
FIX = {
    # the French word lands on a disambiguation page: the article of the precise sense
    "el brazo": "Gray1231.png", "la garganta": "Throat_Diagram.png",
    "el cuerno": "Antilope_cervicapra_rupicapra_Hardwicke_2.jpg", "la garra": "Cat_claw_closeup.jpg",
    "el pulgar": "Thumbup.jpg", "la pulgada": "Дюйм_2,54.jpg", "el ciervo": "Cervus_elaphus_Luc_Viatour_6.jpg",
    # the article's image shows something else (or nothing that speaks)
    "el cerebro": "Skull_and_brain_normal_human.svg",
    "el cuervo": "Corvus_corax_(Common_Raven),_Yosemite_NP,_CA,_US_-_Diliff.jpg",
    "el aliento": None, "la mejilla": None, "la mandíbula": None,
}


def get_json(url, tries=5):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                time.sleep(1)
                return json.load(r)
        except urllib.error.HTTPError as e:  # 429: wait as told
            time.sleep(min(float(e.headers.get("Retry-After") or 10 * (i + 1)), 120))
        except Exception:
            time.sleep(5 * (i + 1))
    return None


def head_word(fr):
    w = re.sub(r"\(.*?\)", "", fr.split(",")[0].split(";")[0]).strip()
    return FR_ART.sub("", w).strip()


def wiki_images(words):
    """Image principale de l'article fr.wikipedia de chaque mot, par lots de
    50 titres (une requête) : {mot: fichier ou None}."""
    out = {}
    for k in range(0, len(words), 50):
        chunk = words[k:k + 50]
        titles = {w[:1].upper() + w[1:]: w for w in chunk}
        q = urllib.parse.urlencode({"action": "query", "titles": "|".join(titles), "redirects": 1,
                                    "prop": "pageimages|pageprops", "piprop": "name", "pilimit": 50,
                                    "format": "json", "formatversion": 2})
        res = (get_json("https://fr.wikipedia.org/w/api.php?" + q) or {}).get("query")
        if res is None:
            continue  # not answered: tried again next time
        alias = {}
        for r in (res.get("normalized") or []) + (res.get("redirects") or []):
            alias[r["to"]] = alias.get(r["from"], r["from"])
        for p in res.get("pages") or []:
            t = p["title"]
            while t in alias and t not in titles:
                t = alias[t]
            w = titles.get(t)
            if w is None:
                continue
            bad = p.get("missing") or "disambiguation" in (p.get("pageprops") or {})
            out[w] = None if bad else p.get("pageimage")
        for w in chunk:
            out.setdefault(w, None)
    return out


def url_of(file):
    return "https://commons.wikimedia.org/wiki/Special:FilePath/" + urllib.parse.quote(file.replace(" ", "_")) + "?width=500"


def main(review=False):
    path = os.path.join(HERE, "vocabulaire.json")
    data = json.load(open(path, encoding="utf-8"))
    cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
    todo = [c for d in data["decks"] for c in d["cards"]
            if set(THEMES) & set(c.get("tags", [])) and not c.get("img")]
    missing = sorted({head_word(c["fr"]) for c in todo} - set(cache))
    if missing:
        cache.update(wiki_images(missing))
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=0)
    added, rows = {}, []
    for c in todo:
        file = FIX[c["es"]] if c["es"] in FIX else cache.get(head_word(c["fr"]))
        rows.append((c["es"], c["fr"], file))
        if file:
            c["img"] = added[c["es"]] = url_of(file)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    path_it = os.path.join(HERE, "vocabolario.json")
    if os.path.exists(path_it):
        it = json.load(open(path_it, encoding="utf-8"))
        for d in it["decks"]:
            for c in d["cards"]:
                if not c.get("img") and c["es"] in added:
                    c["img"] = added[c["es"]]
        with open(path_it, "w", encoding="utf-8") as f:
            json.dump(it, f, ensure_ascii=False, separators=(",", ":"))
    print(f"images animaux / corps : {len(added)} ajoutée(s), {len(todo) - len(added)} sans image")
    if review:
        cells = "".join(f'<figure><img src="{url_of(f).replace("width=500", "width=160")}" loading="lazy"><figcaption><b>{es}</b><br>{fr}</figcaption></figure>'
                        if f else f'<figure class="none"><div>—</div><figcaption><b>{es}</b><br>{fr}</figcaption></figure>' for es, fr, f in rows)
        out = os.path.join(HERE, ".cache", "themes_review.html")
        with open(out, "w", encoding="utf-8") as f:
            f.write('<meta charset="utf-8"><style>body{font:12px sans-serif;display:flex;flex-wrap:wrap;gap:6px}'
                    'figure{margin:0;width:150px}img{width:150px;height:110px;object-fit:cover;background:#eee}'
                    '.none div{width:150px;height:110px;background:#fdd;display:flex;align-items:center;justify-content:center}</style>' + cells)
        print("à vérifier :", out)


if __name__ == "__main__":
    main(review="--review" in sys.argv)
