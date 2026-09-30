# Anki Trainer

Fill-in-the-blank study app for Anki decks: pre-process a `.apkg` export into JSON, import it in the browser, and type out each word of the answer instead of just flipping the card. Scheduling models Anki's actual default algorithm (new → learning steps → review, lapses → relearning). Progress lives in the browser's `localStorage` — no account, no sync, nothing leaves the browser right now (see "Sync (planned)" below for why the Firestore backend already exists but isn't wired up to anything yet).

## Folder structure

```
espanol-trainer/
├── index.html         ← standalone study app (open in any browser, or via GitHub Pages)
├── extract.py         ← CLI: converts a .apkg into JSON for the app (pip install anki recommended)
├── reimport_stats.py  ← CLI: writes progress made here back into a .apkg for re-import into real Anki
├── default.json       ← bundled deck auto-loaded on first run if no source has been imported yet
├── default_media/     ← its audio/image files
├── add_card.py        ← console tool: adds one word pair to the shared "perso" deck (see below)
└── README.md
```

---

## Step 1 — Export your deck from Anki

In Anki: **File → Export...** + check "with stats"→ format **"Anki Deck Package (.apkg)"** → pick the deck(s) you want.

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

## Sync (planned)

There's no sync right now — `localStorage` is the only place progress lives, same as the app worked before any of this. Two identity models were tried and both set aside for now:

- **Google sign-in** — works, but was parked to avoid dealing with Firebase Auth setup (Authorized domains, OAuth consent screen) right away. Kept intact on a separate branch, **`auth`**, exactly as it was built — this is the intended eventual path.
- **A plain name-picking dropdown** (no real auth, just a picked name mapped to a Firestore id) — built as a quicker stand-in, then abandoned: without real authentication behind it, every new person needed a manual Firestore-rules edit to actually get working sync, which didn't seem worth it over just waiting for Google sign-in.

What's left in place on purpose: a Firestore database already exists for this project (`type-in-anki`), and `index.html` still initializes `firebase.firestore()` and carries the full push/merge sync engine (`scheduleSync`, `fetchAndMergeFromFirestore`, chunking, etc.) — all of it dormant, since nothing ever sets `fbUser` anymore. The `users/{uid}` schema below is written to assume a real Firebase Auth `uid`, so switching back to the `auth` branch (or merging its sign-in code back into this one) drops straight into a working sync with no schema migration needed. Nothing has ever been written to it under this scheme, so there's nothing to migrate away from either.

### Data layout (dormant, ready for when sign-in returns)

```
users/{uid}                              { sources: [...meta], theme, updatedAt }
users/{uid}/sources/{sourceId}           { srs, newCount, flagged, updatedAt }
users/{uid}/sources/{sourceId}/cardChunks/{n}   { data, index, total }   (user-imported decks only)
```

The bundled `default.json` deck's card *content* is never duplicated into Firestore (it's already static), only its progress (`srs`/`newCount`/`flagged`) — under the fixed source id `"default"` so it matches across devices. User-imported decks' card content is chunked (each doc kept well under Firestore's 1 MiB limit) since it isn't available anywhere else in the cloud.

The first time someone signs in: if the cloud has nothing yet, their local data is uploaded as-is. If both sides have data, they're merged — per-card SRS keeps whichever side was reviewed more recently (`lastReview` timestamp), flagged cards are unioned — and a timestamped backup of pre-merge local data is saved under a separate `localStorage` key first. On sign-out, the local copy of *that account's* data is cleared (so a shared computer doesn't leak it to the next person); nothing in the cloud is touched. (See the `auth` branch for the actual sign-in/sign-out UI this pairs with — the setup steps, Firestore rules, etc. live in its own README.)

---

## Console tool (`cuatroloop` / `tresloop`)

A pair of shell functions (defined in `~/.bashrc`) that read words one per
line from stdin, translate each with [`translate-shell`](https://github.com/soimort/translate-shell)
(the `trans` CLI), and add the pair as a flashcard — without touching Anki or
re-running `extract.py`. `cuatroloop` translates ES→FR, `tresloop` FR→ES.

Each word goes into the `perso` sub-deck inside `default.json` — the same
deck everyone who loads the site gets, since there's no per-person account
system right now (see "Sync (planned)" above). Once real sign-in is back,
this can move to a per-user deck in Firestore instead; for now it's one
shared deck, same as this app worked originally.

### Install

```bash
brew install translate-shell   # provides `trans`
```

### Usage

```bash
echo "casa" | cuatroloop     # adds casa <-> maison to the shared perso deck
```

or interactively, one word per line, `Ctrl-D` to stop:

```bash
cuatroloop
```

Type **`commit`** as a line (instead of a word to translate) to commit and
push `default.json` right away, with a message noting which loop added the
words.

Words that already exist in that deck (matched case-insensitively against
either side of the pair) are silently skipped instead of duplicated.

---

## Future work

- **Bottom-bar study controls, closer to real Anki.** Right now the rating buttons sit wherever they sit; in real Anki they live in a fixed bottom bar, showing a single control (with the new/due counts) that transitions into the 4 rating buttons once the answer is revealed. Worth doing if the current layout ever actually feels uncomfortable in practice, not just because it's different.
- **Lighter reveal for typed-correct words.** When a card is completed by typing alone (no reveal used), consider only highlighting the rectangle around each solved word instead of the current display — mirrors how little real Anki shows you when you already knew the answer.

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
