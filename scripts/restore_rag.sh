#!/bin/sh
# Restore the prebuilt document index — no PDF re-extraction, no model calls.
#
#     GITHUB_TOKEN=ghp_xxx ./scripts/restore_rag.sh
#
# The index is 578 passages from 45 BKON/Franke service documents. It is
# **derived from copyrighted material**, so it lives on a release of the private
# Amantux/bkon-archive rather than in this repository — which is public, and
# says in its README that no vendor document text is in it. Keeping that true is
# why this is a download rather than a checked-in file.
#
# What it restores:
#   * the local keyword retriever the integration uses  -> $KB_DEST
#   * the same index uploaded to the add-on for citations (if it is reachable)
#
# The LightRAG graph itself is not stored: it is rebuilt from this index by
# scripts/ingest_lightrag.py, which is the only step that needs a model.
set -e

REPO="${REPO:-Amantux/bkon-archive}"
TAG="${TAG:-rag-index-v1}"
ASSET="${ASSET:-bkon_brewer_kb.json.gz}"
KB_DEST="${KB_DEST:-/config/bkon_brewer_kb.json}"
ADDON_URL="${ADDON_URL:-}"

if [ -z "$GITHUB_TOKEN" ]; then
  echo "Set GITHUB_TOKEN to a token that can read $REPO (it is private)." >&2
  exit 1
fi

api="https://api.github.com/repos/$REPO/releases/tags/$TAG"
id=$(curl -sSfL -H "Authorization: Bearer $GITHUB_TOKEN" "$api" \
     | python3 -c "import json,sys;a=[x for x in json.load(sys.stdin)['assets'] if x['name']=='$ASSET'];print(a[0]['id'] if a else '')")
[ -n "$id" ] || { echo "Asset $ASSET not found on $REPO@$TAG" >&2; exit 1; }

tmp=$(mktemp -d)
curl -sSfL -H "Authorization: Bearer $GITHUB_TOKEN" -H "Accept: application/octet-stream" \
  "https://api.github.com/repos/$REPO/releases/assets/$id" -o "$tmp/kb.json.gz"
gunzip -c "$tmp/kb.json.gz" > "$tmp/kb.json"

python3 - "$tmp/kb.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
p = d.get("passages", [])
assert p, "the index is empty"
print(f"  {len(p)} passages from {len({x['doc'] for x in p})} documents")
PY

mkdir -p "$(dirname "$KB_DEST")"
cp "$tmp/kb.json" "$KB_DEST"
echo "  restored -> $KB_DEST"

if [ -n "$ADDON_URL" ]; then
  code=$(curl -sS -o /dev/null -w '%{http_code}' -X POST "$ADDON_URL/documents/index" \
    -H "Content-Type: application/json" --data-binary @"$tmp/kb.json")
  echo "  uploaded to the add-on for citations: HTTP $code"
fi

rm -rf "$tmp"
echo
echo "Done. Restart Home Assistant (or reload the integration) to pick it up."
echo "For semantic answers, feed LightRAG once:  python3 scripts/ingest_lightrag.py \\"
echo "    --kb $KB_DEST --url http://<host>:9621"
