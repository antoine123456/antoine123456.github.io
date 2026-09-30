#!/usr/bin/env python3
"""
migrate_perso.py — Outil ponctuel : reprend les paires de mots qui étaient
dans le deck "perso" partagé de default.json (avant qu'il ne soit retiré) et
les pousse dans le deck Perso Firestore du compte choisi lors du premier
lancement de add_card.py. À lancer une seule fois, si besoin.
"""

from cli_firestore import add_pair, get_client

# Paires reconstruites depuis l'ancien deck "🇪🇸 Espagnol::perso" de default.json.
PAIRS = [
    ("proxima", "prochaine"),
    ("ultima", "dernière"),
    ("almorzar", "déjeuner"),
    ("miedo", "peur"),
    ("sentir", "sentir"),
    ("ressentir", "ressentir"),
    ("pajaro", "oiseau"),
    ("nadie", "personne"),
    ("cuida", "prends soin de toi"),
    ("ladron", "voleurs"),
    ("prendar", "attraper"),
    ("prendaste", "je me suis habillé"),
    ("mover", "déménageur"),
    ("hueles rico", "tu sens bon"),
    ("orage", "orage"),
]


def main():
    db, uid = get_client()
    for w1, w2 in PAIRS:
        add_pair(db, uid, w1, w2, "es")
        print("ajouté : " + w1 + " <-> " + w2)
    print("terminé, " + str(len(PAIRS)) + " paires migrées.")


if __name__ == "__main__":
    main()
