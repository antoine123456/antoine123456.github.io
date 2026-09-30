# Anki Trainer

Fill-in-the-blank study app for Anki decks: pre-process a `.apkg` export into JSON, import it in the browser, and type out each word of the answer instead of just flipping the card. Scheduling models Anki's actual default algorithm (new → learning steps → review, lapses → relearning). Progress lives in the browser's `localStorage` by default — no account needed — with an optional Google sign-in to sync it across devices via Firebase (see "Sync (optional)" below).

## Folder structure

```
espanol-trainer/
├── index.html         ← standalone study app (open in any browser, or via GitHub Pages)
├── extract.py         ← CLI: converts a .apkg into JSON for the app (pip install anki recommended)
├── reimport_stats.py  ← CLI: writes progress made here back into a .apkg for re-import into real Anki
├── default.json       ← bundled deck auto-loaded on first run if no source has been imported yet
├── default_media/     ← its audio/image files
├── add_card.py        ← console tool: adds one word pair to *your own* Perso deck (see below)
├── cli_firestore.py   ← shared Firestore logic used by add_card.py / migrate_perso.py
├── migrate_perso.py   ← one-off: re-import old shared "perso" words into your personal deck
└── README.md
```

---

## Step 1 — Export your deck from Anki

In Anki: **File → Export...** → format **"Anki Deck Package (.apkg)"** → pick the deck(s) you want.

## Step 2 — Convert it to JSON

```bash
pip install anki
python3 extract.py "My Deck.apkg" --out my_deck.json
```

`extract.py` imports the `.apkg` into a throwaway collection and lets Anki's own code render every card, so it handles anything Anki itself handles: sub-decks (`Parent::Child`, shown as a collapsible tree in the app), Basic/Cloze/custom note types, HTML templates, sound/image references, and both the older plain-SQLite `.apkg` format and the newer zstd-compressed one (Anki ≥ 2.1.50).

`pip install anki` is recommended but not required — without it, the script falls back to a stdlib-only reader (`zipfile`/`sqlite3`/`json`) that only understands the **older** `.apkg` format; it will tell you to install `anki` if it hits a newer, incompatible one.

For each card it renders the answer side, strips HTML/sound/image tags, and splits what's left into the list of words you'll type — the question side is kept as-is (with its HTML) and shown above the blanks.

## Step 3 — Import into the app

Open `index.html`, click **＋ Importer un fichier .json**, and pick the file `extract.py` produced. Each source you import stays independent (its own progress, own decks), so you can import several exports side by side.

---

## How studying works

- Pick a deck (or a parent deck, which studies all its sub-decks together) from the home screen; badges show how many cards are **new**, **due**, and already **learned**.
- The question is shown as a card; type each word of the answer into its blank.
- Accents are optional — `ame` is accepted for `âme`.
- After 3 wrong attempts on a word, a hint appears; **💡 Voir les réponses** reveals everything, **Passer →** skips.
- Once every blank on a card is correct, the app rates it automatically from how many mistakes you made (0 → Parfait, 1 → Correct, 2 → Difficile, 3+ → À revoir) and schedules its next review with a lightweight SM-2 algorithm. New cards are capped at 20 per session; cards marked "À revoir" come back later in the same session.

---

## Publish to GitHub Pages

```bash
git add index.html extract.py README.md
git commit -m "feat: Anki Trainer"
git push
```

Then, in the repo's **Settings → Pages**, set the source to this branch, `/ (root)`. `extract.py` never needs to run in the browser — only `index.html` and the JSON files you import (kept in your own browser's `localStorage`) are needed there.

---

## Sync (optional)

Signing in with Google mirrors your progress to Firestore in the background, so it follows you between devices/browsers. Studying still works offline and without ever signing in — `localStorage` remains the source of truth the app actually reads from; sync just keeps a cloud copy in step with it.

`index.html` already has a working `FIREBASE_CONFIG` pointing at this project's own Firebase project, loaded via the **compat** SDK (`<script>` tags from `gstatic.com`, not the npm/modular package — there's no bundler here, it's a plain static file). If you fork this and want your own:

1. Create a project at [console.firebase.google.com](https://console.firebase.google.com), then **Build → Authentication → Sign-in method** → enable **Google**.
2. **Authentication → Settings → Authorized domains** → add your GitHub Pages domain (e.g. `yourname.github.io`) — sign-in fails silently without this.
3. **Build → Firestore Database** → create a database (production mode).
4. **Firestore → Rules**, publish:
   ```
   rules_version = '2';
   service cloud.firestore {
     match /databases/{database}/documents {
       match /users/{uid} {
         allow read, write: if request.auth != null && request.auth.uid == uid;
         match /{document=**} {
           allow read, write: if request.auth != null && request.auth.uid == uid;
         }
       }
     }
   }
   ```
   This is the only access rule that matters: a signed-in user can only ever read/write their own `users/{uid}` subtree.
5. **Project settings → General → Your apps** → register a web app → copy the `firebaseConfig` object into `FIREBASE_CONFIG` near the top of `index.html`'s `<script>`.

Without a valid config (or offline/blocked), the app falls back to `localStorage`-only exactly as before — no sign-in button appears, nothing else changes.

### Data layout

```
users/{uid}                              { sources: [...meta], theme, updatedAt }
users/{uid}/sources/{sourceId}           { srs, newCount, flagged, updatedAt }
users/{uid}/sources/{sourceId}/cardChunks/{n}   { data, index, total }   (user-imported decks only)
```

The bundled `default.json` deck's card *content* is never duplicated into Firestore (it's already static), only its progress (`srs`/`newCount`/`flagged`) — under the fixed source id `"default"` so it matches across devices. User-imported decks' card content is chunked (each doc kept well under Firestore's 1 MiB limit) since it isn't available anywhere else in the cloud.

On first sign-in: if the cloud has nothing yet, your local data is uploaded as-is. If both sides have data, they're merged — per-card SRS keeps whichever side was reviewed more recently (`lastReview` timestamp), flagged cards are unioned — and a timestamped backup of your pre-merge local data is saved under a separate `localStorage` key first. On sign-out, the local copy of *that account's* data is cleared (so a shared computer doesn't leak it to the next person); nothing in the cloud is touched.

---

## Console tool (`cuatroloop` / `tresloop`)

A pair of shell functions (defined in `~/.bashrc`) that read words one per
line from stdin, translate each with [`translate-shell`](https://github.com/soimort/translate-shell)
(the `trans` CLI), and add the pair as a flashcard — without touching Anki or
re-running `extract.py`. `cuatroloop` translates ES→FR, `tresloop` FR→ES.

Each word goes straight into **a personal "Perso" deck in Firestore**
(`add_card.py` → `cli_firestore.py`), not into `default.json`. `default.json`
is the bundled deck shipped to every visitor of the site, so it can't hold
one person's personal vocabulary — each user picked from the tool's menu
gets their own separate Perso deck instead, which only shows up when that
same account signs in with Google in the app.

There's no "log in" step here — a script can't do a Google sign-in popup —
so the tool identifies who a word is for with a plain menu (pick a name,
mapped to that person's already-known Firebase `uid`) instead.

### Install

```bash
brew install translate-shell   # provides `trans`
pip install firebase-admin     # lets add_card.py write to Firestore
```

### One-time setup

The first time `add_card.py` runs (i.e. the first word you add), it asks:

1. **Path to a Firebase service-account key (JSON).** Get one from the
   Firebase console: **⚙️ Project settings → Service accounts → Generate
   new private key**. This is a different, far more powerful credential than
   the public `apiKey` baked into `index.html` — it's the Admin SDK key, and
   it can read/write *any* user's data, not just your own. **Never commit it,
   never share it, keep the downloaded file outside this repo.**
2. **A name and Firebase `uid`** for the person these words are for. Find a
   `uid` in the Firebase console under **Authentication → Users** (after
   that person has signed into the app with Google at least once) — you
   only need to look it up this one time, it's then remembered by name.

All of this is cached in `~/.espanol_trainer_cli.json` (never committed to
git — it lives outside the repo, in your home folder).

With a single user configured, every future word just goes to them
automatically — no prompt. Type **`user`** as a line in `cuatroloop`/
`tresloop` (instead of a word to translate) any time to reopen the menu and
add another person or switch who new words go to.

### Usage

```bash
echo "casa" | cuatroloop     # adds casa <-> maison to the current user's Perso deck
```

or interactively, one word per line, `Ctrl-D` to stop:

```bash
cuatroloop
```

Words that already exist in that deck (matched case-insensitively against
either side of the pair) are silently skipped instead of duplicated.

### Migrating old shared words

Before this change, all `cuatroloop`/`tresloop` additions went into a
`perso` sub-deck shared by every visitor via `default.json`. That deck is
still there, untouched, for now. `migrate_perso.py` re-adds that same list
of word pairs into a personal deck through the setup above — run it once
(`python3 migrate_perso.py`) whenever you're ready, then the shared copy in
`default.json` can be removed.

---

## JSON format reference

```json
{
  "version": 1,
  "source": "My Deck.apkg",
  "decks": [
    {
      "id": "1234567890",
      "name": "Parent::Child",
      "cards": [
        { "id": "111", "question": "<b>question HTML</b>", "words": ["word1", "word2"], "tags": ["tag1"] }
      ]
    }
  ]
}
```
