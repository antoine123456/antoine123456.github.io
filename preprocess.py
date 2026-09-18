#!/usr/bin/env python3
"""
preprocess.py — Generate word-by-word translation data for Español Trainer.

Usage:
  python preprocess.py --title "Corazón de Poeta" --artist "Jeanette" \
                       --lyrics lyrics.txt --lang french --out song.json

The generated JSON can be imported directly into index.html.

Requirements:
  pip install anthropic
  export ANTHROPIC_API_KEY=sk-ant-...
"""

import argparse
import json
import os
import re
import sys
import time

try:
    import anthropic
except ImportError:
    sys.exit("Missing dependency: pip install anthropic")


# ── Helpers ──────────────────────────────────────────────────────────────────

def parse_lyrics(text: str) -> list[dict]:
    """Split raw lyrics text into strophes. Blank lines separate strophes.
    Lines starting with [ ] are treated as labels."""
    strophes = []
    for i, block in enumerate(re.split(r"\n{2,}", text.strip())):
        lines = [l.rstrip() for l in block.strip().splitlines()]
        if not lines:
            continue
        label = None
        if lines[0].startswith("[") and lines[0].endswith("]"):
            label = lines[0][1:-1].strip()
            lines = lines[1:]
        strophes.append({
            "label": label or f"Strophe {i + 1}",
            "text": "\n".join(lines),
        })
    return strophes


def extract_json_array(raw: str) -> list | None:
    """Robustly extract the first [...] block from a string."""
    start = raw.find("[")
    if start == -1:
        return None
    depth, end = 0, -1
    for k in range(start, len(raw)):
        if raw[k] == "[":
            depth += 1
        elif raw[k] == "]":
            depth -= 1
            if depth == 0:
                end = k
                break
    if end == -1:
        return None
    try:
        result = json.loads(raw[start : end + 1])
        return result if isinstance(result, list) else None
    except json.JSONDecodeError:
        return None


def translate_line(client, line: str, target_lang: str, retries: int = 3) -> list[dict]:
    """Ask Claude to translate each token of a Spanish line."""
    prompt = (
        f"Translate each token of this Spanish sentence into {target_lang}.\n"
        "Reply ONLY with a valid JSON array, no markdown, no extra text.\n"
        'Format: [{"w":"token","t":["main translation","variant if needed"]}]\n'
        "Give 1–3 valid translations per word (no distant synonyms).\n"
        f'Sentence: "{line}"'
    )
    for attempt in range(retries):
        try:
            msg = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=600,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = msg.content[0].text
            arr = extract_json_array(raw)
            if arr and len(arr) > 0:
                return arr
        except Exception as e:
            print(f"  ⚠ attempt {attempt + 1} failed: {e}", file=sys.stderr)
            time.sleep(1.5 * (attempt + 1))
    # Fallback: tokens with no expected answers
    return [{"w": w, "t": []} for w in line.split()]


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate Español Trainer translation JSON")
    parser.add_argument("--title",  required=True, help="Song title")
    parser.add_argument("--artist", default="",    help="Artist name")
    parser.add_argument("--lyrics", required=True, help="Path to lyrics .txt file")
    parser.add_argument("--lang",   default="French", help="Target language (default: French)")
    parser.add_argument("--out",    required=True, help="Output .json path")
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit("Set ANTHROPIC_API_KEY environment variable before running.")

    with open(args.lyrics, encoding="utf-8") as f:
        lyrics_text = f.read()

    strophes = parse_lyrics(lyrics_text)
    all_lines = []
    for s in strophes:
        for line in s["text"].splitlines():
            line = line.strip()
            if len(line) > 1:
                all_lines.append(line)
    unique_lines = list(dict.fromkeys(all_lines))  # deduplicate, preserve order

    print(f"Song     : {args.title}" + (f" — {args.artist}" if args.artist else ""))
    print(f"Language : {args.lang}")
    print(f"Lines    : {len(unique_lines)}")
    print()

    client = anthropic.Anthropic(api_key=api_key)
    translations = {}

    for i, line in enumerate(unique_lines):
        print(f"[{i + 1}/{len(unique_lines)}] {line}")
        translations[line] = translate_line(client, line, args.lang)

    song_data = {
        "title":        args.title,
        "artist":       args.artist,
        "targetLang":   args.lang,
        "strophes":     strophes,
        "translations": translations,
    }

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(song_data, f, ensure_ascii=False, indent=2)

    print(f"\n✓ Saved to {args.out}")
    print(f"  Import this file in Español Trainer → Import")


if __name__ == "__main__":
    main()
