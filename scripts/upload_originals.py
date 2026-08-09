#!/usr/bin/env python3
"""Put the original documents on the device, so a citation can open the real thing.

    python3 scripts/upload_originals.py --dir ~/bkon-archive/files \\
        --url http://homeassistant.local:9621 --key YOUR_SERVICE_KEY

The add-on answers from an index of extracted text. That is enough to answer,
but not enough to *check* an answer -- for that you want the page itself, with
its diagrams and its exact wording. This uploads the originals so the "Open
original" link on a citation goes to the actual PDF, at the cited page.

The add-on stores them under /share, which belongs to root, so it has to be the
one to write them -- hence an upload rather than a copy. Files are matched to
documents by name: `Operation Manual.pdf` becomes the original for the indexed
document `Operation Manual`. Anything that does not match an indexed document is
skipped and listed, because a file the index has never heard of cannot be cited
and silently uploading it would just waste space on the device.

Videos are matched by their yt-dlp `.info.json` title, since the archive names
them by video id: `gcDGZS0GJtA.mp4` is the original for `Video: BKON Coffee`.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

#: Only what the add-on will serve. Uploading anything else just fails at the
#: far end, so it is caught here where the message can name the file.
SERVABLE = {".pdf", ".mp4", ".png", ".jpg", ".jpeg", ".txt"}


def api(url: str, path: str, key: str, data: bytes | None = None,
        query: dict | None = None) -> dict:
    full = url.rstrip("/") + path
    if query:
        full += "?" + urllib.parse.urlencode(query)
    req = urllib.request.Request(full, data=data,
                                 method="POST" if data is not None else "GET")
    if key:
        req.add_header("X-API-Key", key)
    if data is not None:
        req.add_header("Content-Type", "application/octet-stream")
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.load(resp)


def video_titles(root: Path) -> dict[str, Path]:
    """`Video: <title>` -> mp4, read from yt-dlp's own sidecar metadata."""
    out: dict[str, Path] = {}
    for info in root.rglob("*.info.json"):
        try:
            title = (json.loads(info.read_text()).get("title") or "").strip()
        except (OSError, ValueError):
            continue
        mp4 = info.with_suffix("").with_suffix(".mp4")
        if title and mp4.is_file():
            out[f"Video: {title}"] = mp4
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", required=True, type=Path,
                    help="the archive directory (searched recursively)")
    ap.add_argument("--url", default="http://homeassistant.local:9621")
    ap.add_argument("--key", default="", help="the add-on's service API key")
    ap.add_argument("--dry-run", action="store_true",
                    help="show what would be uploaded and stop")
    ap.add_argument("--prune", action="store_true",
                    help="also remove stored originals for documents that are "
                         "no longer in the index")
    args = ap.parse_args()

    if not args.dir.is_dir():
        print(f"not a directory: {args.dir}", file=sys.stderr)
        return 2

    try:
        indexed = set(api(args.url, "/documents", args.key)["documents"])
    except (urllib.error.URLError, OSError, KeyError, ValueError) as ex:
        print(f"could not reach the add-on at {args.url}: {ex}", file=sys.stderr)
        return 2
    if not indexed:
        print("the add-on has no document index yet — run ingest first, "
              "or there is nothing for these files to be the originals of.",
              file=sys.stderr)
        return 2

    # Plain files first, then videos, so a real file wins over a title match.
    found: dict[str, Path] = {}
    for f in sorted(args.dir.rglob("*")):
        if f.is_file() and f.suffix.lower() in SERVABLE and f.stem in indexed:
            found[f.stem] = f
    for doc, mp4 in video_titles(args.dir).items():
        if doc in indexed:
            found.setdefault(doc, mp4)

    missing = sorted(indexed - set(found))
    print(f"{len(found)} of {len(indexed)} indexed documents have an original here")
    if missing:
        print("no original found for:")
        for m in missing:
            print(f"  {m}")
    if args.dry_run:
        return 0
    if not found:
        return 1

    if args.prune:
        stored = set(api(args.url, "/documents", args.key).get("originals") or [])
        for doc in sorted(stored - indexed):
            req = urllib.request.Request(
                args.url.rstrip("/") + "/documents/original?"
                + urllib.parse.urlencode({"doc": doc}), method="DELETE")
            if args.key:
                req.add_header("X-API-Key", args.key)
            try:
                urllib.request.urlopen(req, timeout=60)
                print(f"  removed {doc} (no longer indexed)")
            except (urllib.error.URLError, OSError) as ex:
                print(f"  could not remove {doc}: {ex}", file=sys.stderr)

    ok = 0
    for doc, path in sorted(found.items()):
        try:
            api(args.url, "/documents/original", args.key, data=path.read_bytes(),
                query={"doc": doc, "filename": path.name})
        except (urllib.error.URLError, OSError, ValueError) as ex:
            print(f"  FAILED {doc}: {ex}", file=sys.stderr)
            continue
        ok += 1
        print(f"  {doc}  ({path.stat().st_size // 1024} KB)")

    print(f"\n{ok} uploaded. Citations will now link to the document itself.")
    return 0 if ok == len(found) else 1


if __name__ == "__main__":
    sys.exit(main())
