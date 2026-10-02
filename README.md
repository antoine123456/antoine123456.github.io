# Anki Trainer

Fill-in-the-blank study app for Anki decks: pre-process a `.apkg` export into JSON, import it in the browser, and type out each word of the answer instead of just flipping the card. Scheduling models Anki's actual default algorithm (new → learning steps → review, lapses → relearning). Progress lives in the browser's `localStorage` — no account, no sync, nothing leaves the browser right now (see "Sync (planned)" below for why the Firestore backend already exists but isn't wired up to anything yet).

## Folder structure

```
espanol-trainer/
├── index.html         ← standalone study app (open in any browser, or via GitHub Pages)
├── extract.py         ← CLI: converts a .apkg into JSON for the app (pip install anki recommended)
├── sync_to_anki.py    ← CLI: one command pushes downloaded progress straight into your local Anki collection
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

**Or skip the export** and read your local Anki collection directly (needs `pip install anki`; quit Anki first, it locks the collection):

```bash
python3 extract.py --collection --deck Arbres --out arbres_extrait.json
```

`--collection` auto-detects your profile (`--profile` if you have several, or `--collection path/to/collection.anki2`). `--deck` keeps only that deck and its sub-decks; repeat it for several decks. It also works with a `.apkg`.

Images whose `src` is a web link (`<img src="https://…">`) are left as-is, not copied: handy to avoid storing pictures in Anki at all (the Arbres deck uses Wikimedia Commons links), but they won't show offline, in Anki or here.

`pip install anki` is recommended but not required — without it, the script falls back to a stdlib-only reader (`zipfile`/`sqlite3`/`json`) that only understands the **older** `.apkg` format; it will tell you to install `anki` if it hits a newer, incompatible one.

For each card it renders the answer side, strips HTML/sound/image tags, and splits what's left into the list of words you'll type — the question side is kept as-is (with its HTML) and shown above the blanks. The answer side's own HTML (what follows `<hr id=answer>`, images included) is kept too, as `answer`, for the card browser.

## Step 3 — Import into the app

Open `index.html`, click **＋ Importer un fichier .json**, and pick the file `extract.py` produced. Each source you import stays independent (its own progress, own decks), so you can import several exports side by side.

## Step 4 — Push your progress back into Anki

Click 📤 next to the source to download its stats, then run:

```bash
ankisync                           # shell function in ~/.bashrc (see below)
# or: trainervenv/bin/python sync_to_anki.py   (Anki must be closed)
```

`ankisync` quits Anki if it's open, runs `sync_to_anki.py` on every `~/Downloads/*_stats*.json`, then reopens Anki so its normal sync sends everything to AnkiWeb. The script writes straight into your local Anki collection (auto-detected profile; a backup is made first), so there's no `.apkg` to re-import. Only cards you actually studied in the app are pushed, and a card you've since reviewed in Anki is left alone. Each pushed card gets a "Manual" entry in Anki's review history, so re-running the command over old downloads is harmless. Cards started for the first time today (in the app or in Anki) are also counted against Anki's daily new-card limit, per deck and its parents, so Anki doesn't offer another 20 new cards on top of what you already did in the app. `ankisync --dry-run` previews.

Words added with `add_card.py` / `cuatroloop` are created in Anki first: one "Basic (and reversed card)" note per pair in the `perso` deck, with the app's card ids so their progress syncs too. A word is skipped if a note with the same front already exists in Anki, or if its "translation" is identical to the word (e.g. `orage → orage`).

```bash
ankisync() {
  local repo="/Users/quang/Documents/espanol-trainer"
  local was_open=0
  if pgrep -if "Anki.app/Contents/MacOS|aqt\.run" >/dev/null; then
    was_open=1
    osascript -e 'quit app "Anki"'
    while pgrep -if "Anki.app/Contents/MacOS|aqt\.run" >/dev/null; do sleep 0.5; done
  fi
  "$repo/trainervenv/bin/python" "$repo/sync_to_anki.py" "$@" || return
  case " $* " in *" --dry-run "*) [ $was_open = 1 ] && open -a Anki; return ;; esac
  open -a Anki
}
```

`reimport_stats.py` still exists for the `.apkg` route, e.g. on a machine without your Anki profile.

---

## How studying works

- Pick a deck (or a parent deck, which studies all its sub-decks together) from the home screen; badges show how many cards are **new**, **due**, and already **learned**.
- The question is shown as a card; type each word of the answer into its blank, inside the card under its "verso" line.
- The **⌨️ Saisie / 🃏 Mode normal** toggle at the top of the study screen (remembered per browser) switches to plain Anki-style review: **Space** shows the back in the card, then rate with the buttons, **1–4** or **F2/F3/F4/F7** (**Space** again = Correct).
- Accents are optional — `ame` is accepted for `âme`.
- The bottom bar holds the actions as pills: **💡 Indice** (F1) shows the word at the cursor, **Voir la réponse** (F8) shows the whole answer. Once every missing word is shown (or after F8), the bar turns into the 4 rating pills (À revoir · Difficile · Correct · Facile, F2/F4/F3/F7); typing the words or pressing F1 once more still rates À revoir and moves on.
- On phones the card has a fixed shape sized to what the keyboard leaves visible: the recto half and the type-in/verso half each scroll on their own around a fixed "verso" line, and while the keyboard is up only the 💡 Indice / Voir la réponse pills stay (tapping Indice keeps the keyboard up); counters and rating pills show once it is down.
- **F6** (no on-screen button) marks the card to fix in Anki; 🚩 on the home screen lists the marked cards.
- The rating's color lights up the card (red / orange / green / blue) when it's automatic or from the keyboard; clicking or tapping a pill only lights up that pill.
- After 3 wrong attempts on a word, a hint appears; **💡 Voir les réponses** reveals everything, **Passer →** skips.
- **🔍** on any deck row opens a read-only card browser: decks with pictures get a carousel (front and back together; swipe, mouse wheel, **← / →** or ‹ › to move), word/sentence decks a dense `front | back` list; the search box filters on both sides (accents ignored), **Esc** goes back. Nothing you do there touches scheduling. JSON made before `answer` existed shows the typed words as the back.
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
> can you put that to "project", separate in so-called "ui","machanic","learning" various themes, yeah as you said (keep the readme clean from my ai comments, don't push the comments)
- **Lighter reveal for typed-correct words.** When a card is completed by typing alone (no reveal used), consider only highlighting the rectangle around each solved word instead of the current display — mirrors how little real Anki shows you when you already knew the answer.
- **Connect directly to Anki via its API?** AnkiConnect (a well-known Anki add-on) exposes a local HTTP API for reading/writing a real, running Anki collection — worth a look as an alternative to the `extract.py`/`.apkg` round-trip for some workflows.
- **Other languages (Chinese) — parked on the `chinois` branch.** The Refold Mandarin deck needs more than this app does today: its note type's CSS leaks into the page and its fonts get overridden (fix: render cards in a Shadow DOM), and the generic "type the whole back" rule would ask for hanzi + pinyin + meaning + sentence (fix: a per-note-type field to type, the pinyin here). The branch holds an untested first pass; not merged since bundling that deck's media isn't wanted until decks can be uploaded to a server.
- **Image-occlusion diagram quizzes — in progress on the `image-occlusion-quiz` branch.** The idea: a labeled diagram (e.g. a car) where you type each part's name instead of flipping a card, built on Anki's native **Image Occlusion** note type so the same cards work unmodified in real Anki. One note per diagram, one masked region (cloze) per part — confirmed round-tripping correctly through Anki's own import/export with real coordinates (`left`/`top`/`width`/`height` as 0–1 fractions of the image, e.g. `{{c1::image-occlusion:rect:left=.051:top=.415:width=.114:height=.065:oi=1}}`, shapes joined by `<br>` in the note's `Occlusion` field). `car_diagram.svg`/`.png` on that branch is a hand-built reference diagram (10 labeled parts: parabrisas, espejo, volante, asientos, maletero, intermitente, motor, rueda, puerta, carretera) with an example `.apkg` masking each one. Still to do: `extract.py` support for reading this note type back into JSON, and a web-app study mode that prompts one part at a time, keeps correct labels visible, requeues wrong/revealed ones, and gives the whole diagram one overall SRS rating once every part's been typed correctly.
- browser can show already learnt, due card - either way with color or filter
- chose keybinding

### Learning
- add per tree sub collection having some info about it or tag (recognize tree - info - etc) then also add possibility to filter tag

### Idees etranges
- un caroussel de mots marqués à revoir défilant en haut de l'ui avec les cartes en mode apprentissage
- un raccourci pour ajouter des mots à apprendre

## Known bugs
> Can you add this to github "issues"

- Saw a case with 3 wrong marks (❌) already under a word where pressing F1 (reveal) then graded the card as Correct instead of À revoir.
- Typing fast enough doesn't always advance to the next blank in time.
- there a bug with mouse scroll on the caroussel, it get stuck when scolling fast (maybe just a bug of the mouse)


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
        { "id": "111", "question": "<b>question HTML</b>", "answer": "answer HTML", "words": ["word1", "word2"], "tags": ["tag1"] }
      ]
    }
  ]
}
```
