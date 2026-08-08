#!/usr/bin/env sh
# BKON LightRAG add-on entrypoint. Reads the add-on options into the namespaced
# env the provider layer expects (providers/config.py), then execs uvicorn.
#
# Booleans/coercion are not a risk here — every option is a string or an enum,
# and the provider layer validates them (unknown provider, missing key/model,
# and an SSRF-guarded base URL all fail loudly at startup rather than serving a
# half-working service).
set -e
CFG=/data/options.json

export LIGHTRAG_API_KEY="$(jq -r '.service_api_key // ""' "$CFG")"
export LOG_LEVEL="$(jq -r '.log_level // "INFO"' "$CFG")"

# Pluggable generation provider, namespaced so one vendor's key is never read by
# another (the edibl chat-and-providers pattern).
PROVIDER="$(jq -r '.ai_provider // "ollama"' "$CFG")"
export AI_PROVIDER="$PROVIDER"
UP="$(echo "$PROVIDER" | tr '[:lower:]' '[:upper:]')"
export "${UP}_MODEL=$(jq -r '.model // ""' "$CFG")"
export "${UP}_API_KEY=$(jq -r '.api_key // ""' "$CFG")"
BASE="$(jq -r '.base_url // ""' "$CFG")"
[ -n "$BASE" ] && export "${UP}_BASE_URL=$BASE"
# Ollama with no base URL means Ollama Cloud.
[ "$PROVIDER" = "ollama" ] && [ -z "$BASE" ] && export OLLAMA_BASE_URL="https://ollama.com"

# Storage persists on the /share mount so it survives add-on updates.
export WORKING_DIR="/share/bkon_lightrag/rag_storage"
mkdir -p "$WORKING_DIR"

echo "BKON LightRAG: local embeddings + provider=$PROVIDER (ingress + LAN on 9621)"
exec uvicorn server:app --host 0.0.0.0 --port 9621 \
  --log-level "$(echo "$LOG_LEVEL" | tr '[:upper:]' '[:lower:]')"
