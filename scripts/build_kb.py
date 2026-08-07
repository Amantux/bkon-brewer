#!/usr/bin/env python3
"""Build the local knowledge-base index from BKON service documents.

Run this on your own machine, pointed at your own copy of the documents:

    python3 scripts/build_kb.py /path/to/bkon-archive \
        --out /config/bkon_brewer_kb.json

It extracts text, splits each document into passages, and writes a JSON index
the integration reads at runtime. The output is intentionally NOT committed and
is git-ignored: it contains Franke's document text, which is yours to index for
your own machine but not to redistribute. The integration ships the *retriever*,
you supply the *index*.

Needs `pypdf` (pip install pypdf). PDFs with no text layer (scanned diagrams)
are skipped with a note rather than silently dropped.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Passage sizing: long enough to be a self-contained answer, short enough that
# retrieval stays specific and a quoted snippet is a paragraph, not a page.
TARGET_CHARS = 700
MIN_CHARS = 120


def split_passages(text: str) -> list[str]:
    """Break a page into passages on blank lines, packing to a target size."""
    text = text.replace("\r", "")
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
    passages: list[str] = []
    buf = ""
    for b in blocks:
        b = re.sub(r"[ \t]+", " ", b)
        if len(buf) + len(b) + 1 <= TARGET_CHARS:
            buf = f"{buf}\n{b}".strip()
        else:
            if len(buf) >= MIN_CHARS:
                passages.append(buf)
            buf = b
            while len(buf) > TARGET_CHARS * 1.6:      # a single huge block
                passages.append(buf[:TARGET_CHARS])
                buf = buf[TARGET_CHARS:]
    if len(buf) >= MIN_CHARS:
        passages.append(buf)
    return passages


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("source", help="folder containing the BKON PDFs")
    ap.add_argument("--out", default="bkon_brewer_kb.json")
    args = ap.parse_args()

    try:
        import pypdf
    except ImportError:
        print("Needs pypdf:  pip install pypdf", file=sys.stderr)
        return 2

    import warnings
    warnings.filterwarnings("ignore")

    pdfs = sorted(Path(args.source).rglob("*.pdf"))
    if not pdfs:
        print(f"No PDFs found under {args.source}", file=sys.stderr)
        return 1

    passages: list[dict] = []
    skipped: list[str] = []
    for pdf in pdfs:
        doc = pdf.stem
        try:
            reader = pypdf.PdfReader(str(pdf))
        except Exception as ex:                        # noqa: BLE001
            skipped.append(f"{doc} ({ex})")
            continue
        doc_passages = 0
        for i, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            for p in split_passages(text):
                passages.append({"doc": doc, "page": i, "text": p})
                doc_passages += 1
        if doc_passages == 0:
            skipped.append(f"{doc} (no text layer)")

    Path(args.out).write_text(
        json.dumps({"passages": passages}, ensure_ascii=False),
        encoding="utf-8")

    docs = len({p["doc"] for p in passages})
    print(f"Indexed {len(passages)} passages from {docs} documents -> {args.out}")
    if skipped:
        print(f"Skipped {len(skipped)}: " + ", ".join(skipped))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
