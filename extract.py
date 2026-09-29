#!/usr/bin/env python3
"""
extract_apkg.py — Convertit un deck Anki .apkg en JSON pour Anki Trainer.

Deux modes d'extraction :
  1. Via le paquet 'anki' (pip install anki) — RECOMMANDÉ. Importe le .apkg
     dans une collection éphémère et laisse Anki lui-même faire le rendu des
     templates, ce qui gère correctement tous les modèles, y compris le
     format récent (Anki ≥ 2.1.50, base compressée zstd + config protobuf).
  2. Repli stdlib-only (zipfile, sqlite3, json) si le paquet 'anki' n'est
     pas installé — ne fonctionne que sur les .apkg "legacy" dont la base
     n'est pas compressée et dont col.models/col.decks sont encore de
     simples blobs JSON (exports d'anciennes versions d'Anki).

Usage :
    python extract_apkg.py mon_deck.apkg --out mon_deck.json

Gère :
  - sous-decks (noms avec "::")
  - modèles Basic, Cloze, et modèles personnalisés
  - cartes vides / templates manquants (ignorés proprement)
"""

import argparse
import json
import os
import re
import shutil
import sqlite3
import subprocess
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


def strip_sound_tags(html_text: str) -> str:
    """Retire les balises son (legacy [sound:...] et le nouveau
    [anki:play:...]) d'un HTML destiné à être AFFICHÉ tel quel — on gère
    la lecture audio nous-mêmes via audioQuestion/audioAnswer, ces balises
    ne doivent donc jamais apparaître comme texte à l'écran."""
    t = re.sub(r'\[sound:[^\]]+\]', '', html_text)
    t = re.sub(r'\[anki:play:[^\]]+\]', '', t)
    return t


def clean_for_words(html_text: str) -> str:
    """Retire les références son/image, renvoie le texte brut (pour le
    découpage en mots, pas pour l'affichage)."""
    t = strip_sound_tags(html_text)
    t = re.sub(r'<img[^>]*>', ' ', t, flags=re.IGNORECASE)
    return strip_html(t)


def card_words_and_question(question_html: str, answer_html: str):
    """À partir du HTML rendu (question() / answer()), isole le texte de la
    réponse (sans répéter la question) et le découpe en mots."""
    marker = '<hr id=answer>'
    idx = answer_html.lower().find(marker)
    answer_new_html = answer_html[idx + len(marker):] if idx != -1 else answer_html

    q_text = clean_for_words(question_html)
    a_text = clean_for_words(answer_new_html)
    if idx == -1 and a_text.lower().startswith(q_text.lower()):
        a_text = a_text[len(q_text):].strip()

    words = [w for w in a_text.split() if w and any(ch.isalnum() for ch in w)]
    return words


# ── Médias (audio/images) ───────────────────────────────────────────────────────

IMG_SRC_RE = re.compile(r'(<img[^>]*\bsrc=["\'])([^"\']+)(["\'])', re.IGNORECASE)
SOUND_TAG_RE = re.compile(r'\[sound:([^\]]+)\]')


class MediaCollector:
    """Copie à la demande les fichiers médias référencés par les cartes vers
    `out_dir`, en mémorisant ce qui a déjà été copié (ou constaté manquant)
    pour ne jamais copier deux fois le même fichier."""

    def __init__(self, out_dir: str, subdir_name: str):
        self.out_dir = out_dir
        self.subdir_name = subdir_name
        self._cache: dict = {}   # filename -> relative path, or None si absent
        self.missing = 0

    def _copy_from_disk(self, filename: str, media_dir: str):
        return os.path.join(media_dir, filename) if media_dir else None

    def add(self, filename: str, *, media_dir: str = None, data: bytes = None) -> str | None:
        if not filename:
            return None
        if filename in self._cache:
            return self._cache[filename]

        try:
            if data is not None:
                payload = data
            elif media_dir:
                src = os.path.join(media_dir, filename)
                if not os.path.isfile(src):
                    raise FileNotFoundError(src)
                with open(src, 'rb') as f:
                    payload = f.read()
            else:
                raise FileNotFoundError(filename)
        except (FileNotFoundError, OSError):
            self._cache[filename] = None
            self.missing += 1
            return None

        os.makedirs(os.path.join(self.out_dir, self.subdir_name), exist_ok=True)
        dst = os.path.join(self.out_dir, self.subdir_name, filename)
        with open(dst, 'wb') as f:
            f.write(payload)
        rel = f"{self.subdir_name}/{filename}"
        self._cache[filename] = rel
        return rel

    @property
    def copied_count(self) -> int:
        return sum(1 for v in self._cache.values() if v)


def rewrite_img_srcs(html_text: str, collector: MediaCollector, resolve) -> str:
    """resolve(filename) -> kwargs dict for collector.add() (media_dir=... or data=...)."""
    def _sub(m):
        filename = m.group(2)
        rel = collector.add(filename, **resolve(filename))
        return m.group(1) + (rel or filename) + m.group(3)
    return IMG_SRC_RE.sub(_sub, html_text)


# ── Mode 1 : via le paquet 'anki' (recommandé) ─────────────────────────────────

def process_apkg_via_anki(apkg_path: str, media: MediaCollector) -> list[dict]:
    from anki.collection import Collection
    from anki import import_export_pb2 as pb

    with tempfile.TemporaryDirectory() as tmp:
        col_path = os.path.join(tmp, 'collection.anki2')
        col = Collection(col_path)
        skipped = 0
        try:
            req = pb.ImportAnkiPackageRequest(
                package_path=os.path.abspath(apkg_path),
                options=pb.ImportAnkiPackageOptions(),
            )
            col.import_anki_package(req)
            media_dir = col.media.dir()

            deck_map: dict = {}
            for d in col.decks.all_names_and_ids():
                name = d.name.strip()
                if not name or name == 'Default':
                    continue
                deck_map[d.id] = {'id': str(d.id), 'name': name, 'cards': []}

            for cid in col.find_cards(''):
                card = col.get_card(cid)
                if card.did not in deck_map:
                    skipped += 1
                    continue
                q_html = card.question()
                a_html = card.answer()
                words = card_words_and_question(q_html, a_html)
                if not words:
                    skipped += 1
                    continue

                audio_q = [rel for tag in card.question_av_tags()
                           if (fn := getattr(tag, 'filename', None))
                           and (rel := media.add(fn, media_dir=media_dir))]
                audio_a = [rel for tag in card.answer_av_tags()
                           if (fn := getattr(tag, 'filename', None))
                           and (rel := media.add(fn, media_dir=media_dir))]
                q_html = rewrite_img_srcs(q_html, media, lambda fn: {'media_dir': media_dir})
                q_html = strip_sound_tags(q_html)

                note = card.note()
                card_obj = {
                    'id': str(cid),
                    'question': q_html,
                    'words': words,
                    'tags': list(note.tags),
                }
                if audio_q:
                    card_obj['audioQuestion'] = audio_q
                if audio_a:
                    card_obj['audioAnswer'] = audio_a
                deck_map[card.did]['cards'].append(card_obj)
        finally:
            col.close()

    if skipped:
        print(f"  ⚠  {skipped} carte(s) ignorée(s) (deck exclu ou réponse non parseable)",
              file=sys.stderr)

    return sorted([d for d in deck_map.values() if d['cards']], key=lambda d: d['name'])


# ── Mode 2 : repli stdlib-only (legacy uniquement) ─────────────────────────────

def decompress_zstd(src_path: str, dst_path: str) -> bool:
    """Décompresse un fichier zstd vers dst_path. Renvoie False si aucun
    décompresseur (module 'zstandard' ou CLI zstd/unzstd) n'est disponible."""
    try:
        import zstandard
        dctx = zstandard.ZstdDecompressor()
        with open(src_path, 'rb') as f_in, open(dst_path, 'wb') as f_out:
            dctx.copy_stream(f_in, f_out)
        return True
    except ImportError:
        pass

    for exe, args in (
        ('zstd', ['-d', '-f', '-q', src_path, '-o', dst_path]),
        ('unzstd', ['-f', '-q', src_path, '-o', dst_path]),
    ):
        try:
            subprocess.run([exe] + args, check=True,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except (FileNotFoundError, subprocess.CalledProcessError):
            continue
    return False


def render_template(tmpl: str, field_map: dict, front_html: str = '') -> str:
    """Substitue {{Champ}} dans un template Anki (legacy, modèles JSON)."""
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


def process_db_legacy(db_path: str, media: MediaCollector, media_bytes_fn) -> list[dict]:
    con = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    cur.execute("SELECT models, decks FROM col LIMIT 1")
    row = cur.fetchone()
    models = json.loads(row['models'] or '{}')
    decks_raw = json.loads(row['decks'] or '{}')
    if not models or not decks_raw:
        con.close()
        sys.exit(
            "Cette base n'a pas de modèles/decks au format JSON legacy "
            "(export Anki récent). Installez le paquet 'anki' pour la lire "
            "correctement : pip install anki"
        )

    cur.execute("SELECT id, mid, flds, tags FROM notes")
    note_map: dict = {}
    for r in cur.fetchall():
        note_map[r['id']] = {
            'mid': str(r['mid']),
            'fields': r['flds'].split('\x1f'),
            'tags': r['tags'].strip().split() if r['tags'].strip() else [],
        }

    cur.execute("SELECT id, nid, did, ord FROM cards")
    cards_raw = cur.fetchall()
    con.close()

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

        words = card_words_and_question(q_html, a_html)
        if not words:
            skipped += 1
            continue

        resolve = lambda fn: {'data': media_bytes_fn(fn)}  # noqa: E731
        audio_q = [rel for fn in SOUND_TAG_RE.findall(q_html)
                   if (rel := media.add(fn, data=media_bytes_fn(fn)))]
        audio_a = [rel for fn in SOUND_TAG_RE.findall(a_html)
                   if (rel := media.add(fn, data=media_bytes_fn(fn)))]
        q_html = rewrite_img_srcs(q_html, media, resolve)
        q_html = strip_sound_tags(q_html)

        card_obj = {
            'id': str(c['id']),
            'question': q_html,
            'words': words,
            'tags': note['tags'],
        }
        if audio_q:
            card_obj['audioQuestion'] = audio_q
        if audio_a:
            card_obj['audioAnswer'] = audio_a
        deck_map[did]['cards'].append(card_obj)

    if skipped:
        print(f"  ⚠  {skipped} carte(s) ignorée(s) (template vide ou réponse non parseable)",
              file=sys.stderr)

    return sorted([d for d in deck_map.values() if d['cards']], key=lambda d: d['name'])


def build_legacy_media_lookup(z: zipfile.ZipFile) -> dict:
    """{filename: zip member name} à partir du manifeste 'media' (JSON legacy
    uniquement — les manifestes zstd/protobuf des exports récents ne sont pas
    supportés ici ; utilisez le paquet 'anki' pour ceux-là)."""
    if 'media' not in z.namelist():
        return {}
    try:
        manifest = json.loads(z.read('media') or b'{}')
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return {filename: num for num, filename in manifest.items()}


def process_apkg_legacy(apkg_path: str, media: MediaCollector) -> list[dict]:
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(apkg_path, 'r') as z:
            names = z.namelist()
            uncompressed_name = next(
                (n for n in ('collection.anki21', 'collection.anki2') if n in names),
                None
            )
            db_path = None
            if 'collection.anki21b' in names:
                z.extract('collection.anki21b', tmp)
                compressed_path = os.path.join(tmp, 'collection.anki21b')
                candidate_path = os.path.join(tmp, 'collection.anki21b.db')
                if decompress_zstd(compressed_path, candidate_path):
                    db_path = candidate_path
                elif uncompressed_name:
                    print("  ⚠ zstd indisponible (ni module 'zstandard' ni CLI "
                          "zstd/unzstd) : repli sur la base legacy, potentiellement "
                          "incomplète", file=sys.stderr)
                else:
                    sys.exit(
                        "La base est compressée (zstd) et ni le module Python "
                        "'zstandard' ni l'outil 'zstd'/'unzstd' ne sont disponibles.\n"
                        "Installez l'un des deux, ex. : pip install zstandard  "
                        "ou  brew install zstd — ou, mieux : pip install anki"
                    )
            if db_path is None:
                if not uncompressed_name:
                    sys.exit("Aucune base SQLite trouvée dans l'archive")
                z.extract(uncompressed_name, tmp)
                db_path = os.path.join(tmp, uncompressed_name)

            lookup = build_legacy_media_lookup(z)

            def media_bytes_fn(filename, _z=z, _lookup=lookup):
                num = _lookup.get(filename)
                if num is None or num not in _z.namelist():
                    return None
                try:
                    return _z.read(num)
                except KeyError:
                    return None

            return process_db_legacy(db_path, media, media_bytes_fn)


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

    out_dir = os.path.dirname(os.path.abspath(args.out)) or '.'
    out_stem = os.path.splitext(os.path.basename(args.out))[0]
    media = MediaCollector(out_dir, out_stem + '_media')

    print(f"Ouverture de {os.path.basename(args.apkg)}…")
    try:
        import anki  # noqa: F401
        print("Extraction des cartes (via le paquet 'anki')…")
        decks = process_apkg_via_anki(args.apkg, media)
    except ImportError:
        print("  ℹ paquet 'anki' non installé — repli sur le lecteur stdlib "
              "(fonctionne uniquement avec les exports Anki plus anciens ; "
              "pip install anki pour un support complet)", file=sys.stderr)
        print("Extraction des cartes…")
        decks = process_apkg_legacy(args.apkg, media)

    total = sum(len(d['cards']) for d in decks)
    print(f"\n✓ {total} cartes dans {len(decks)} deck(s) :")
    for d in decks:
        indent = "  " * d['name'].count('::')
        print(
            f"   {indent}· {d['name'].split('::')[-1]}  ({len(d['cards'])} cartes)")

    if media.copied_count:
        print(f"\n🔊 {media.copied_count} fichier(s) média copié(s) dans "
              f"{out_stem}_media/ — gardez ce dossier à côté du .json et de "
              f"index.html.")
    elif media.missing:
        print(f"\n⚠  {media.missing} référence(s) média trouvée(s) mais aucun "
              f"fichier correspondant dans l'archive — réexportez depuis Anki "
              f"avec 'Inclure les médias' coché si vous voulez le son/les images.",
              file=sys.stderr)

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
