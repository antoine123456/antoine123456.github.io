#!/usr/bin/env python3
"""
cli_firestore.py — logique partagée pour écrire dans le deck "Perso" PERSONNEL
d'un utilisateur, directement dans Firestore (utilisé par add_card.py et
migrate_perso.py). Voir la section "Outil en ligne de commande" du README
pour l'installation et la configuration.

Chaque utilisateur a son propre deck "Perso" sous users/{uid}/sources/perso —
donc plus question d'un seul default.json partagé par tout le monde. Pas de
"log in" ici : impossible de faire un popup Google depuis un script, donc on
identifie l'utilisateur via un simple menu (nom -> uid Firebase déjà connu),
choisi une fois et mémorisé localement.
"""

import json
import os
import re
import sys
import time

CONFIG_PATH = os.path.expanduser("~/.espanol_trainer_cli.json")

STYLE = (
    "<style>.card {\n"
    "    font-family: arial;\n"
    "    font-size: 20px;\n"
    "    text-align: center;\n"
    "    color: black;\n"
    "    background-color: white;\n"
    "}\n</style>"
)

SOURCE_ID = "perso"
DECK_ID = "perso-deck"
DECK_NAME = "Perso"
CHUNK_SIZE = 900000  # bien en dessous de la limite Firestore de 1 MiB par doc


def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    try:
        os.chmod(CONFIG_PATH, 0o600)
    except OSError:
        pass


def ensure_service_account(cfg):
    if cfg.get("serviceAccountPath"):
        return
    print("Il faut une clé de compte de service Firebase (Admin SDK) :")
    print("  Console Firebase -> icone d'engrenage -> Paramètres du projet")
    print("  -> onglet 'Comptes de service' -> 'Générer une nouvelle clé privée'")
    print("  -> un fichier .json se télécharge.")
    print()
    print("  /!\\ Cette clé donne un accès ADMIN à toute la base Firestore.")
    print("      Ne la commitez JAMAIS dans git, ne la partagez avec personne.")
    print("      Elle n'est PAS la même chose que le 'apiKey' public du site.")
    print()
    key_path = input("Chemin vers ce fichier .json : ").strip()
    key_path = os.path.abspath(os.path.expanduser(key_path))
    if not os.path.isfile(key_path):
        sys.exit("fichier introuvable : " + key_path)
    cfg["serviceAccountPath"] = key_path
    save_config(cfg)


def slugify(name):
    """Même règle que KNOWN_USERS côté index.html (minuscules + tirets), pour
    que le même nom donne le même id des deux côtés sans rien copier-coller."""
    return re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")


def add_user_interactive(cfg):
    print("Nouvel utilisateur :")
    name = input("  nom (ex: Quang) : ").strip()
    if not name:
        sys.exit("nom vide, abandon")
    uid = slugify(name)
    if not uid:
        sys.exit("nom invalide (aucune lettre/chiffre), abandon")
    cfg.setdefault("users", []).append({"name": name, "uid": uid})
    cfg["lastUser"] = name
    save_config(cfg)
    print("-> ajouté aussi KNOWN_USERS dans index.html si ce n'est pas déjà fait :")
    print('   { id: "' + uid + '", name: "' + name + '" }')
    return uid


def pick_user_interactive(cfg):
    users = cfg.get("users", [])
    print("Pour qui sont ces mots ?")
    for i, u in enumerate(users, 1):
        print("  " + str(i) + ") " + u["name"])
    add_idx = len(users) + 1
    print("  " + str(add_idx) + ") + ajouter un nouvel utilisateur")
    choice = input("Choix : ").strip()
    if choice == str(add_idx) or not choice:
        return add_user_interactive(cfg)
    try:
        u = users[int(choice) - 1]
    except (ValueError, IndexError):
        sys.exit("choix invalide")
    cfg["lastUser"] = u["name"]
    save_config(cfg)
    return u["uid"]


def resolve_uid(cfg, force_menu=False):
    users = cfg.get("users", [])
    if not users:
        return add_user_interactive(cfg)
    if not force_menu:
        last = next((u for u in users if u["name"] == cfg.get("lastUser")), None)
        if last:
            return last["uid"]
    return pick_user_interactive(cfg)


def get_client(force_menu=False):
    """Charge (ou crée) la config, retourne (db, uid)."""
    try:
        import firebase_admin
        from firebase_admin import credentials, firestore
    except ImportError:
        sys.exit("pip install firebase-admin")

    cfg = load_config()
    ensure_service_account(cfg)
    uid = resolve_uid(cfg, force_menu=force_menu)

    if not firebase_admin._apps:
        cred = credentials.Certificate(cfg["serviceAccountPath"])
        firebase_admin.initialize_app(cred)

    return firestore.client(), uid


def _chunk_string(s):
    if not s:
        return [""]
    return [s[i:i + CHUNK_SIZE] for i in range(0, len(s), CHUNK_SIZE)]


def _norm_front(card):
    q = card.get("question", "")
    if q.startswith(STYLE):
        q = q[len(STYLE):]
    return q.strip().lower()


def load_perso_cards(db, uid):
    """Retourne la liste des cartes actuelles du deck Perso (ou [])."""
    chunk_col = db.collection("users").document(uid).collection("sources").document(SOURCE_ID).collection("cardChunks")
    docs = sorted(chunk_col.stream(), key=lambda d: d.to_dict().get("index", 0))
    if not docs:
        return []
    joined = "".join(d.to_dict().get("data", "") for d in docs)
    if not joined:
        return []
    try:
        by_deck = json.loads(joined)
    except (ValueError, TypeError):
        return []
    return by_deck.get(DECK_ID, [])


def write_perso_cards(db, uid, cards):
    """Écrase le deck Perso avec la liste de cartes donnée, et met à jour
    l'entrée du deck dans users/{uid}.sources pour qu'il apparaisse à l'écran
    d'accueil de l'appli."""
    src_ref = db.collection("users").document(uid).collection("sources").document(SOURCE_ID)
    chunk_col = src_ref.collection("cardChunks")

    payload = json.dumps({DECK_ID: cards}, ensure_ascii=False)
    chunks = _chunk_string(payload)

    for d in list(chunk_col.stream()):
        d.reference.delete()
    for i, chunk in enumerate(chunks):
        chunk_col.document(str(i)).set({"data": chunk, "index": i, "total": len(chunks)})

    from firebase_admin import firestore
    if not src_ref.get().exists:
        src_ref.set({"srs": {}, "newCount": {}, "flagged": {}, "updatedAt": firestore.SERVER_TIMESTAMP})
    else:
        src_ref.set({"updatedAt": firestore.SERVER_TIMESTAMP}, merge=True)

    user_ref = db.collection("users").document(uid)
    user_doc = user_ref.get()
    data = user_doc.to_dict() if user_doc.exists else {}
    sources = data.get("sources", [])
    entry = {"id": SOURCE_ID, "name": DECK_NAME, "isDefault": False,
              "decks": [{"id": DECK_ID, "name": DECK_NAME, "cardCount": len(cards)}]}
    sources = [s for s in sources if s.get("id") != SOURCE_ID] + [entry]
    user_ref.set({"sources": sources, "updatedAt": firestore.SERVER_TIMESTAMP}, merge=True)


def add_pair(db, uid, w1, w2, lang1="es"):
    """Ajoute la paire w1/w2 au deck Perso, sauf si l'un des deux mots y est
    déjà (comparaison insensible à la casse). Retourne le nombre total de
    cartes après ajout, ou None si la paire existait déjà (rien fait)."""
    lang2 = "fr" if lang1 == "es" else "es"
    cards = load_perso_cards(db, uid)
    existing = {_norm_front(c) for c in cards}
    if w1.strip().lower() in existing or w2.strip().lower() in existing:
        return None

    base_id = int(time.time() * 1000)
    cards.append({"id": str(base_id), "question": STYLE + w1, "words": w2.split(),
                  "tags": ["cuatroloop"], "lang": lang1})
    cards.append({"id": str(base_id + 1), "question": STYLE + w2, "words": w1.split(),
                  "tags": ["cuatroloop"], "lang": lang2})
    write_perso_cards(db, uid, cards)
    return len(cards)
