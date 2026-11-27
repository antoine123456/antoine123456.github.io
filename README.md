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
├── enrich_es.py       ← builds enrich_es.json: example sentence (from the deck's own sentence cards) + word class for the Spanish cards' « rendu complet » — re-run when default.json changes
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
- **One box** (#249): a card already seen (a new one back in the same session too) starts with a single box for the whole answer — the word boxes would give away how many words and how long. A miss (Entrée), Entrée with nothing typed, a hint or the answer brings the word boxes back. In the boxes, Entrée on an empty box gives that word's hint.
- **What counts as right:** accents are optional; every meaning written on the card is accepted, not only the first one to type (« je te tiens au courant » for te aviso); the French / Italian article of a noun is optional (« maison » for la casa — FR → ES cards still ask for the Spanish article, it's the gender); meanings added in the terminal (`+`) too.
- The **⌨️ Saisie / 🃏 Mode normal** toggle at the top of the study screen (remembered per browser) switches to plain Anki-style review: **Space** shows the back in the card, then rate with the buttons, **1–4** or **F2/F3/F4/F7** (**Space** again = Correct).
- The bottom bar holds the actions as pills: **💡 Indice** (F1) shows the word at the cursor, **Voir la réponse** (F8) shows the whole answer. Once every missing word is shown (or after F8), the bar turns into the 4 rating pills (À revoir · Difficile · Correct · Facile, F2/F4/F3/F7); typing the words or pressing F1 once more still rates À revoir and moves on.
- On phones, and in any window where the card would run under the bottom bar, the card switches to a compact fixed shape sized to the visible screen (and to what the keyboard leaves visible): the recto half and the type-in/verso half each scroll on their own around a fixed "verso" line, and while the keyboard is up only the 💡 Indice / Voir la réponse pills stay (tapping Indice keeps the keyboard up); counters and rating pills show once it is down.
- **F6** (no on-screen button) marks the card to fix: it leaves the session and is never offered again (🚩 on the home screen lists the marked cards). The stats export (📤) carries them, and the next `ankisync` flags them red, tags them `a_corriger`, suspends them in Anki and lists them for review.
- **Staged cards** (tag `etapeN`, e.g. the bundled **Grammaire** source, `grammaire.json`, extracted from Anki's `🇪🇸 Espagnol::Grammaire`): stage N's new cards stay locked (🔒 badge) until at least 80 % of every earlier stage's cards are in review. `ankisync` applies the same rule in Anki: locked new cards are suspended with the tag `etape_verrou` and unsuspended once their stage opens.
- **Automatic ratings** (#249, as Anki / FSRS mean them): the answer seen (hint, word given after 3 misses) = À revoir; found alone with effort (2 misses or more, the one box missed, far slower than usual) = Difficile; with the word boxes = Correct; in the one box at once, on a card seen before today = Facile. The four pills then stay, the one given lit, with why in a bubble that floats up (aide, 3 erreurs, trop lent…), and the card gets a frame in its colour (red / orange / green / blue); another pill gives that rating instead.
- **Both directions, not the same day** (#269): as Anki buries siblings, once a word is answered one way (🇪🇸 → 🇫🇷 or 🇫🇷 → 🇪🇸), its other direction waits until tomorrow (unless it's in learning steps) — else « así que » then « donc » a minute later gave the answer away.
- **📴 Offline** (#276): `sw.js`, a service worker, keeps the page, the decks and the sounds / pictures already loaded, so the app opens without network once it has been opened with it. Answers were already kept on the device after each card and sent to Firestore when the network comes back.
- **⌫** on a card where nothing has been typed yet shows the card before, whole, with its rating; Espace / Entrée go on.
- **≠ Words that get mixed up** (`confusables.py`: todavía / siempre, saber / conocer, ver / mirar…): the difference is in the blue note on the back, with the group's other words; in 🔍 a click looks them up.
- **🔍** on any deck row opens a read-only card browser: decks with pictures get a carousel (front and back together; swipe, mouse wheel, **← / →** or ‹ › to move), word/sentence decks a dense `front | back` list; the search box filters on both sides (accents ignored), **Esc** goes back. Nothing you do there touches scheduling. JSON made before `answer` existed shows the typed words as the back.
- The next review is scheduled with a lightweight SM-2 algorithm. New cards per day follow the ⚙ setting (synced between devices); cards rated « À revoir » come back later in the same session. A setting changed during a session applies from the next card.

---

## Songs (lyrics view)

`songs.json` (3 songs, from the old `lyrics-trainer` branch) is bundled as a **Chansons** source — one deck per song, studied like any other deck. Each distinct lyric line is a card (a repeated chorus line is one card): you type the Spanish line, with its French gloss as the hint. The study screen shows the whole song like a lyrics player — lines you know as text, the active line centred with its blanks, the rest as greyed blanks — and keeps the song's order: due lines and new lines go top to bottom, lines to see again come back in a second pass. **⚙** in the top bar holds options to try out: hint (French gloss / context only / first letters) and new lines (one verse at a time / 5 lines / whole song). Songs in the same JSON format (e.g. generated with the AI prompt from the `lyrics-trainer` branch) can be added with **＋ Importer**. Song cards don't exist in Anki, so `ankisync` reports them as missing ids.

---

## Learning theory (development milestones)

The app's development follows Paul Nation's **four strands**: a balanced language course gives roughly equal time to each. They are the GitHub milestones *Volet 1–4*.

| Strand | What it is | In the app today |
|---|---|---|
| 1 — Comprendre (meaning-focused input) | lots of comprehensible reading/listening (~98 % known words) | songs |
| 2 — Produire (meaning-focused output) | writing/speaking to say something | — (issues #40, #42) |
| 3 — Langue (language-focused learning) | explicit vocabulary, conjugation, grammar | cards, spaced repetition |
| 4 — Fluidité (fluency) | doing it fast with what is already known | quick reviews |

Other findings the design leans on: the **testing effect** and **spaced repetition** (recalling beats rereading), the **involvement load hypothesis** (Laufer & Hulstijn — a word sticks when you must search for it, choose it and use it yourself), the **output hypothesis** (Swain — producing reveals what you can't say yet), and **~98 % lexical coverage** for a text to be understood and useful (Nation, Hu).

---

## Publish to GitHub Pages

The app is at **https://antoine123456.github.io/typeinanki/** (#226). Repo
`antoine123456/typeinanki` serves it, and its `main` is a copy of branch
`firebase-debug`. To deploy, after pushing `main`:

```bash
cd ../espanol-trainer-firebase        # worktree of firebase-debug
git merge main -m "Merge main"        # keep the NS + "…" localStorage keys on conflicts
git push origin firebase-debug
git push typeinanki firebase-debug:main
```

The site root, https://antoine123456.github.io/, is served from branch `site`
of this repo: a list of links, where other pages can go. Its `404.html` sends
the app's old addresses (`/?fantome=…`, `/app.html`…) to `/typeinanki/`. All
the app's links are relative, so it works under any path. It's still the same
domain, so the data saved in the browser carried over.

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

## Terminal trainer (`trainer.py`)

A presentation, with a sample session: [docs/ankiterm.md](docs/ankiterm.md).

A minimalist version of the app in the terminal (#215): the front of the
card, you type the back. It has no sound and no pictures (a card with only a
picture isn't asked).
Progress is the same as the app's: Firestore (`users/<name>/sources/<deck>`),
written card after card with the same scheduler. Only the reviewed card's
`srs` entry is written, so the other cards stay untouched. Standard library
only:

Install it as the `ankiterm` command (a link in `~/.local/bin`, already on the
PATH, so no shell config to edit):

```bash
chmod +x trainer.py && ln -sf "$PWD/trainer.py" ~/.local/bin/ankiterm
```

Then `ankiterm` from anywhere takes the same arguments as `python3 trainer.py`:

```bash
python3 trainer.py              # 1st time: who are you? then every deck with cards today, one after the other
python3 trainer.py -l           # the list of decks, to pick one
python3 trainer.py vocab        # first deck whose name has « vocab »
python3 trainer.py vocab -d "Niveau 2" -n 10   # sub-decks with « Niveau 2 », 10 new cards
python3 trainer.py --dry        # write nothing
python3 trainer.py --user       # pick the name again
python3 trainer.py --voir veo   # a word's details (veo → ver)
python3 trainer.py --dico       # a small explorer of the Vocabulaire and the Grammaire
python3 trainer.py --restaurer  # put back the reviews of the log that an older copy overwrote (--dry: count only)
python3 trainer.py --journal    # day by day: answers, new cards, right at once, intervals given
```

- **During a card:** type the answer and press Entrée. Accents and punctuation
  don't count.
- **Checking:** a wrong answer can be retyped, up to three tries; after that
  the answer shows (in red) and the card is rated À revoir. `?` shows the answer
  at once (À revoir too). A right answer is rated as in the app: at once on a
  card seen before today = Facile (✓ in blue), else Correct (green); after 2
  misses, or far slower than usual (the app's ⚙ « trop lent ») = Difficile
  (yellow); with the table = À revoir. The rating and why follow the ✓.
- **Keywords:** `:word` or its first letter(s) can't be taken for an answer —
  `:h` / `:i` help, `:t` table, `:s` / `:ti` what's left, `:d` dump, `:q` stop.
  The plain words (`info`, `help`, `tab`, `stats`, `temps`, `dump`, `q`) and
  `i`, `h`, `t` alone still work.
- **Last seen:** next to each card, how long since it was last answered (« vue il y a 3 j », or « nouvelle »).
- **Entrée twice** with nothing typed shows the card again.
- **When it comes back:** after the ✓ (or the answer, after a miss), as Anki
  shows it above its buttons: « Correct (4j) », « À revoir (<1m) ».
- **Pause:** `:p` stops the clock until Entrée. Each wait for an answer counts
  60 s at most anyway, so a break while a card is up doesn't count either.
- **Same answer, not twice in a row:** a card whose answer was just on screen
  (missed on another card — « han » for the gap sentence and for haber — or in
  a table) waits until it has scrolled out of sight.
- **Offline:** a review Firestore didn't take (« timed out ») is sent again after the next cards, and before leaving; what still couldn't be is kept in `trainer.json` and sent at the next start (the newer answer wins).
- **A word's details (`:v mot`, or `ankiterm --voir mot`):** its Vocabulaire card (meanings, word class, sentence, the ≠ note and the words it gets mixed up with), where each direction stands (last seen, when it comes back, lapses), and the verb a form comes from — veo → ver, tenemos → tener, presente, nosotros. Doesn't use a try.
- **Explorer (`:e [mot]`, or `ankiterm --dico [mot]`):** a very small explorer of the Vocabulaire and the Grammaire, straight on a search: a bit of a word, Spanish or French (accents ignored), the exact word first, 15 at most; a number shows that word's details (as `:v`), another text searches again, Entrée goes back to the card.
- **Both directions, not the same day:** as in the app (#269), a word answered one way today sends its other direction to tomorrow.
- **Challenge (`ankiterm --defi [tag]`):** one minute to type, from memory, as many Spanish words of a tag as you can (verbe, adjectif, états et émotions…), each checked against the Vocabulaire; the best score per tag is kept, and the most frequent words you didn't give are listed at the end.
- **Log:** every card answered goes into `~/.config/espanol-trainer/log.tsv`
  (when, deck, card, rating, when it comes back, seconds, where it stood before);
  `:l` shows today's cards, those seen several times first. A `--dry` session
  writes nothing there.
- **Journal (`ankiterm --journal`):** to check the algorithm, day by day from the
  log: answers and cards, new ones, answers per card, the known cards right at
  their first answer of the day (Anki aims at 85–90 %), the intervals given
  (<1j · 1-3j · 4-10j · 11-30j · >30j), then the Vocabulaire cards due on each of
  the next 14 days.
- **Gap sentences:** « A mí me ___ el chocolate » takes « gusta » or « me gusta ».
- **Time:** the end count adds up the time spent on each card (60 s at most per
  answer, nothing during `:p`), so a session left open doesn't count.
- **Self-rated cards:** for the 🌊 formulas and turned-over cards, Entrée turns
  the card over, then Entrée = knew it and `n` = didn't.
- **`dump`:** typed as an answer, lists every card left, with its answer.
- **`stats`** (or **`temps`**): shows the cards left: new · learning · review,
  in blue · red · green, and the time left (« ≈ 12 min »: each card's usual
  time, a new card ×3 for its repeats, a learning one ×1.5).
- **`info`:** shows the keywords and a short guide.
- **`tab`:** on a Grammaire conjugation card, the table of that verb and tense
  (stem plain, ending in green, this card's person marked ›), like F1 in the
  app. The table shows the answer, so the card ends « À revoir ».
- **`save`:** says « enregistré ». Each card is already saved as soon as it's
  answered, so there's nothing left to send.
- **No try used:** the keywords and `+` don't use up one of the three
  tries.
- **Adding a meaning** (Vocabulaire only — a conjugation or a gap sentence has one right answer): after a miss, `+` adds your last answer to the card's
  accepted answers, or `+ another meaning` adds that one instead. Use it when
  your meaning was right but not in the list: the card counts as Correct. It's
  saved as an edit in Firestore (`card.alt`), so the terminal accepts it
  everywhere, and the app accepts it too: in the one box, or typed across the
  word boxes.
- **Too late for `+`?** Typed first on the next card (before any try there),
  `+` (or `+ another meaning`) adds the meaning to the card just before — if
  it was missed (then rated Correct instead of À revoir), or found after a try
  that wasn't taken (its rating stays). The question names the card
  (« ajouter « au lieu de » à « en vez de » ? »); `n` offers it to this card instead.
- **After a miss:** `tab` still shows the table at the « Entrée = suivante » prompt. The answer shows in red (like the learning count after
  it: the card goes back there), then the cards left and the time left show, as under the app's cards:
  new · learning · review, in blue · red · green. The screen isn't wiped:
  the missed card — and, after `tab`, the other forms of that table — comes back only once its answer has scrolled out of the
  window (other cards go first; if none is left, blank lines push it up), so
  it can't be copied from the screen.
- **Stopping:** `q` stops.
- **Deck:** with no deck named, every deck with cards today, one after the
  other — the one reviewed last (in the app or here) first, not the 💤 ones;
  `-l` shows the list instead, with the last one as default (Entrée).
- **Name:** the chosen name is kept in `~/.config/espanol-trainer/trainer.json`.

Same cards in the same order as the app: the terminal draws the day's queue
with the app's seed (day + deck), its shuffle, its stage locks and its 🚩
marks. So you can start a session in the app and finish it in the terminal,
or the other way round: each review is saved at once, and the other side
picks up where it stopped. The app's ⚙ settings are synced (`users/<user>.settings`),
so the terminal allows as many new cards as the app: its « nouvelles cartes
par jour », or in time mode the number the app worked out today. `-n` still
overrides it.

The app takes the terminal's reviews when it loads, and a card's most recent
review wins. Since #279 the app never sends an older review over a newer one: before
each sync it reads the cloud, keeps each card's most recent review, and sends
only the cards reviewed more recently on its side (before, a tab left open
sent its whole copy back and wiped 328 cards reviewed in the terminal).
`ankiterm --restaurer` replays `log.tsv` over what Firestore still has, card
by card, each « revient » taken from the log, and writes only the cards
behind it. Reload the app's tab after a terminal session, or an open tab may
send its older copy back.

---

## Tags of idee.md (`tags_snippets.py`)

The `## Tags` section of `idee.md` is a table, one line per tag with its
description. `tags_snippets.py` reads that table and writes
`.vscode/markdown.code-snippets`, so typing `@v` in a Markdown file offers
`@v1` with its description. It needs no Claude and no package. To run it:

- **In VS Code:** F1 → « Tasks: Run Task » → « Tags → snippets » (it also runs
  when the folder opens).
- **In a terminal:** `python3 tags_snippets.py [idee.md]`.

It also lists the tags used in the file but missing from the table.

---

## Reading music (`build_partition.py`, #259)

`partition.json` (bundled deck « 🎼 Partition ») is generated by `build_partition.py`: one note on a staff per card (inline SVG drawn in `currentColor`, so it follows the dark theme), answered on a wheel of notes (`card.wheel`, ♯ / ♭ in the middle with `card.wheelAcc`, #283) or typed on a computer (do, ré, mi…, « fa dièse »). Five numbered levels open one after the other: treble clef on the staff, treble ledger lines, bass clef, bass ledger lines, sharps and flats. The back says where the note sits and its English name (E4…). Clef and accidental outlines come from GNU FreeSerif (needs `pip install fonttools`).

```
python3 build_partition.py
```

## Future work
> can you put that to "project", separate in so-called "ui","machanic","learning" various themes, yeah as you said (keep the readme clean from my ai comments, don't push the comments)
- **Lighter reveal for typed-correct words.** When a card is completed by typing alone (no reveal used), consider only highlighting the rectangle around each solved word instead of the current display — mirrors how little real Anki shows you when you already knew the answer.
- **Connect directly to Anki via its API?** AnkiConnect (a well-known Anki add-on) exposes a local HTTP API for reading/writing a real, running Anki collection — worth a look as an alternative to the `extract.py`/`.apkg` round-trip for some workflows.
- **Other languages (Chinese) — parked on the `chinois` branch.** The Refold Mandarin deck needs more than this app does today: its note type's CSS leaks into the page and its fonts get overridden (fix: render cards in a Shadow DOM), and the generic "type the whole back" rule would ask for hanzi + pinyin + meaning + sentence (fix: a per-note-type field to type, the pinyin here). The branch holds an untested first pass; not merged since bundling that deck's media isn't wanted until decks can be uploaded to a server.
- **Image-occlusion diagram quizzes — in progress on the `image-occlusion-quiz` branch.** The idea: a labeled diagram (e.g. a car) where you type each part's name instead of flipping a card, built on Anki's native **Image Occlusion** note type so the same cards work unmodified in real Anki. One note per diagram, one masked region (cloze) per part — confirmed round-tripping correctly through Anki's own import/export with real coordinates (`left`/`top`/`width`/`height` as 0–1 fractions of the image, e.g. `{{c1::image-occlusion:rect:left=.051:top=.415:width=.114:height=.065:oi=1}}`, shapes joined by `<br>` in the note's `Occlusion` field). `car_diagram.svg`/`.png` on that branch is a hand-built reference diagram (10 labeled parts: parabrisas, espejo, volante, asientos, maletero, intermitente, motor, rueda, puerta, carretera) with an example `.apkg` masking each one. Still to do: `extract.py` support for reading this note type back into JSON, and a web-app study mode that prompts one part at a time, keeps correct labels visible, requeues wrong/revealed ones, and gives the whole diagram one overall SRS rating once every part's been typed correctly.
- browser can show already learnt, due card - either way with color or filter
- chose keybinding
- **Active practice (issue #40)** — the app is mostly recognition/recall of single cards; ideas to make the vocabulary *used*:
  - write a short text in Spanish at the end of a session with the words just studied, downloaded like the stats and corrected here by Claude (badly used words back to "À revoir");
  - a short text written by Claude with the learnt vocabulary + comprehension questions — ideally built on a real news item, so it makes sense;
  - dictation from the cards' recorded audio or the browser's speech synthesis (demo to evaluate audibility);
  - translate short French sentences reusing the day's words; build a sentence with imposed words.
- **Greyed-out hint inside the blank** — tried and set aside (git tag `indice-fantome`, issue #26): on phones the keyboard capitalizes the first letter, typing starts in the middle of the centered blank, and the fixed grey word doesn't line up with what's typed. The hint is back in small orange under the blank.
- instead of automatically switch to the newt blank, wait for "space"
- keep this "future work" in track with the github project
- temps de transition apres correct parfois long ? simplement temps de l'audio 
- maybe orange instead of red if typed after the hint ?

### Learning
- add per tree sub collection having some info about it or tag (recognize tree - info - etc) then also add possibility to filter tag

### Idees etranges
- un caroussel de mots marqués à revoir défilant en haut de l'ui avec les cartes en mode apprentissage
- un raccourci pour ajouter des mots à apprendre

## Known bugs

Tracked as `bug` issues on the [project board](https://github.com/users/antoine123456/projects/1).

- Mouse-wheel scrolling on the carousel sometimes gets stuck when scrolling fast (maybe just the mouse) — #4.

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
