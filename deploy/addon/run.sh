#!/usr/bin/with-contenv bash
# Read add-on options and start the LightRAG server against Ollama.
set -e
CONFIG=/data/options.json
export LIGHTRAG_API_KEY="$(jq -r '.api_key' $CONFIG)"
OLLAMA="$(jq -r '.ollama_url' $CONFIG)"

export LLM_BINDING="ollama"
export LLM_BINDING_HOST="$OLLAMA"
export LLM_MODEL="$(jq -r '.llm_model' $CONFIG)"
export EMBEDDING_BINDING="ollama"
export EMBEDDING_BINDING_HOST="$OLLAMA"
export EMBEDDING_MODEL="$(jq -r '.embedding_model' $CONFIG)"
export EMBEDDING_DIM="$(jq -r '.embedding_dim' $CONFIG)"
export WORKING_DIR="/share/bkon_lightrag/rag_storage"
export INPUT_DIR="/share/bkon_lightrag/inputs"
mkdir -p "$WORKING_DIR" "$INPUT_DIR"

echo "BKON LightRAG -> Ollama at $OLLAMA (llm=$LLM_MODEL, embed=$EMBEDDING_MODEL)"
exec lightrag-server --host 0.0.0.0 --port 9621
