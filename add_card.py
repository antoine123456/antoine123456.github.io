#!/usr/bin/env python3
"""
add_card.py — Ajoute une paire de cartes (ES→FR et FR→ES) au deck "perso"
de default.json. Utilisé par la fonction bash `cuatroloop` (voir ~/.bashrc) :
chaque mot traduit avec `trans` est ajouté ici sans repasser par extract.py.

Usage :
    python3 add_card.py <mot_espagnol> <traduction_francaise>
"""

import json
import os
import sys
import time

DEFAULT_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "default.json")

# Même bloc de style que les autres cartes "perso" existantes, pour que les
# nouvelles cartes aient un rendu identique dans l'appli.
STYLE = (
    "<style>.card {\n"
    "    font-family: arial;\n"
    "    font-size: 20px;\n"
    "    text-align: center;\n"
    "    color: black;\n"
    "    background-color: white;\n"
    "}\n</style>"
)


def main():
    if len(sys.argv) != 3:
        sys.exit("usage: add_card.py <mot_espagnol> <traduction_francaise>")
    es, fr = sys.argv[1].strip(), sys.argv[2].strip()
    if not es or not fr:
        sys.exit("mot ou traduction vide, rien d'ajouté")

    with open(DEFAULT_JSON, encoding="utf-8") as f:
        data = json.load(f)

    deck = next((d for d in data["decks"] if d["name"].split("::")[-1] == "perso"), None)
    if deck is None:
        root = data["decks"][0]["name"].split("::")[0] if data["decks"] else "Perso"
        deck = {"id": str(int(time.time() * 1000)), "name": root + "::perso", "cards": []}
        data["decks"].append(deck)

    base_id = int(time.time() * 1000)
    deck["cards"].append({
        "id": str(base_id),
        "question": STYLE + es,
        "words": fr.split(),
        "tags": ["cuatroloop"],
    })
    deck["cards"].append({
        "id": str(base_id + 1),
        "question": STYLE + fr,
        "words": es.split(),
        "tags": ["cuatroloop"],
    })

    with open(DEFAULT_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
