#!/usr/bin/with-contenv bash
set -e
CFG=/data/options.json
export LIGHTRAG_API_KEY="$(jq -r '.service_api_key' $CFG)"
export OLLAMA_API_KEY="$(jq -r '.ollama_cloud_key' $CFG)"
export OLLAMA_HOST="https://ollama.com"
export LLM_MODEL="$(jq -r '.llm_model' $CFG)"
export WORKING_DIR="/share/bkon_lightrag/rag_storage"
mkdir -p "$WORKING_DIR"
echo "BKON LightRAG: local embeddings + Ollama Cloud ($LLM_MODEL)"
exec uvicorn server:app --host 0.0.0.0 --port 9621
