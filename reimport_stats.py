#!/usr/bin/env python3
"""
reimport_stats.py — Réinjecte la progression faite dans Anki Trainer (le
fichier JSON téléchargé par le bouton "📤 Exporter les stats") dans une copie
du deck .apkg d'origine, pour la réimporter ensuite dans le vrai Anki.

Usage :
    pip install anki
    python reimport_stats.py mon_deck.apkg stats.json --out mon_deck_maj.apkg

Puis dans Anki : Fichier → Importer → mon_deck_maj.apkg (les cartes
existantes, identifiées par leur id, seront mises à jour).

Limite assumée, par sécurité : le champ "due" d'Anki n'a pas le même sens
selon l'état d'une carte (position pour une carte neuve, horodatage Unix
empaqueté avec le nombre d'étapes restantes pour une carte en cours
d'apprentissage, décompte de jours pour une carte de révision) — reconstruire
l'état exact d'une carte encore en cours d'apprentissage ("learning" /
"relearning" côté Anki Trainer) risquerait de fausser silencieusement la
planification. Ces cartes sont donc réinjectées comme des cartes de révision
avec un intervalle minimal (1 jour) plutôt que de deviner cet état interne.
Rien d'important n'est perdu : l'ease, les lapses et le nombre de
répétitions sont conservés tels quels.
"""

import argparse
import json
import os
import sys
import tempfile


def main():
    ap = argparse.ArgumentParser(
        description="Réinjecte les stats d'Anki Trainer dans un .apkg pour ré-import dans Anki"
    )
    ap.add_argument("apkg", help="Deck .apkg d'origine (celui donné à extract.py)")
    ap.add_argument("stats", help="Fichier JSON exporté par '📤 Exporter les stats'")
    ap.add_argument("--out", required=True, help="Nouveau .apkg à importer dans Anki")
    args = ap.parse_args()

    try:
        from anki.collection import Collection
        from anki import import_export_pb2 as pb
        from anki import generic_pb2 as generic
        from anki.consts import CARD_TYPE_REV, QUEUE_TYPE_REV
        from anki.errors import NotFoundError
    except ImportError:
        sys.exit("Le paquet 'anki' est requis : pip install anki")

    if not os.path.exists(args.apkg):
        sys.exit(f"Fichier introuvable : {args.apkg}")
    if not os.path.exists(args.stats):
        sys.exit(f"Fichier introuvable : {args.stats}")

    with open(args.stats, encoding="utf-8") as f:
        payload = json.load(f)
    cards_srs = payload.get("cards", {})
    if not cards_srs:
        sys.exit("Aucune carte dans ce fichier de stats.")

    print(f"Ouverture de {os.path.basename(args.apkg)}…")
    with tempfile.TemporaryDirectory() as tmp:
        col_path = os.path.join(tmp, "collection.anki2")
        col = Collection(col_path)
        try:
            req = pb.ImportAnkiPackageRequest(
                package_path=os.path.abspath(args.apkg),
                options=pb.ImportAnkiPackageOptions(),
            )
            col.import_anki_package(req)

            today = col.sched.today  # jours depuis la création de CETTE collection
            updated = 0
            missing = 0
            regraduated = 0

            print(f"Mise à jour de {len(cards_srs)} carte(s)…")
            for card_id_str, srs in cards_srs.items():
                try:
                    cid = int(card_id_str)
                except ValueError:
                    continue
                try:
                    card = col.get_card(cid)
                except NotFoundError:
                    missing += 1
                    continue

                state = srs.get("state", "review")
                ease = float(srs.get("ease", 2.5))
                reps = int(srs.get("reps", 0))
                lapses = int(srs.get("lapses", 0))
                interval = int(srs.get("interval") or 0)

                if state in ("learning", "relearning") or interval < 1:
                    interval = 1
                    regraduated += 1

                card.type = CARD_TYPE_REV
                card.queue = QUEUE_TYPE_REV
                card.ivl = interval
                card.factor = max(1300, round(ease * 1000))
                card.reps = reps
                card.lapses = lapses
                card.due = today + interval
                col.update_card(card)
                updated += 1

            print(f"  ✓ {updated} carte(s) mise(s) à jour"
                  + (f" ({regraduated} encore en apprentissage, graduées à 1 jour)" if regraduated else ""))
            if missing:
                print(f"  ⚠ {missing} id de carte introuvable(s) dans ce deck (deck différent ?)",
                      file=sys.stderr)

            print(f"Export vers {args.out}…")
            export_opts = pb.ExportAnkiPackageOptions(
                with_scheduling=True,
                with_deck_configs=True,
                with_media=True,
                legacy=False,
            )
            limit = pb.ExportLimit(whole_collection=generic.Empty())
            col.export_anki_package(out_path=os.path.abspath(args.out), options=export_opts, limit=limit)
        finally:
            col.close()

    print(f"\n→ {args.out}")
    print("  Dans Anki : Fichier → Importer… ce fichier — les cartes existantes")
    print("  (mêmes ids) seront mises à jour avec la progression d'Anki Trainer.")


if __name__ == "__main__":
    main()
