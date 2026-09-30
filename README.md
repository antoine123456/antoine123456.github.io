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
