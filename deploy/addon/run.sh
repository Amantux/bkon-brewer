#!/usr/bin/with-contenv bash
set -e
CFG=/data/options.json
export LIGHTRAG_API_KEY="$(jq -r '.service_api_key' $CFG)"
# Pluggable provider (edibl chat-and-providers pattern). Namespaced env so a key
# for one vendor is never read by another. Ollama defaults to Cloud when no
# base_url is given.
PROVIDER="$(jq -r '.ai_provider' $CFG)"
export AI_PROVIDER="$PROVIDER"
UP="$(echo "$PROVIDER" | tr '[:lower:]' '[:upper:]')"
export ${UP}_MODEL="$(jq -r '.model' $CFG)"
export ${UP}_API_KEY="$(jq -r '.api_key' $CFG)"
BASE="$(jq -r '.base_url // empty' $CFG)"
[ -n "$BASE" ] && export ${UP}_BASE_URL="$BASE"
[ "$PROVIDER" = "ollama" ] && [ -z "$BASE" ] && export OLLAMA_BASE_URL="https://ollama.com"
export WORKING_DIR="/share/bkon_lightrag/rag_storage"
mkdir -p "$WORKING_DIR"
echo "BKON LightRAG: local embeddings + provider=$PROVIDER"
exec uvicorn server:app --host 0.0.0.0 --port 9621
