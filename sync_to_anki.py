#!/usr/bin/env python3
"""
sync_to_anki.py — Pousse en une commande la progression faite dans Anki
Trainer (les fichiers téléchargés par "📤 Exporter les stats") directement
dans la collection Anki locale. Pas besoin du .apkg d'origine ni d'import
manuel : au prochain lancement d'Anki, une synchro normale envoie le tout
sur AnkiWeb.

Usage (Anki doit être FERMÉ) :
    python sync_to_anki.py                  # tous les *_stats*.json de ~/Downloads
    python sync_to_anki.py stats.json ...   # fichiers précis
    python sync_to_anki.py --dry-run        # montre ce qui changerait, n'écrit rien

Règles :
- Seules les cartes réellement étudiées dans Anki Trainer (champ
  "lastReview") sont poussées ; si plusieurs fichiers parlent de la même
  carte, le plus récent gagne — on peut donc relancer sans risque sur tous
  les téléchargements accumulés.
- Une carte révisée dans Anki APRÈS sa dernière révision dans Anki Trainer
  n'est pas touchée (Anki a la version la plus récente).
- Chaque carte mise à jour reçoit une entrée d'historique "Manuel" datée de
  sa révision dans Anki Trainer : c'est ce qui rend la commande idempotente
  (une 2e exécution ne réécrit rien) et laisse une trace dans les stats Anki.
- Comme reimport_stats.py, les cartes en (ré)apprentissage sont réinjectées
  comme cartes de révision à 1 jour plutôt que de deviner l'état interne
  d'Anki ; ease, lapses et répétitions sont conservés.
- Les mots du deck "perso" de default.json (add_card.py / cuatroloop) absents
  d'Anki y sont créés d'abord (une note "Basic (and reversed card)" par
  paire, avec les ids de cartes de l'appli), sauf doublon ou traduction
  identique au mot d'origine.
- Une sauvegarde Anki est créée avant toute écriture (dossier backups/ du
  profil, restaurable via Fichier → Changer de profil → Ouvrir une sauvegarde).
"""

import argparse
import glob
import json
import os
import re
import subprocess
import sys
import time

ANKI_BASE = os.path.expanduser("~/Library/Application Support/Anki2")
REVLOG_MANUAL = 4
DEFAULT_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "default.json")


def find_collection(profile):
    if not os.path.isdir(ANKI_BASE):
        sys.exit(f"Dossier Anki introuvable : {ANKI_BASE} (utilise --collection)")
    profiles = sorted(p for p in os.listdir(ANKI_BASE)
                      if os.path.isfile(os.path.join(ANKI_BASE, p, "collection.anki2")))
    if profile:
        if profile not in profiles:
            sys.exit(f"Profil '{profile}' introuvable. Profils : {', '.join(profiles)}")
        return os.path.join(ANKI_BASE, profile, "collection.anki2")
    if len(profiles) != 1:
        sys.exit(f"Plusieurs profils Anki ({', '.join(profiles)}) : précise --profile")
    return os.path.join(ANKI_BASE, profiles[0], "collection.anki2")


def anki_is_running():
    try:
        out = subprocess.run(["pgrep", "-if", "Anki.app/Contents/MacOS"],
                             capture_output=True, text=True)
        return out.returncode == 0
    except FileNotFoundError:
        return False


def load_latest_entries(paths):
    """card id -> entrée SRS la plus récemment révisée parmi tous les fichiers."""
    latest = {}
    for path in paths:
        with open(path, encoding="utf-8") as f:
            cards = json.load(f).get("cards", {})
        for cid, srs in cards.items():
            if not srs.get("lastReview"):
                continue  # jamais étudiée dans Anki Trainer (état repris d'Anki)
            if cid not in latest or srs["lastReview"] > latest[cid]["lastReview"]:
                latest[cid] = srs
    return latest


def strip_style(question):
    return re.sub(r"(?s)<style>.*?</style>", "", question).strip()


def add_perso_notes(col, dry_run):
    """Crée dans Anki les mots du deck "perso" de default.json (ajoutés par
    add_card.py / cuatroloop) qui n'y sont pas encore : une note "Basic (and
    reversed card)" par paire, dont les 2 cartes reçoivent les ids de
    l'appli — leur progression se synchronise ensuite comme les autres."""
    with open(DEFAULT_JSON, encoding="utf-8") as f:
        deck = next((d for d in json.load(f)["decks"]
                     if d["name"].split("::")[-1] == "perso"), None)
    if deck is None:
        return
    cards = {int(c["id"]): c for c in deck["cards"]}
    exists = lambda cid: col.db.scalar("select 1 from cards where id = ?", cid)

    pairs, done = [], set()
    for cid in sorted(cards):
        if cid in done or exists(cid):
            continue
        front, back = strip_style(cards[cid]["question"]), " ".join(cards[cid]["words"])
        partner = cards.get(cid + 1)
        if partner and not exists(cid + 1) and strip_style(partner["question"]) == back:
            done.add(cid + 1)
            pairs.append((cid, front, back, cards[cid].get("tags", []), True))
        else:
            pairs.append((cid, front, back, cards[cid].get("tags", []), False))
    if not pairs:
        return

    reversed_nt = col.models.by_name("Basic (and reversed card)")
    basic_nt = col.models.by_name("Basic")
    deck_id = None if dry_run else col.decks.id(deck["name"])
    created, skipped, seen = [], [], set()
    for cid, front, back, tags, is_pair in pairs:
        # Même mot déjà présent dans Anki (n'importe quelle note) → pas de doublon.
        if (front.lower() in seen or front.lower() == back.lower()
                or col.find_notes(col.build_search_string(f'"front:{front}"'))):
            skipped.append(front)
            continue
        seen.add(front.lower())
        created.append(f"{front} ↔ {back}" if is_pair else f"{front} → {back}")
        if dry_run:
            continue
        note = col.new_note(reversed_nt if is_pair else basic_nt)
        note["Front"], note["Back"] = front, back
        note.tags = tags
        col.add_note(note, deck_id)
        # Ids de l'appli (jamais synchronisées encore, usn -1 : renommage sans risque).
        for card in sorted(note.cards(), key=lambda c: c.ord):
            col.db.execute("update cards set id = ? where id = ?", cid + card.ord, card.id)
        if not col.db.scalar("select 1 from notes where id = ?", cid):
            col.db.execute("update notes set id = ? where id = ?", cid, note.id)
            col.db.execute("update cards set nid = ? where nid = ?", cid, note.id)

    verb = "seraient créées" if dry_run else "créée(s)"
    if created:
        print(f"  ✓ perso : {len(created)} note(s) {verb} dans « {deck['name']} »")
        for c in created:
            print(f"      {c}")
    if skipped:
        print(f"  = perso : {len(skipped)} ignorée(s) (déjà dans Anki, ou traduction identique) : "
              + ", ".join(skipped))


def main():
    ap = argparse.ArgumentParser(
        description="Pousse la progression d'Anki Trainer dans la collection Anki locale"
    )
    ap.add_argument("stats", nargs="*",
                    help="Fichiers JSON exportés (défaut : ~/Downloads/*_stats*.json)")
    ap.add_argument("--profile", help="Profil Anki (si plusieurs)")
    ap.add_argument("--collection", help="Chemin explicite vers un collection.anki2")
    ap.add_argument("--dry-run", action="store_true", help="N'écrit rien")
    args = ap.parse_args()

    try:
        from anki.collection import Collection
        from anki.consts import CARD_TYPE_REV, QUEUE_TYPE_REV
        from anki.errors import NotFoundError
    except ImportError:
        sys.exit("Le paquet 'anki' est requis : pip install anki")

    paths = args.stats or sorted(glob.glob(os.path.expanduser("~/Downloads/*_stats*.json")))
    entries = load_latest_entries(paths)
    print(f"{len(paths)} fichier(s) de stats, {len(entries)} carte(s) étudiée(s) dans Anki Trainer.")

    col_path = os.path.abspath(args.collection) if args.collection else find_collection(args.profile)
    if not args.collection and anki_is_running():
        sys.exit("Anki est ouvert : ferme-le d'abord (sinon la collection est verrouillée).")

    print(f"Collection : {col_path}")
    col = Collection(col_path)
    try:
        if not args.dry_run:
            backups = os.path.join(os.path.dirname(col_path), "backups")
            os.makedirs(backups, exist_ok=True)
            col.create_backup(backup_folder=backups, force=True, wait_for_completion=True)
            print(f"  sauvegarde créée dans {backups}")

        add_perso_notes(col, args.dry_run)

        today = col.sched.today
        today_stamp = int(time.time() // 86400)  # même jour "UTC" que dayStamp() côté app
        updated = newer_in_anki = missing = regraduated = 0

        for cid_str, srs in entries.items():
            cid = int(cid_str)
            try:
                card = col.get_card(cid)
            except NotFoundError:
                missing += 1
                continue

            last_anki = col.db.scalar("select max(id) from revlog where cid = ?", cid) or 0
            if last_anki >= srs["lastReview"]:
                newer_in_anki += 1
                continue

            interval = int(srs.get("interval") or 0)
            if srs.get("state") in ("learning", "relearning") or interval < 1:
                interval = 1
                due_in = 1
                regraduated += 1
            else:
                due_in = int(srs.get("due", today_stamp + interval)) - today_stamp

            last_ivl = card.ivl
            card.type = CARD_TYPE_REV
            card.queue = QUEUE_TYPE_REV
            card.ivl = interval
            card.factor = max(1300, round(float(srs.get("ease", 2.5)) * 1000))
            card.reps = int(srs.get("reps", card.reps))
            card.lapses = int(srs.get("lapses", card.lapses))
            card.due = today + due_in
            updated += 1
            if args.dry_run:
                continue
            col.update_card(card)

            # Entrée d'historique "Manuel" à l'heure de la révision dans l'app
            # (id de revlog = timestamp ms, doit être unique).
            rid = int(srs["lastReview"])
            while col.db.scalar("select 1 from revlog where id = ?", rid):
                rid += 1
            col.db.execute(
                "insert into revlog (id, cid, usn, ease, ivl, lastIvl, factor, time, type)"
                " values (?, ?, ?, 0, ?, ?, ?, 0, ?)",
                rid, cid, -1, interval, last_ivl, card.factor, REVLOG_MANUAL,
            )
    finally:
        col.close()

    verb = "seraient mises à jour" if args.dry_run else "mise(s) à jour"
    print(f"  ✓ {updated} carte(s) {verb}"
          + (f" ({regraduated} en apprentissage → révision à 1 jour)" if regraduated else ""))
    if newer_in_anki:
        print(f"  = {newer_in_anki} déjà à jour (révisées plus récemment dans Anki, ou déjà synchronisées)")
    if missing:
        print(f"  ⚠ {missing} id(s) de carte absents de cette collection", file=sys.stderr)
    if updated and not args.dry_run:
        print("\n→ Ouvre Anki et synchronise : la progression part sur AnkiWeb.")


if __name__ == "__main__":
    main()
