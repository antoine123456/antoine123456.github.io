# Español Trainer

Fill-in-the-blank song lyric trainer for Spanish. Translations are pre-generated offline via the Anthropic API and stored in `songs.json` — no API key needed inside the browser.

## Folder structure

```
espanol-trainer/
├── index.html       ← standalone training app (open in any browser)
├── preprocess.py    ← CLI script: generates JSON from lyrics via Anthropic API
├── songs.json        ← built-in song database, shown automatically on the home screen
└── README.md
```

---

## Step 1 — Prepare lyrics

Create a plain `.txt` file with the lyrics. Separate strophes with a blank line. Optionally, label each strophe with `[Label]` on the first line of that block:

```
[Couplet 1]
Tiene la expresión de una flor
La voz de un pájaro

[Couplet 2]
Tienen sus palabras calor y frío de invierno
Y tiene el corazón de poeta
```

---

## Step 2 — Pre-process with `preprocess.py`

### Install dependencies

```bash
pip install anthropic
```

### Set your API key

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

Get a key at [console.anthropic.com](https://console.anthropic.com).

### Run

```bash
python preprocess.py \
  --title "Corazón de Poeta" \
  --artist "Jeanette" \
  --lyrics lyrics.txt \
  --lang French \
  --out corazon_de_poeta.json
```

| Option | Description |
|--------|-------------|
| `--title` | Song title (required) |
| `--artist` | Artist name (optional) |
| `--lyrics` | Path to the `.txt` file (required) |
| `--lang` | Target language, e.g. `French`, `English` (default: `French`) |
| `--out` | Output `.json` path (required) |

The script calls `claude-haiku-4-5` once per unique line, with 3 retries and exponential backoff. A 30-line song costs roughly $0.01–0.03.

---

## Step 3 — Add to the song database

Open `index.html` in any modern browser (Chrome, Firefox, Safari), or via GitHub Pages.

Songs are read from `songs.json` and shown directly on the home screen — no import needed. To add a song, append its generated JSON object to the array in `songs.json`.

> **Note:** the **Importer une chanson** button on the home screen is a placeholder for now — it is visible but disabled, since it can't yet save a song anywhere durable. Maintain `songs.json` directly instead.

---

## How training works

- Each phrase appears as a row of Spanish words above blank input fields.
- Type the French (or target-language) translation for each word.
- Accents are optional — `ame` is accepted for `âme`.
- After 3 wrong attempts on a word, a hint appears.
- When all words in a phrase are correct, the app advances automatically.
- Use **💡 Voir les réponses** to reveal all answers, **Passer →** to skip.

---

## Publish to GitHub

```bash
cd espanol-trainer
git init
git add .
git commit -m "feat: initial Español Trainer"

# Create a repo on github.com, then:
git remote add origin https://github.com/YOUR_USERNAME/espanol-trainer.git
git branch -M main
git push -u origin main
```

To host the app on GitHub Pages:
1. Go to repo **Settings → Pages**
2. Set source to **main branch, / (root)**
3. The app will be live at `https://YOUR_USERNAME.github.io/espanol-trainer/`

> `songs.json` must be committed and pushed — it's the built-in song database GitHub Pages serves to every visitor. `.gitignore` already excludes `trainervenv/` and other local-only files.

---

## JSON format reference

```json
{
  "title": "Song Title",
  "artist": "Artist Name",
  "targetLang": "French",
  "strophes": [
    { "label": "Couplet 1", "text": "Line one\nLine two" }
  ],
  "translations": {
    "Line one": [
      { "w": "spanish_word", "t": ["translation1", "variant2"] }
    ]
  }
}
```

`t` is an array of accepted translations (case-insensitive, punctuation-stripped). Words with an empty `t: []` are displayed but not checked.
