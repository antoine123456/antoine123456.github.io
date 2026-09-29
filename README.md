# Anki Trainer

Fill-in-the-blank study app for Anki decks: pre-process a `.apkg` export into JSON, import it in the browser, and type out each word of the answer instead of just flipping the card. Progress uses a simple SM-2-style spaced-repetition schedule, stored in the browser's `localStorage` — no account, no backend.

## Folder structure

```
espanol-trainer/
├── index.html    ← standalone study app (open in any browser, or via GitHub Pages)
├── extract.py    ← CLI: converts a .apkg into JSON for the app (pip install anki recommended)
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
