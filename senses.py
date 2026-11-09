"""
senses.py — ce qu'on tape dans une réponse, et ce qu'on ne tape pas.

« il est; elle est; c'est (permanent) » :
  - words : les mots à taper            ["il", "est", "elle", "est", "c'est"]
  - sep   : où commence chaque sens       [2, 4]      → « / » entre les cases (#154)
  - notes : précisions entre parenthèses  {"4": "(permanent)"} → en gris après
            le mot n° 4, pas à taper (#173) ; "-1" = avant la première case.
Un sens qui n'est fait que d'une parenthèse (« (volume) ») reste à taper.
"""
import re

PUNCT_EDGES = re.compile(r"^[^\w]+|[^\w]+$")


def _tokens(text):
    return [t for t in (PUNCT_EDGES.sub("", x) for x in text.split()) if t and any(ch.isalnum() for ch in t)]


def split_answer(text, senses=True):
    """(words, sep, notes) d'un texte de réponse ; senses=False : un seul sens."""
    words, sep, notes = [], [], {}
    parts = [p for p in (text.split(";") if senses else [text]) if p.strip()]
    for p in parts:
        chunks = re.split(r"(\([^)]*\))", p)
        plain = [c for c in chunks if not c.startswith("(")]
        if not _tokens(" ".join(plain)):  # « (volume) » alone: typed
            chunks = [p.replace("(", " ").replace(")", " ")]
        start = len(words)
        if words and _tokens(" ".join(chunks)):
            sep.append(start)
        for c in chunks:
            if c.startswith("(") and c.endswith(")"):
                k = str(len(words) - 1)
                notes[k] = (notes[k] + " " if k in notes else "") + c.strip()
            else:
                words += _tokens(c)
    return words, sep, notes
