# Español Trainer

Fill-in-the-blank song lyric trainer for Spanish. Each song's word-by-word translations are generated ahead of time with an AI assistant and stored in `songs.json` — no API key or backend needed inside the browser.

## Folder structure

```
espanol-trainer/
├── index.html   ← standalone training app (open in any browser)
├── songs.json   ← built-in song database, shown automatically on the home screen
└── README.md
```

---

## Step 1 — Generate a song's JSON with an AI assistant

Open the app, click **＋ Importer une chanson**, and copy the prompt shown at the top of the modal (also reproduced below). Paste it into an AI assistant (Claude, ChatGPT...), replace the placeholder with the song's lyrics, and run it:

```
Tu es un générateur de données pour "Español Trainer", une appli d'apprentissage de l'espagnol par traduction mot à mot.

Voici des paroles de chanson en espagnol (les strophes sont séparées par une ligne vide) :

[COLLE ICI LES PAROLES DE LA CHANSON]

Génère UNIQUEMENT un objet JSON valide (pas de texte avant/après, pas de balises markdown) avec exactement cette structure :

{
  "title": "Titre de la chanson",
  "artist": "Nom de l'artiste",
  "targetLang": "French",
  "strophes": [
    { "label": "Couplet 1", "text": "ligne 1\nligne 2" }
  ],
  "translations": {
    "ligne exacte telle qu'elle apparaît dans strophes": [
      { "w": "mot ou courte expression en espagnol", "t": ["traduction principale", "variante si utile"] }
    ]
  }
}

Règles :
- Une clé dans "translations" par ligne UNIQUE des paroles (si une ligne se répète, ex. un refrain, ne la traduis qu'une fois).
- Découpe chaque ligne en mots ou courtes expressions ("w"), dans l'ordre d'apparition, en couvrant toute la ligne.
- Donne 1 à 3 traductions correctes et naturelles en français dans "t" (pas de synonymes trop éloignés).
- Les interjections ou mots difficiles à traduire seuls peuvent avoir "t": [].
- Regroupe les lignes en strophes avec un "label" pertinent (Intro, Couplet 1, Refrain, Pont, Outro...), dans l'ordre du texte original, refrains répétés inclus.
```

The `strophes` array matters even though `translations` already holds every line: it's what tells the app the **order** the lines play in, groups them under section **labels** (shown during training), and preserves **repeats** (a chorus that comes back twice must appear twice in `strophes.text`, even though it only needs one entry in `translations`). Without it the app would have no way to reconstruct the song's actual structure from a flat translation dictionary.

---

## Step 2 — Add to the song database

Open `index.html` in any modern browser (Chrome, Firefox, Safari), or via GitHub Pages.

Songs are read from `songs.json` and shown directly on the home screen — no import needed. To add a song, append its generated JSON object to the array in `songs.json`.

> **Note:** the **Importer une chanson** button on the home screen is a placeholder for now — it is visible but disabled, since it can't yet save a song anywhere durable. Maintain `songs.json` directly instead.

---

## Step 3 (optional) — Sync a YouTube video

Add a `video` field to a song entry to embed its YouTube video during training. The video plays through each line, then auto-pauses right before the next one starts — giving you a pause window to fill in the blanks — and resumes once you complete the phrase (or hit **Passer →**):

```json
{
  "title": "...",
  "artist": "...",
  "strophes": [ ... ],
  "translations": { ... },
  "video": {
    "youtubeId": "VIDEO_ID_HERE",
    "cues": ["0:11", "0:23", "0:31"]
  }
}
```

- `cues[i]` is the timestamp (seconds, or `"mm:ss"` / `"h:mm:ss"`) at which line *i* of `strophes` starts in the video — one entry per line, in the same order (repeated lines like a chorus need their own entry each time they occur).
- Easiest way to get these timestamps: open the video on YouTube, click **···** below the player → **Show transcript**, and copy the time shown next to the point where each of your lyric lines begins. No manual tapping or extra tooling needed.
- If `cues` has fewer entries than the song has lines, sync simply stops applying after the last provided cue — the trainer still works, just without auto-pause for the remaining lines.
- The YouTube player needs the page served over `http://` or `https://` (a local server or GitHub Pages) — it won't initialize when `index.html` is opened directly as a `file://` URL.

---

## How training works

- Each phrase appears as a row of Spanish words above blank input fields.
- Type the French (or target-language) translation for each word.
- Accents are optional — `ame` is accepted for `âme`.
- After 3 wrong attempts on a word, a hint appears.
- When all words in a phrase are correct, the app advances automatically.
- Use **💡 Voir les réponses** to reveal all answers, **Passer →** to skip.

## Progress tracking

The app automatically saves progress in the browser's `localStorage`: how far you got in each song (so reopening a song resumes where you left off), how many words you found on the first try, and which songs you've completed — including whether you completed one without a single mistake ("★ Parfaite").

Since this is a static site with no account system, that data lives only in one browser. To carry it to another browser or device, open **📊 Progression** on the home screen and copy the export code — pasting it back in on the other side (via the same panel) restores it there.

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
