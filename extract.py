#!/usr/bin/env python3
"""
extract_apkg.py — Convertit un deck Anki .apkg en JSON pour Anki Trainer.
Aucune dépendance externe (stdlib uniquement : zipfile, sqlite3, json).

Usage :
    python extract_apkg.py mon_deck.apkg --out mon_deck.json

Gère :
  - sous-decks (noms avec "::")
  - modèles Basic, Cloze, et modèles personnalisés
  - templates HTML avec substitution {{Champ}}
  - cartes vides / templates manquants (ignorés proprement)
"""

import argparse
import json
import os
import re
import sqlite3
import sys
import tempfile
import zipfile
from html.parser import HTMLParser


# ── Utilitaires HTML ─────────────────────────────────────────────────────────

class _Stripper(HTMLParser):
    BLOCK = {'br', 'p', 'div', 'li', 'tr', 'hr',
             'h1', 'h2', 'h3', 'h4', 'h5', 'h6'}

    def __init__(self):
        super().__init__()
        self._parts = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() in self.BLOCK:
            self._parts.append(' ')

    def handle_endtag(self, tag):
        if tag.lower() in self.BLOCK:
            self._parts.append(' ')

    def handle_data(self, d):
        self._parts.append(d)

    def result(self):
        return ' '.join(''.join(self._parts).split())


def strip_html(text: str) -> str:
    s = _Stripper()
    try:
        s.feed(str(text))
    except Exception:
        pass
    return s.result()


def render_template(tmpl: str, field_map: dict, front_html: str = '') -> str:
    """Substitue {{Champ}} dans un template Anki."""
    out = str(tmpl)
    if front_html:
        out = re.sub(r'\{\{FrontSide\}\}', front_html,
                     out, flags=re.IGNORECASE)
    out = re.sub(r'\{\{hint:[^}]+\}\}', '', out)               # hints → vide
    out = re.sub(r'\{\{type:[^}]+\}\}', '', out)               # type-in → vide
    out = re.sub(r'\{\{#[^}]+\}\}[\s\S]*?\{\{/[^}]+\}\}',
                 '', out)  # conditionals
    for name, val in field_map.items():
        out = re.sub(r'\{\{' + re.escape(name) + r'\}\}',
                     val, out, flags=re.IGNORECASE)
    out = re.sub(r'\{\{[^}]+\}\}', '', out)
    out = re.sub(r'<script[\s\S]*?</script>', '', out, flags=re.IGNORECASE)
    return out.strip()


def strip_cloze(text: str) -> str:
    """{{c1::mot::hint}} → mot"""
    return re.sub(r'\{\{c\d+::([^:}]+)(?:::[^}]*)?\}\}', r'\1', text)


def clean_for_words(html_text: str) -> str:
    """Retire les références son/image, renvoie le texte brut."""
    t = re.sub(r'\[sound:[^\]]+\]', ' ', html_text)
    t = re.sub(r'<img[^>]*>', ' ', t, flags=re.IGNORECASE)
    return strip_html(t)


def build_field_map(model: dict, fields: list) -> dict:
    flds = sorted(model.get('flds', []), key=lambda f: f.get('ord', 0))
    fm = {}
    is_cloze = model.get('type') == 1
    for i, f in enumerate(flds):
        val = fields[i] if i < len(fields) else ''
        if is_cloze:
            val = strip_cloze(val)
        fm[f['name']] = val
    return fm


# ── Extraction SQLite ─────────────────────────────────────────────────────────

def process_db(db_path: str) -> list[dict]:
    con = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    # Collection : modèles et decks
    cur.execute("SELECT models, decks FROM col LIMIT 1")
    row = cur.fetchone()
    models = json.loads(row['models'])
    decks_raw = json.loads(row['decks'])

    # Notes
    cur.execute("SELECT id, mid, flds, tags FROM notes")
    note_map: dict = {}
    for r in cur.fetchall():
        note_map[r['id']] = {
            'mid': str(r['mid']),
            'fields': r['flds'].split('\x1f'),
            'tags': r['tags'].strip().split() if r['tags'].strip() else [],
        }

    # Cartes
    cur.execute("SELECT id, nid, did, ord FROM cards")
    cards_raw = cur.fetchall()
    con.close()

    # Index des decks (filtrer "Default" vide)
    deck_map: dict = {}
    for did, d in decks_raw.items():
        name = d.get('name', '').strip()
        if not name or name == 'Default':
            continue
        deck_map[str(did)] = {'id': str(did), 'name': name, 'cards': []}

    skipped = 0
    for c in cards_raw:
        did = str(c['did'])
        if did not in deck_map:
            continue
        note = note_map.get(c['nid'])
        if not note:
            skipped += 1
            continue
        model = models.get(note['mid'])
        if not model:
            skipped += 1
            continue

        tmpls = model.get('tmpls', [])
        tmpl_idx = c['ord'] if c['ord'] < len(tmpls) else 0
        tmpl = tmpls[tmpl_idx] if tmpls else None
        if not tmpl:
            skipped += 1
            continue

        fm = build_field_map(model, note['fields'])
        q_html = render_template(tmpl.get('qfmt', ''), fm)
        a_html = render_template(tmpl.get('afmt', ''), fm, front_html=q_html)

        # Texte de la réponse (sans répéter la question)
        q_text = clean_for_words(q_html)
        a_text = clean_for_words(a_html)
        if a_text.lower().startswith(q_text.lower()):
            a_text = a_text[len(q_text):].strip()

        words = [w for w in a_text.split() if w]
        if not words:
            skipped += 1
            continue

        deck_map[did]['cards'].append({
            'id': str(c['id']),
            'question': q_html,
            'words': words,
            'tags': note['tags'],
        })

    if skipped:
        print(f"  ⚠  {skipped} carte(s) ignorée(s) (template vide ou réponse non parseable)",
              file=sys.stderr)

    result = sorted(
        [d for d in deck_map.values() if d['cards']],
        key=lambda d: d['name']
    )
    return result


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="Convertit un .apkg Anki en JSON pour Anki Trainer"
    )
    ap.add_argument("apkg", help="Fichier .apkg ou .colpkg")
    ap.add_argument("--out", required=True, help="Fichier .json de sortie")
    args = ap.parse_args()

    if not os.path.exists(args.apkg):
        sys.exit(f"Fichier introuvable : {args.apkg}")

    print(f"Ouverture de {os.path.basename(args.apkg)}…")
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(args.apkg, 'r') as z:
            names = z.namelist()
            # Préférer anki21 (format récent), fallback anki2
            db_name = next(
                (n for n in ('collection.anki21', 'collection.anki2') if n in names),
                None
            )
            if not db_name:
                sys.exit("Aucune base SQLite trouvée dans l'archive")
            z.extract(db_name, tmp)
            db_path = os.path.join(tmp, db_name)

        print("Extraction des cartes…")
        decks = process_db(db_path)

    total = sum(len(d['cards']) for d in decks)
    print(f"\n✓ {total} cartes dans {len(decks)} deck(s) :")
    for d in decks:
        indent = "  " * d['name'].count('::')
        print(
            f"   {indent}· {d['name'].split('::')[-1]}  ({len(d['cards'])} cartes)")

    output = {
        'version': 1,
        'source': os.path.basename(args.apkg),
        'decks': decks,
    }
    with open(args.out, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n→ JSON sauvegardé : {args.out}")
    print("  Importez ce fichier dans index.html  (Importer un deck)")


if __name__ == '__main__':
    main()
