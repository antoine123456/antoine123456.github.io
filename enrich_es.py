#!/usr/bin/env python3
"""
enrich_es.py — Données du « rendu complet » des cartes espagnoles (#65).

Pour chaque mot / expression courte de default.json (pas les phrases) :
  - une phrase d'exemple tirée des cartes-phrases du paquet qui contiennent
    ce mot, avec sa traduction et son audio natif (la plus courte, en
    préférant un paquet déjà ouvert : même numéro ou avant) ;
  - la nature / le genre quand ils sont sûrs : el / la / los / las + nom,
    verbe à l'infinitif (-ar, -er, -ir, -se) traduit par un infinitif.
Rien n'est inventé : sans phrase trouvée, la carte n'a que la nature.

Usage :
    python3 enrich_es.py          → enrich_es.json (lu par index.html)
À relancer quand default.json change (nouveaux mots perso, etc.).
"""
import html
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "default.json")
OUT = os.path.join(HERE, "enrich_es.json")

TOKEN = re.compile(r"[a-záéíóúüñ]+(?:'[a-záéíóúüñ]+)?", re.I)
ARTICLE = re.compile(r"^(el|la|los|las|un|una)\s+", re.I)


def plain(q):
    q = re.sub(r"(?s)<style>.*?</style>", "", q)
    return " ".join(re.sub(r"<[^>]+>", " ", q).split())


def sides(card):
    """(espagnol, français, audio espagnol) d'une carte, selon son sens."""
    q = plain(card["question"])
    w = " ".join(card.get("words") or [])
    if "🇪🇸 ➡️ 🇫🇷" in q or card.get("lang") == "es":
        return q.replace("🇪🇸 ➡️ 🇫🇷", "").strip(), w, card.get("audioQuestion") or []
    return w, q.replace("🇫🇷 ➡️ 🇪🇸", "").strip(), card.get("audioAnswer") or []


def deck_rank(name):
    m = re.search(r"(\d+)$", name)
    return int(m.group(1)) if m else 99


def is_sentence(es):
    return len(es.split()) >= 4 or bool(re.search(r"[?!.¿¡]", es))


def toks(s):
    return [t.lower() for t in TOKEN.findall(s)]


def pos_of(es, fr):
    m = ARTICLE.match(es)
    if m:
        art = m.group(1).lower()
        gender = "masculin" if art in ("el", "los", "un") else "féminin"
        return "nom " + gender + (" pluriel" if art in ("los", "las") else "")
    if (len(es.split()) == 1 and re.search(r"(ar|er|ir)(se)?$", es.lower())
            and re.search(r"(er|ir|re|oir)$", fr.lower().split()[-1] if fr else "")):
        return "verbe"
    return ""


def bold(sentence, key):
    """Met en gras les occurrences du mot (mot entier, sans tenir compte de la casse)."""
    out = html.escape(sentence)
    for k in key:
        out = re.sub(r"(?<![\wáéíóúüñ])(" + re.escape(html.escape(k)) + r")(?![\wáéíóúüñ])",
                     r"<b>\1</b>", out, flags=re.I)
    return out


def main():
    with open(SRC, encoding="utf-8") as f:
        decks = json.load(f)["decks"]

    entries = []  # (rang du paquet, es, fr, audio, id de carte)
    for deck in decks:
        rank = deck_rank(deck["name"].split("::")[-1])
        for c in deck["cards"]:
            es, fr, audio = sides(c)
            if es:
                entries.append((rank, es, fr, audio, c["id"]))

    # Phrases disponibles (une par texte espagnol, avec un audio si possible).
    sentences = {}
    for rank, es, fr, audio, _ in entries:
        if not is_sentence(es) or "..." in es or "…" in es:
            continue
        k = es.lower()
        if k not in sentences or (audio and not sentences[k]["audio"]) or rank < sentences[k]["rank"]:
            sentences[k] = {"es": es, "fr": fr, "audio": audio, "rank": rank, "toks": toks(es)}
    pool = list(sentences.values())

    out, with_sentence, words = {}, set(), set()
    for rank, es, fr, audio, cid in entries:
        if is_sentence(es):
            continue
        words.add(es.lower())
        info = {}
        p = pos_of(es, fr)
        if p:
            info["pos"] = p
        core = toks(ARTICLE.sub("", es))
        if core:
            def contains(s):
                t = s["toks"]
                if len(t) < 4 or t == toks(es):
                    return False
                n = len(core)
                return any(t[i:i + n] == core for i in range(len(t) - n + 1))
            cands = [s for s in pool if contains(s)]
            if cands:
                best = min(cands, key=lambda s: (s["rank"] > rank, len(s["toks"]), s["es"]))
                info["s"] = bold(best["es"], [" ".join(core)] if len(core) > 1 else core)
                info["sf"] = best["fr"]
                if best["audio"]:
                    info["sa"] = best["audio"][0]
                with_sentence.add(es.lower())
        if info:
            out[cid] = info

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"{len(words)} mots/expressions · {len(with_sentence)} avec phrase d'exemple · "
          f"{sum(1 for v in out.values() if 'pos' in v)} cartes avec nature/genre → {OUT}")


if __name__ == "__main__":
    main()
