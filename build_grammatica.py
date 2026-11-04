#!/usr/bin/env python3
"""
build_grammatica.py — « Grammatica spagnola » : le paquet Grammaire avec les
consignes en italien (#110).

Les phrases espagnoles et les réponses ne changent pas ; seuls passent en
italien le sens des verbes, le nom des temps et les indications entre
parenthèses des cartes de règles. Les étiquettes (verbe, temps, etapeN) sont
gardées : le tableau de conjugaison (F1 maintenu) et les étapes 🔒 marchent
pareil. La progression enregistrée dans grammaire.json n'est pas reprise.

Usage :
    python3 build_grammatica.py      → grammatica.json
Un texte français resté sans traduction arrête le script (à ajouter ci-dessous).
"""
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ID_BASE = 1_102_000_000_000  # ids dans le passé, hors des autres paquets (cf. build_vocab.py)

DECKS = {"🇪🇸 Espagnol::Grammaire::Conjugaison": "🇪🇸 Spagnolo::Grammatica::Coniugazione",
         "🇪🇸 Espagnol::Grammaire::Règles": "🇪🇸 Spagnolo::Grammatica::Regole"}

# Texte entre parenthèses (sens du verbe, indication de règle) : français → italien.
PAREN = {
    "manger": "mangiare", "dire": "dire", "dormir": "dormire", "plaire → j'aimerais…": "piacere → mi piacerebbe…",
    "parler": "parlare", "faire": "fare", "aller": "andare", "jouer": "giocare",
    "demander, commander": "chiedere, ordinare", "penser": "pensare", "pouvoir": "potere",
    "vouloir, aimer": "volere, amare", "savoir": "sapere", "être": "essere", "avoir": "avere", "vivre": "vivere",
    "être (état, lieu)": "essere, stare (stato, luogo)",
    "ser / estar — un événement": "ser / estar — un evento",
    "por / para — destination": "por / para — destinazione",
    "por / para — à travers": "por / para — attraverso",
    "por / para — but": "por / para — scopo",
    "pronom complément direct": "pronome complemento oggetto",
    "pronom complément indirect": "pronome complemento di termine",
    "deux pronoms (le + lo)": "due pronomi (le + lo)",
    "venir — subjonctif": "venir — congiuntivo",
    "llegar — subjonctif": "llegar — congiuntivo",
    "llegar — subjonctif après cuando (futur)": "llegar — congiuntivo dopo cuando (futuro)",
    "hacer — subjonctif": "hacer — congiuntivo",
    "tomar — passé composé": "tomar — passato prossimo",
    "ir — passé simple": "ir — passato remoto",
    "jugar — imparfait": "jugar — imperfetto",
    "être en train de manger": "stare mangiando",
    "il faut (impersonnel)": "bisogna (impersonale)",
    "je dois": "devo",
    "personne": "nessuno",
    "rien": "niente",
    "ser — la gente = singulier": "ser — la gente = singolare",
    "querer — la gente = singulier": "querer — la gente = singolare",
    "ces — masculin pluriel": "questi — maschile plurale",
    "ces — féminin pluriel": "queste — femminile plurale",
    "ce — masculin": "questo — maschile",
    "cette — féminin": "questa — femminile",
    "el / la — día finit en -a mais…": "el / la — día finisce in -a ma…",
    "el / la — les mots en -ma": "el / la — le parole in -ma",
    "pronom obligatoire": "pronome obbligatorio",
    "ir a + infinitif — futur proche": "ir a + infinito — futuro prossimo",
    "il va y avoir": "ci sarà",
}
# Déjà neutres (espagnol) : gardés tels quels.
NEUTRAL = {"ser / estar", "por / para", "gustar", "a + el", "de + el", "muy / mucho", "un / una", "le + lo"}
TENSES = {"présent": "presente", "passé simple": "passato remoto", "futur": "futuro", "conditionnel": "condizionale"}
# Tags in Italian, except « conjugaison »: the app finds conjugation cards by it.
TAGS = {"grammaire": "grammatica", "Pronoms": "pronomi", "articles": "articoli", "gérondif": "gerundio",
        "négation": "negazione", "obligation": "obbligo", "passés": "passati", "subjonctif": "congiuntivo"}


def translate_question(q):
    def paren(m):
        inner = m.group(2)
        if inner in NEUTRAL:
            return m.group(0)
        if inner not in PAREN:
            raise SystemExit(f"Sans traduction : ({inner})")
        return m.group(1) + PAREN[inner] + m.group(3)
    # the (…) right inside the grey span, possibly with nested brackets
    q = re.sub(r"(<span style='opacity:\.6'>\()(.*)(\)</span>)", paren, q)
    q = re.sub(r"<br>(présent|passé simple|futur|conditionnel) ·", lambda m: "<br>" + TENSES[m.group(1)] + " ·", q)
    return q


def main():
    with open(os.path.join(HERE, "grammaire.json"), encoding="utf-8") as f:
        src = json.load(f)
    decks, i = [], 0
    for d in src["decks"]:
        cards = []
        for c in d["cards"]:
            i += 1
            t = {k: v for k, v in c.items() if k != "srs"}  # fresh progress
            t["id"] = str(ID_BASE + i * 10 + 1)
            t["question"] = translate_question(c["question"])
            t["tags"] = [TAGS.get(x, x) for x in c.get("tags", [])]
            cards.append(t)
        decks.append({"id": "it-" + d["id"], "name": DECKS[d["name"]], "cards": cards})
    out = {"version": 1, "source": "Grammatica spagnola (italiano)", "decks": decks, "styles": src.get("styles", [])}
    def translated_parts(q):  # only what was translated: the grey (…) and the tense
        return " ".join(re.findall(r"<span style='opacity:\.6'>\((.*)\)</span>", q) + re.findall(r"<br>([^<·]*) ·", q))
    left = [c["question"] for d in decks for c in d["cards"]
            if re.search(r"[êçëœ]|é(?!l\b)|présent|passé|futur\b|conditionnel", translated_parts(c["question"]))]
    if left:
        raise SystemExit("Français restant :\n" + "\n".join(left[:10]))
    with open(os.path.join(HERE, "grammatica.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"{i} cartes → grammatica.json ({', '.join(d['name'].split('::')[-1] + ' ' + str(len(d['cards'])) for d in decks)})")


if __name__ == "__main__":
    main()
