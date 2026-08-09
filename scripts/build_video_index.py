#!/usr/bin/env python3
"""Index BKON training videos into the same passage index as the documents.

    python3 scripts/build_video_index.py /path/to/bkon-archive/videos \
        --merge bkon_brewer_kb.json --out bkon_brewer_kb.json

    # with transcripts (needs network, and yt-dlp installed):
    python3 scripts/build_video_index.py <dir> --captions --merge kb.json --out kb.json

Reads the `*.info.json` files yt-dlp writes alongside a download. Title and
description are always available locally; captions are not — YouTube serves them
from a URL, so fetching them is opt-in and needs a network round trip.

Each passage carries the video's `webpage_url`, so a citation to a video can
link out to it. Documents have no such link (the PDFs are not on the device and
are not ours to serve), which is exactly why the field is optional.

Output is the same index build_kb.py produces and is merged into it, so there is
one index and one retriever rather than a second path for video. Like that
index, it is derived from material that is not ours to redistribute: keep it
private and out of git.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys

MAX_CHARS = 900          # a passage; matches the document splitter's grain


def split(text: str) -> list[str]:
    """Break a blob into passages on sentence boundaries where possible."""
    text = re.sub(r"\s+", " ", (text or "")).strip()
    if not text:
        return []
    if len(text) <= MAX_CHARS:
        return [text]
    out, cur = [], ""
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if len(cur) + len(sentence) + 1 > MAX_CHARS and cur:
            out.append(cur.strip()); cur = ""
        cur += sentence + " "
    if cur.strip():
        out.append(cur.strip())
    return out


def captions_for(info: dict) -> str:
    """English captions, fetched from the URL yt-dlp recorded. Opt-in."""
    tracks = (info.get("automatic_captions") or {}).get("en") or []
    tracks += (info.get("subtitles") or {}).get("en") or []
    pick = next((t for t in tracks if t.get("ext") == "json3"), None)
    if not pick or not pick.get("url"):
        return ""
    try:
        import urllib.request
        with urllib.request.urlopen(pick["url"], timeout=20) as r:
            data = json.load(r)
    except Exception as ex:                          # noqa: BLE001
        print(f"    captions unavailable ({ex})", file=sys.stderr)
        return ""
    words = []
    for ev in data.get("events") or []:
        for seg in ev.get("segs") or []:
            w = seg.get("utf8", "")
            if w and w != "\n":
                words.append(w)
    return "".join(words).strip()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("videos", help="directory of *.info.json files")
    ap.add_argument("--out", default="bkon_brewer_kb.json")
    ap.add_argument("--merge", default="", help="an existing index to add to")
    ap.add_argument("--captions", action="store_true",
                    help="also fetch English captions (network)")
    args = ap.parse_args()

    passages: list[dict] = []
    if args.merge and os.path.exists(args.merge):
        passages = json.load(open(args.merge, encoding="utf-8")).get("passages", [])
        # Re-running should replace video passages, not pile up duplicates.
        passages = [p for p in passages if not p.get("url")]
        print(f"  merging into {len(passages)} document passages")

    files = sorted(glob.glob(os.path.join(args.videos, "*.info.json")))
    if not files:
        print(f"No *.info.json in {args.videos}", file=sys.stderr)
        return 1

    added = 0
    for f in files:
        try:
            info = json.load(open(f, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        title = (info.get("title") or os.path.basename(f)).strip()
        url = info.get("webpage_url") or ""
        doc = f"Video: {title}"

        chunks: list[str] = []
        desc = (info.get("description") or "").strip()
        if desc:
            chunks += split(desc)
        if args.captions:
            text = captions_for(info)
            if text:
                chunks += split(text)
                print(f"  {title}: +{len(split(text))} caption passages")
        if not chunks:
            print(f"  {title}: nothing to index", file=sys.stderr)
            continue
        for i, c in enumerate(chunks, 1):
            passages.append({"doc": doc, "page": i, "text": c, "url": url})
            added += 1
        print(f"  {title} -> {len(chunks)} passages")

    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump({"passages": passages}, fh)
    docs = len({p["doc"] for p in passages})
    print(f"\n{added} video passages added; {len(passages)} total across {docs} sources -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
