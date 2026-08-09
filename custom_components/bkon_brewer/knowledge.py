"""Local knowledge base over the BKON service documents.

Answers questions from the manuals the owner archived for their own machine.
The document text is NOT part of this integration -- it is indexed into a local
data file on the owner's own system (see scripts/build_kb.py) and read at
runtime. Nothing here redistributes Franke's documentation; it retrieves from a
private index the owner built from documents they hold.

Retrieval is a small TF-IDF cosine ranker in pure Python -- no model, no
dependency, no network. For a few hundred passages that is more than enough, and
it keeps the whole thing inspectable: you can see exactly why a passage was
returned. The ranking logic is pure and testable; only loading the index touches
disk.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

_WORD = re.compile(r"[a-z0-9]+")

# Words too common to help ranking. Kept short on purpose -- an aggressive stop
# list throws away the domain terms ("water", "time") that actually matter here.
_STOP = frozenset(
    "the a an and or of to in on for is are be with at as by it this that "
    "your you from can will if when how what which".split())


def _stem(w: str) -> str:
    """Crude, consistent stemmer. Linguistic accuracy is not the goal -- applying
    the SAME reduction to query and document is, so that "descale", "descaling"
    and "descaler" all land on one token and match each other.
    """
    for suf, keep in (("ing", 4), ("edly", 4), (" ed", 4), ("er", 4),
                      ("es", 3), ("ed", 4)):
        suf = suf.strip()
        if len(w) > keep and w.endswith(suf):
            w = w[: -len(suf)]
            break
    else:
        if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
    if len(w) > 4 and w.endswith("e"):
        w = w[:-1]
    return w


def _tokens(text: str) -> list[str]:
    return [_stem(w) for w in _WORD.findall(text.lower())
            if w not in _STOP and len(w) > 1]


@dataclass(slots=True)
class Passage:
    doc: str
    page: int
    text: str
    #: Where to go to see the source, when there is somewhere to go. A video
    #: links out; a PDF is served from the device once its originals have been
    #: uploaded. Empty for everything else.
    url: str = ""
    #: A described picture, rather than text lifted off the page. Most of this
    #: corpus is diagrams and screenshots, so a figure's description is indexed
    #: alongside the prose and ranked against it -- "where does the drain line
    #: connect?" should be able to match a schematic. `figure` is the id to
    #: fetch it by.
    kind: str = ""
    figure: str = ""


@dataclass(slots=True)
class Hit:
    passage: Passage
    score: float


class KnowledgeBase:
    """A searchable index of document passages."""

    def __init__(self, passages: list[Passage]) -> None:
        self._passages = passages
        self._tf: list[dict[str, float]] = []
        self._idf: dict[str, float] = {}
        self._build()

    @classmethod
    def from_file(cls, path: str | Path) -> "KnowledgeBase":
        """Load an index built by scripts/build_kb.py. Empty if absent.

        A missing index is not an error -- it just means the owner has not built
        one yet, and the agent should say so plainly rather than fail. This is
        the only method here that touches disk.
        """
        p = Path(path)
        if not p.exists():
            return cls([])
        data = json.loads(p.read_text(encoding="utf-8"))
        return cls([Passage(d["doc"], int(d.get("page", 0)), d["text"],
                            d.get("url", ""), d.get("kind", ""),
                            d.get("figure", ""))
                    for d in data.get("passages", [])])

    @property
    def ready(self) -> bool:
        return bool(self._passages)

    @property
    def size(self) -> int:
        return len(self._passages)

    @property
    def documents(self) -> list[str]:
        return sorted({p.doc for p in self._passages})

    def _build(self) -> None:
        n = len(self._passages)
        df: dict[str, int] = {}
        for p in self._passages:
            counts: dict[str, float] = {}
            toks = _tokens(p.text)
            for t in toks:
                counts[t] = counts.get(t, 0) + 1
            # Sub-linear term frequency: a passage that says "vacuum" ten times
            # is not ten times as much about vacuum.
            for t in counts:
                counts[t] = 1 + math.log(counts[t])
            self._tf.append(counts)
            for t in set(toks):
                df[t] = df.get(t, 0) + 1
        for t, d in df.items():
            self._idf[t] = math.log((1 + n) / (1 + d)) + 1

    def search(self, query: str, k: int = 3) -> list[Hit]:
        """Top-k passages for a query, best first. Empty when nothing matches.

        Scores by TF-IDF cosine. Below a small floor a passage is dropped rather
        than returned as a weak best guess -- answering "I don't have anything
        on that" is better than surfacing an irrelevant paragraph with
        confidence.
        """
        q = _tokens(query)
        if not q or not self._passages:
            return []
        qv: dict[str, float] = {}
        for t in q:
            qv[t] = qv.get(t, 0) + 1
        for t in qv:
            qv[t] = (1 + math.log(qv[t])) * self._idf.get(t, 0.0)
        qnorm = math.sqrt(sum(v * v for v in qv.values())) or 1.0

        hits: list[Hit] = []
        for passage, tf in zip(self._passages, self._tf):
            dot = 0.0
            dnorm = 0.0
            for t, w in tf.items():
                wi = w * self._idf.get(t, 0.0)
                dnorm += wi * wi
                if t in qv:
                    dot += wi * qv[t]
            if dot <= 0:
                continue
            score = dot / (qnorm * (math.sqrt(dnorm) or 1.0))
            hits.append(Hit(passage, score))

        hits.sort(key=lambda h: h.score, reverse=True)
        return [h for h in hits if h.score > 0.03][:k]

    def answer(self, query: str, k: int = 3) -> str:
        """A readable answer: the best passages, each attributed to its document.

        Deliberately quotes the manuals rather than paraphrasing them -- for a
        maintenance question the exact wording is the safe thing to relay, and
        the source is always named so the owner can open the document itself.
        """
        hits = self.search(query, k)
        if not hits:
            return ("I don't have anything on that in the BKON documents. Try "
                    "rephrasing, or ask about brewing, cleaning, descaling, "
                    "installation or error codes.")
        parts = []
        for h in hits:
            src = h.passage.doc
            if h.passage.page:
                src += f", p.{h.passage.page}"
            snippet = _trim(h.passage.text)
            parts.append(f"{snippet}\n  — {src}")
        return "\n\n".join(parts)


def _trim(text: str, limit: int = 480) -> str:
    """A focused snippet: collapse whitespace, cut on a sentence near the limit."""
    clean = re.sub(r"\s+", " ", text).strip()
    if len(clean) <= limit:
        return clean
    cut = clean[:limit]
    dot = cut.rfind(". ")
    return (cut[:dot + 1] if dot > limit * 0.5 else cut) + " …"
