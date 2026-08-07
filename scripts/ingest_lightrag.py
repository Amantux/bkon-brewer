#!/usr/bin/env python3
"""Feed the BKON document passages into a running LightRAG server.

    python3 scripts/ingest_lightrag.py \
        --kb /config/bkon_brewer_kb.json \
        --url http://homeassistant.local:9621 \
        --key YOUR_API_KEY

Uses the same local index build_kb.py produces, so there is one source of
document text and LightRAG is fed from it rather than re-parsing PDFs. Insertion
is one document at a time with the source name attached, so LightRAG's graph
keeps the provenance the local retriever already tracks.

Only sends text you already hold locally to a server you run locally. Nothing
leaves the network; the API key is the one you set on the server.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict


def post(url: str, key: str, path: str, payload: dict) -> tuple[int, str]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url.rstrip("/") + path, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    if key:
        req.add_header("X-API-Key", key)
        req.add_header("Authorization", f"Bearer {key}")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")[:200]
    except urllib.error.HTTPError as ex:
        return ex.code, ex.read().decode("utf-8", "replace")[:200]
    except Exception as ex:                          # noqa: BLE001
        return 0, str(ex)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--kb", default="bkon_brewer_kb.json")
    ap.add_argument("--url", required=True)
    ap.add_argument("--key", default="")
    args = ap.parse_args()

    data = json.loads(open(args.kb, encoding="utf-8").read())
    passages = data.get("passages", [])
    if not passages:
        print("No passages in the index. Build it with build_kb.py first.")
        return 1

    # Group passages back into whole documents: LightRAG builds a better graph
    # from a coherent document than from a shower of disconnected fragments.
    by_doc: dict[str, list[str]] = defaultdict(list)
    for p in passages:
        by_doc[p["doc"]].append(p["text"])

    status, _ = post(args.url, args.key, "/health", {})
    print(f"{len(by_doc)} documents to ingest into {args.url}\n")

    ok = 0
    for i, (doc, chunks) in enumerate(sorted(by_doc.items()), 1):
        text = f"# {doc}\n\n" + "\n\n".join(chunks)
        code, msg = post(args.url, args.key, "/documents/text",
                         {"text": text, "description": doc})
        mark = "ok " if 200 <= code < 300 else "ERR"
        print(f"  [{i:>2}/{len(by_doc)}] {mark} {code}  {doc}")
        if 200 <= code < 300:
            ok += 1
        elif code in (401, 403):
            print("  -> API key rejected. Check --key matches the server.")
            return 2
        time.sleep(0.3)          # let a Pi keep up with embedding each insert

    print(f"\nIngested {ok}/{len(by_doc)} documents. LightRAG is indexing them "
          f"in the background; large graphs take a few minutes to finish.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
