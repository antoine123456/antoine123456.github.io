#!/usr/bin/env python3
"""
add_card.py — Ajoute une paire de cartes (mot1 <-> mot2) au deck "Perso"
PERSONNEL choisi via un petit menu, directement dans Firestore. Utilisé par
les fonctions bash `cuatroloop`/`tresloop` (voir ~/.bashrc et la section
"Outil en ligne de commande" du README).

Au premier lancement, demande la clé de compte de service Firebase puis
propose de créer un utilisateur (juste un nom — l'id est dérivé du nom, voir
slugify() dans cli_firestore.py, pour matcher KNOWN_USERS d'index.html). Pas
de "log in" Google ici : juste un menu, mémorisé localement pour les fois
suivantes tant qu'un seul utilisateur existe.

Usage :
    python3 add_card.py <mot1> <mot2> [lang1: es|fr]
    python3 add_card.py --user        # rouvre le menu pour changer d'utilisateur

lang1 est la langue du premier mot ("es" ou "fr", "es" par défaut — c'est le
cas de cuatroloop) ; le second mot est supposé être dans l'autre langue.
Sert uniquement à choisir la voix pour la synthèse vocale côté appli.
"""

import sys

from cli_firestore import add_pair, get_client


def main():
    if len(sys.argv) == 2 and sys.argv[1] == "--user":
        get_client(force_menu=True)
        return

    if len(sys.argv) not in (3, 4):
        sys.exit("usage: add_card.py <mot1> <mot2> [lang1: es|fr]")
    w1, w2 = sys.argv[1].strip(), sys.argv[2].strip()
    lang1 = sys.argv[3].strip() if len(sys.argv) == 4 else "es"
    if not w1 or not w2:
        sys.exit("mot ou traduction vide, rien d'ajouté")

    db, uid = get_client()
    total = add_pair(db, uid, w1, w2, lang1)
    if total is None:
        print("perso: déjà présent, rien ajouté")
    else:
        print("perso: " + str(total) + " carte(s) au total")


if __name__ == "__main__":
    main()
