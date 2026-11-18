#!/usr/bin/env python3
"""
tags_snippets.py — the tags of the « ## Tags » table of idee.md, offered as
you type in the project's Markdown files (VS Code snippets).

The table, in idee.md (one line per tag, add a line to create one):

    ## Tags

    | tag | description |
    |---|---|
    | @v1 | version 1 : l'app actuelle |

writes .vscode/markdown.code-snippets: typing « @v » (or « v1 ») in a
Markdown file then offers @v1 with its description. No Claude, no package:
run it from VS Code — F1 → « Tasks: Run Task » → « Tags → snippets » — or:

    python3 tags_snippets.py [idee.md]

It also lists the tags used in the file but missing from the table.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
ROW = re.compile(r"^\|\s*(@[\w\-À-ÿ]+)\s*\|\s*(.*?)\s*\|\s*$")
USED = re.compile(r"(?<![\w@])@([\w\-À-ÿ]+)")


def read_tags(lines):
    """[(tag, description)] from the « ## Tags » section's table."""
    tags, inside = [], False
    for line in lines:
        if line.startswith("## "):
            inside = line[3:].strip().lower() == "tags"
            continue
        m = inside and ROW.match(line.strip())
        if m:
            tags.append((m.group(1), m.group(2)))
    return tags


def main():
    src = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "idee.md"))
    lines = open(src, encoding="utf-8").read().splitlines()
    tags = read_tags(lines)
    if not tags:
        sys.exit("Pas de tableau sous « ## Tags » dans %s" % src)
    snippets = {t: {"scope": "markdown", "prefix": [t, t[1:]], "body": t + "$0", "description": d}
                for t, d in tags}
    out = os.path.join(os.path.dirname(src), ".vscode", "markdown.code-snippets")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write("// written by tags_snippets.py from the « ## Tags » table of %s — edit the table, not this file\n"
                % os.path.basename(src))
        json.dump(snippets, f, ensure_ascii=False, indent=2)
    print("%d tags → %s" % (len(tags), os.path.relpath(out)))
    known = {t for t, _ in tags}
    body = "\n".join(l for l in lines if not ROW.match(l.strip()))
    missing = sorted({"@" + t for t in USED.findall(body)} - known)
    if missing:
        print("utilisés mais pas dans le tableau : " + " ".join(missing))


if __name__ == "__main__":
    main()
