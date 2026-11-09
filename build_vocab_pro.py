#!/usr/bin/env python3
"""
build_vocab_pro.py — les mots fréquents du Vocabulaire (#161, #170).

Les mots qu'on entend le plus dans les films et séries espagnols (liste de
fréquences FrequencyWords 2018, tirée des sous-titres OpenSubtitles) et qui
manquaient aux paquets de l'appli. La liste a été regroupée par mot du
dictionnaire (quería → querer), puis triée à la main : ni prénoms, ni
anglais, ni abréviations, ni interjections, ni grossièretés, ni grammaire
(pronoms, démonstratifs, formes conjuguées : c'est le paquet Grammaire).
Chaque mot a sa nature, son sens en français et en italien, et une phrase
d'exemple écrite pour lui (lue par la voix du navigateur) — vocab_pro.tsv.

Ce ne sont pas un paquet à part : build_vocab.py les range dans les niveaux
du Vocabulaire (et du Vocabolario) selon leur fréquence, avec leurs propres
ids (rang × 100). Lancer build_vocab.py ; ce script seul vérifie la liste :
    python3 build_vocab_pro.py
"""
import html
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from build_vocab import typed_meanings, words_to_type  # noqa: E402

STEPS = [1000, 2000, 3000, 5000, 10000]
LANGS = {
    "fr": {"source": "Mots fréquents", "deck": "🇪🇸 Mots fréquents", "step": "Étape", "json": "vocab_pro.json",
           "id_base": 1_104_000_000_000, "deck_id": "vocab-pro"},
    "it": {"source": "Parole frequenti (italiano)", "deck": "🇪🇸 Parole frequenti", "step": "Tappa", "json": "vocab_pro_it.json",
           "id_base": 1_105_000_000_000, "deck_id": "vocab-pro-it"},
}
POS_IT = {"nom masculin": "sostantivo maschile", "nom féminin": "sostantivo femminile", "verbe": "verbo",
          "adjectif": "aggettivo", "adverbe": "avverbio", "conjonction": "congiunzione", "préposition": "preposizione",
          "expression": "espressione", "interjection": "interiezione"}


def step_of(rank):
    for n, top in enumerate(STEPS, 1):
        if rank <= top:
            return n
    return len(STEPS)


def rows():
    out = []
    with open(os.path.join(HERE, "vocab_pro.tsv"), encoding="utf-8") as f:
        for line in f:
            if line.startswith("#") or not line.strip():
                continue
            p = line.rstrip("\n").split("\t")
            if len(p) not in (8, 9):
                raise SystemExit("ligne incomplète : " + line)
            out.append(dict(zip(["rank", "es", "pos", "fr", "it", "s", "sf", "sit", "tags"], p)))
    return out


def card(r, lang, n_same_rank):
    L = LANGS[lang]
    rank = int(r["rank"])
    meaning = r["fr"] if lang == "fr" else r["it"]
    shown = re.sub(r"\s*;\s*", ", ", meaning)
    words, sep = typed_meanings(meaning)
    c = {"id": str(L["id_base"] + rank * 100 + n_same_rank * 10 + 1), "key": rank, "es": r["es"], "fr": shown,
         "question": html.escape(r["es"]), "answer": html.escape(shown),
         "words": words or words_to_type(meaning),
         "tags": ["vocabulaire"] + [t.strip() for t in r.get("tags", "").split(",") if t.strip()],
         "pos": r["pos"] if lang == "fr" else POS_IT.get(r["pos"], r["pos"]),
         "s": r["s"], "sf": r["sf"] if lang == "fr" else r["sit"], "sg": True}
    if sep:
        c["sep"] = sep
    return c


def deck_json(cards, lang):
    L = LANGS[lang]
    decks = []
    for n in range(1, len(STEPS) + 1):
        cs = [c for c in cards if step_of(c["key"]) == n]
        if not cs:
            continue
        lo = 1 if n == 1 else STEPS[n - 2] + 1
        decks.append({"id": f"{L['deck_id']}-{n}", "name": f"{L['deck']}::{L['step']} {n}", "range": [lo, STEPS[n - 1]], "cards": cs})
    return {"version": 1, "source": L["source"], "decks": decks}


def main():
    rs = rows()
    print(f"{len(rs)} mots fréquents dans vocab_pro.tsv — à construire avec build_vocab.py")


if __name__ == "__main__":
    main()
