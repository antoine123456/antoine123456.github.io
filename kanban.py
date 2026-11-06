#!/usr/bin/env python3
"""
kanban.py — idee.md en tableau Kanban (#129).

Lit idee.md et écrit kanban.html (ignoré par git), à ouvrir dans le
navigateur :
  À trier   les entrées de « Pending » (dont les [ui])
  À faire   [ ]      En cours   [_]      Fait   [X]
Chaque carte garde sa section (Idée / Correction), son groupe (« conjugaison: »,
« rendu complet : »…), ses sous-lignes, et ses issues #N avec leur état
GitHub (via `gh`, si disponible ; sinon de simples liens).

Usage :
    python3 kanban.py            génère et ouvre kanban.html
    python3 kanban.py --watch    regénère à chaque modification de idee.md
                                 (la page se recharge toute seule)
"""
import html
import json
import os
import re
import subprocess
import sys
import time
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "idee.md")
OUT = os.path.join(HERE, "kanban.html")
REPO = "antoine123456/antoine123456.github.io"
COLUMNS = [("pending", "À trier"), ("todo", "À faire"), ("doing", "En cours"), ("done", "Fait")]
MARKS = {" ": "todo", "_": "doing", "x": "done", "X": "done"}


def parse(text):
    cards, section, group, card, last = [], None, None, None, None
    for line in text.splitlines():
        if line.startswith("## "):
            section, group, card, last = line[3:].strip(), None, None, None
            continue
        if section in (None, "Règles") or not line.strip():
            if not line.strip():
                card = group = None
            continue
        m = re.match(r"^- (?:\[(.{1,3})\]\s*)?(.*)$", line)
        if m and m.group(1) is None and section != "Pending" and last:
            last["notes"].append(m.group(2))  # « - Estoy aprendiendo » : brainstorm under an idea
        elif m:
            mark, body = m.group(1), m.group(2)
            if section == "Pending":
                col = "pending"
            elif mark in MARKS:
                col = MARKS[mark]
            elif mark is None:
                col = "todo"
            else:
                col = "pending"
            tag = mark if mark and mark not in MARKS else None
            # « @v1 », « @volet1 »… : the GitHub milestone of the issue (#129)
            ms = re.findall(r"(?<!\S)@([\w-]+)", body)
            body = re.sub(r"\s*(?<!\S)@[\w-]+", "", body).strip()
            card = {"col": col, "section": section, "group": group, "tag": tag, "ms": ms, "text": body, "notes": []}
            cards.append(card)
            last = card
        elif line.startswith((" ", "\t")) and card:
            card["notes"].append(line.strip().lstrip("- "))
        elif re.match(r"^[^-].*:\s*$", line):
            group, card = line.strip().rstrip(":").strip(), None
        elif card:
            card["notes"].append(line.strip())
    return cards


def issue_states():
    try:
        out = subprocess.run(["gh", "issue", "list", "--repo", REPO, "--state", "all", "--limit", "1000",
                              "--json", "number,state,title"], capture_output=True, text=True, timeout=30)
        return {str(i["number"]): i for i in json.loads(out.stdout)}
    except Exception:
        return {}


def render(cards, issues):
    def chips(text):
        out = []
        for n in dict.fromkeys(re.findall(r"#(\d+)", text)):
            i = issues.get(n, {})
            st = i.get("state", "").lower()
            out.append(f'<a class="iss {st}" href="https://github.com/{REPO}/issues/{n}" target="_blank" '
                       f'title="{html.escape(i.get("title", ""))}">#{n}{" ✓" if st == "closed" else ""}</a>')
        return "".join(out)

    def card_html(c):
        kind = "corr" if c["section"] == "Correction" else "idea"
        label = {"corr": "Correction", "idea": "Idée"}[kind] if c["section"] != "Pending" else "à classer"
        badges = f'<span class="b {kind if c["section"] != "Pending" else "pend"}">{label}</span>'
        if c["tag"]:
            badges += f'<span class="b tag">{html.escape(c["tag"])}</span>'
        for m in c["ms"]:
            badges += f'<span class="b ms">{html.escape(m)}</span>'
        if c["group"]:
            badges += f'<span class="b grp">{html.escape(c["group"])}</span>'
        text = re.sub(r"\s*\((#\d+[^)]*)\)\s*$", r" <span class=detail>(\1)</span>", html.escape(c["text"]))
        notes = "".join(f"<li>{html.escape(n)}</li>" for n in c["notes"] if n)
        allt = c["text"] + " " + " ".join(c["notes"])
        return (f'<div class="card {kind}" data-q="{html.escape(allt.lower())}" data-kind="{kind}" data-ms="{" ".join(c["ms"])}">'
                f'<div class="badges">{badges}</div><div class="txt">{text}</div>'
                + (f'<details><summary>{len(c["notes"])} note(s)</summary><ul>{notes}</ul></details>' if notes else "")
                + f'<div class="chips">{chips(allt)}</div></div>')

    cols = []
    for key, name in COLUMNS:
        cs = [c for c in cards if c["col"] == key]
        cols.append(f'<section class="col" data-col="{key}"><h2>{name} <span class="n">{len(cs)}</span></h2>'
                    + "".join(card_html(c) for c in cs) + "</section>")
    stamp = time.strftime("%d/%m %H:%M")
    tags = sorted({m for c in cards for m in c["ms"]})
    msb = "".join(f'<button data-m="{html.escape(m)}">{html.escape(m)}</button>' for m in tags)
    return PAGE.replace("{{MS}}", msb).replace("{{COLS}}", "".join(cols)).replace("{{STAMP}}", stamp)


PAGE = """<!doctype html><html lang=fr><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>Kanban des idées</title>
<style>
:root{--bg:#f4f3ef;--col:#e9e7e1;--card:#fff;--ink:#222;--mute:#777;--idea:#2f6fdb;--corr:#d9473b;--pend:#a77d00;--done:#2e9b57}
@media (prefers-color-scheme:dark){:root{--bg:#17181a;--col:#212327;--card:#2b2e33;--ink:#e8e8e8;--mute:#999}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.4 -apple-system,system-ui,sans-serif}
header{display:flex;gap:10px;align-items:center;flex-wrap:wrap;padding:12px 16px;position:sticky;top:0;background:var(--bg);z-index:2}
h1{font-size:17px;margin:0 8px 0 0}input{flex:1;min-width:160px;padding:6px 10px;border-radius:8px;border:1px solid #8885;background:var(--card);color:var(--ink)}
button{border:1px solid #8885;background:var(--card);color:var(--ink);border-radius:999px;padding:4px 11px;cursor:pointer}
button.on{background:var(--ink);color:var(--bg)}.stamp{color:var(--mute);font-size:12px}
main{display:grid;grid-template-columns:repeat(4,minmax(240px,1fr));gap:12px;padding:0 16px 24px;overflow-x:auto}
.col{background:var(--col);border-radius:12px;padding:10px;min-height:120px}
.col h2{font-size:13px;text-transform:uppercase;letter-spacing:.6px;margin:2px 4px 10px;color:var(--mute)}
.n{background:#8883;border-radius:999px;padding:0 7px;margin-left:4px}
.card{background:var(--card);border-radius:9px;padding:9px 10px;margin-bottom:8px;border-left:4px solid var(--idea);box-shadow:0 1px 2px #0001}
.card.corr{border-left-color:var(--corr)}.col[data-col=pending] .card{border-left-color:var(--pend)}
.col[data-col=done] .card{opacity:.72}
.badges{display:flex;gap:4px;flex-wrap:wrap;margin-bottom:4px}
.b{font-size:10.5px;border-radius:5px;padding:1px 6px;background:#8882}.b.idea{color:var(--idea)}.b.corr{color:var(--corr)}.b.pend{color:var(--pend)}
.b.tag{background:var(--pend);color:#fff}.b.ms{background:#2e9b5722;color:var(--done);font-weight:600}.sep{width:1px;height:20px;background:#8885}.b.grp{color:var(--mute)}
.detail{color:var(--mute);font-size:12.5px}details{font-size:12.5px;color:var(--mute);margin-top:4px}details ul{margin:4px 0;padding-left:18px}
.chips{display:flex;gap:4px;flex-wrap:wrap;margin-top:5px}.iss{font-size:11.5px;text-decoration:none;border-radius:999px;padding:0 7px;border:1px solid var(--idea);color:var(--idea)}
.iss.closed{border-color:var(--done);color:var(--done)}
.hide{display:none}
@media (max-width:700px){main{grid-template-columns:1fr}}
</style>
<header><h1>Kanban des idées</h1><input id=q placeholder="Filtrer…">
<button data-k=all class=on>Tout</button><button data-k=idea>Idées</button><button data-k=corr>Corrections</button>
<span class=sep></span><button data-m="" class=on>tous</button>{{MS}}<span class=sep></span><button id=hd>Masquer « Fait »</button><span class=stamp>idee.md · {{STAMP}}</span></header>
<main>{{COLS}}</main>
<script>
// Filters survive the reloads of --watch.
var kind="all",ms="",hideDone=false;try{hideDone=localStorage.kbHide==="1";kind=localStorage.kbKind||"all";ms=localStorage.kbMs||"";
document.querySelectorAll("[data-m]").forEach(function(x){x.classList.toggle("on",x.dataset.m===ms)});document.getElementById("q").value=localStorage.kbQ||"";
document.querySelectorAll("[data-k]").forEach(function(x){x.classList.toggle("on",x.dataset.k===kind)})}catch(e){}
function apply(){var q=document.getElementById("q").value.toLowerCase();try{localStorage.kbQ=q;localStorage.kbKind=kind;localStorage.kbMs=ms}catch(e){}
document.querySelectorAll(".card").forEach(function(c){c.classList.toggle("hide",(q&&c.dataset.q.indexOf(q)<0)||(kind!=="all"&&c.dataset.kind!==kind)||(ms&&(" "+c.dataset.ms+" ").indexOf(" "+ms+" ")<0))});
document.querySelector("[data-col=done]").classList.toggle("hide",hideDone);document.getElementById("hd").classList.toggle("on",hideDone);
document.querySelector("main").style.gridTemplateColumns=hideDone?"repeat(3,minmax(240px,1fr))":"";}
document.getElementById("q").oninput=apply;
document.querySelectorAll("[data-k]").forEach(function(b){b.onclick=function(){kind=b.dataset.k;document.querySelectorAll("[data-k]").forEach(function(x){x.classList.toggle("on",x===b)});apply()}});
document.querySelectorAll("[data-m]").forEach(function(b){b.onclick=function(){ms=b.dataset.m;document.querySelectorAll("[data-m]").forEach(function(x){x.classList.toggle("on",x===b)});apply()}});
document.getElementById("hd").onclick=function(){hideDone=!hideDone;try{localStorage.kbHide=hideDone?"1":"0"}catch(e){}apply()};
apply();
// --watch : kanban.py rewrites this file when idee.md changes; reload then.
if(location.search.indexOf("watch")>=0)setInterval(function(){location.reload()},4000);
</script></html>
"""


def build():
    with open(SRC, encoding="utf-8") as f:
        cards = parse(f.read())
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(render(cards, issue_states()))
    return cards


def main():
    cards = build()
    counts = {k: sum(1 for c in cards if c["col"] == k) for k, _ in COLUMNS}
    print(f"kanban.html : " + " · ".join(f"{n} {counts[k]}" for k, n in COLUMNS))
    watch = "--watch" in sys.argv
    if "--no-open" not in sys.argv:
        webbrowser.open("file://" + OUT + ("?watch" if watch else ""))
    if watch:
        last = os.path.getmtime(SRC)
        while True:
            time.sleep(1.5)
            m = os.path.getmtime(SRC)
            if m != last:
                last = m
                build()
                print(time.strftime("%H:%M:%S"), "regénéré")


if __name__ == "__main__":
    main()
