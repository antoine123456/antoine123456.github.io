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
    "devoir → je devrais…": "dovere → dovrei…",
    "referirse — tú : se référer, parler de": "referirse — tú: riferirsi, parlare di",
    "levantarse — se lever": "levantarse — alzarsi",
    "quejarse — se plaindre": "quejarse — lamentarsi",
    "llamarse — tú": "llamarse — tú",
    "acordarse — yo : se souvenir": "acordarse — yo: ricordarsi",
    "soler — j'ai l'habitude de": "soler — ho l'abitudine di",
    "soler — nosotros": "soler — nosotros",
    "soler — tú": "soler — tú",
    "soler — il fait d'habitude": "soler — di solito fa",
    "haber — vosotros : passé composé": "haber — vosotros: passato prossimo",
    "haber — yo": "haber — yo",
    "haber — ellos": "haber — ellos",
    "il y a": "c'è / ci sono",
    "toi, qu'en penses-tu ? — le sujet d'abord, puis qué": "tu, cosa ne pensi? — prima il soggetto, poi qué",
    "qu'est-ce que tu me racontes ? — qué + pronom + verbe": "cosa mi racconti? — qué + pronome + verbo",
    "nous pouvons toujours — l'adverbe avant le verbe": "possiamo sempre — l'avverbio prima del verbo",
    "quelque chose de grand — l'adjectif après, sans « de »": "qualcosa di grande — l'aggettivo dopo, senza « de »",
    "une très belle ville — l'adjectif après le nom": "una città molto bella — l'aggettivo dopo il nome",
    "regarder (la télé) — yo : ver": "guardare (la tv) — yo: ver",
    "regarde ! — tú : mirar": "guarda! — tú: mirar",
    "voir — yo": "vedere — yo",
    "regarder (avec attention) — yo": "guardare (con attenzione) — yo",
    "avoir — auxiliaire": "avere — ausiliare",
}
# Cards added to grammaire.json after the first build (deber, #155): their own
# ids, after all the others, so that no card already here changes id.
LATE = ["1791382981350", "1791382981351", "1791382981352", "1791382981353", "1791382981354", "1791382981355",
        # « Idées vocabulaire » → Grammaire (#171): pronominaux, soler, haber, ordre des mots, ver / mirar
        "1791382981361", "1791382981362", "1791382981363", "1791382981364", "1791382981365", "1791382981366", "1791382981367", "1791382981368", "1791382981369", "1791382981370", "1791382981371", "1791382981372", "1791382981373", "1791382981374", "1791382981375", "1791382981376", "1791382981377", "1791382981378", "1791382981379", "1791382981380", "1791382981381", "1791382981382", "1791382981383", "1791382981384", "1791382981385", "1791382981386", "1791382981387", "1791382981388"]
# Déjà neutres (espagnol) : gardés tels quels.
NEUTRAL = {"ser / estar", "por / para", "gustar", "a + el", "de + el", "muy / mucho", "un / una", "le + lo"}
TENSES = {"présent": "presente", "passé simple": "passato remoto", "futur": "futuro", "conditionnel": "condizionale"}
# Tags in Italian, except « conjugaison »: the app finds conjugation cards by it.
TAGS = {"grammaire": "grammatica", "Pronoms": "pronomi", "articles": "articoli", "gérondif": "gerundio",
        "négation": "negazione", "obligation": "obbligo", "passés": "passati", "subjonctif": "congiuntivo",
        "pronominaux": "pronominali", "ordre": "ordine"}


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
            t = {k: v for k, v in c.items() if k != "srs"}  # fresh progress
            if c["id"] in LATE:
                t["id"] = str(ID_BASE + (5000 + LATE.index(c["id"])) * 10 + 1)
            else:
                i += 1
                t["id"] = str(ID_BASE + i * 10 + 1)
            t["question"] = translate_question(c["question"])
            t["tags"] = [TAGS.get(x, x) for x in c.get("tags", [])]
            cards.append(t)
        decks.append({"id": "it-" + d["id"], "name": DECKS[d["name"]], "cards": cards})
    out = {"version": 1, "source": "Grammatica spagnola (italiano)", "decks": decks, "styles": src.get("styles", [])}
    def translated_parts(q):  # only what was translated: the grey (…) and the tense
        return " ".join(re.findall(r"<span style='opacity:\.6'>\((.*)\)</span>", q) + re.findall(r"<br>([^<·]*) ·", q))
    left = [c["question"] for d in decks for c in d["cards"]
            if re.search(r"[êçëœ]|(?<!qu)é(?!l\b)|présent|passé|futur\b|conditionnel", translated_parts(c["question"]))]
    if left:
        raise SystemExit("Français restant :\n" + "\n".join(left[:10]))
    with open(os.path.join(HERE, "grammatica.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"{i} cartes → grammatica.json ({', '.join(d['name'].split('::')[-1] + ' ' + str(len(d['cards'])) for d in decks)})")


if __name__ == "__main__":
    main()
