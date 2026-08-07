# Semantic RAG with LightRAG + Ollama

The concierge answers questions two ways, and the second is an optional upgrade
over the first.

**Built-in (always on).** A TF-IDF retriever over the local index. No server, no
model, no configuration — it ships working and needs nothing. It matches on
words, so it is fast and explainable but literal: "the coffee tastes burnt" will
not find a passage about "over-extraction" unless the words overlap.

**LightRAG + Ollama (optional).** A graph RAG server that understands the
documents semantically and writes an answer with a local LLM, so looser phrasing
works and the reply reads like prose rather than a quoted paragraph. Everything
runs on your own hardware — Ollama serves the model, LightRAG does the retrieval,
and nothing leaves your network.

The upgrade can never be a downgrade: **every question falls back to the built-in
retriever** if the LightRAG server is slow, down, restarting, or misconfigured.
You get a less fluent answer, never an error.

## Standing it up

The models and server run as a sidecar — they cannot live inside Home
Assistant's core container. Two supported ways:

**On the Home Assistant host** — install the add-on in `deploy/addon/` as a
local add-on (copy it into your `/addons` share, then Settings → Add-ons → the
local repository). It runs the LightRAG server; point its `ollama_url` at an
Ollama you provide (a community Ollama add-on, or another machine).

**On any other box** — `deploy/docker-compose.yml` brings up Ollama and LightRAG
together:

```bash
cd deploy
LIGHTRAG_API_KEY=your-secret docker compose up -d
docker exec -it ollama ollama pull nomic-embed-text
docker exec -it ollama ollama pull qwen2.5:3b-instruct
```

### Models for a Raspberry Pi 5 / CM5 (aarch64, ~15 GB RAM)

| Role | Model | Why |
|---|---|---|
| Embeddings | `nomic-embed-text` | Small, CPU-fast, 768-dim |
| Generation | `qwen2.5:3b-instruct` or `llama3.2:3b` | Usable on CPU |

Drop generation to `qwen2.5:1.5b` if it is too slow; only go to 7B with a GPU.
Embedding is cheap; generation is the part a Pi feels.

## Feeding it the documents

Same local index the built-in retriever uses — one source of document text:

```bash
python3 scripts/build_kb.py /path/to/bkon-archive --out bkon_brewer_kb.json
python3 scripts/ingest_lightrag.py --kb bkon_brewer_kb.json \
    --url http://homeassistant.local:9621 --key your-secret
```

The document text is yours to index for your own machine; it is never committed
to this repository and never sent anywhere but your own server.

## Pointing the integration at it

Settings → Devices & Services → BKON → **Configure**:

- **LightRAG URL** — e.g. `http://homeassistant.local:9621`. Blank = built-in
  retriever only.
- **API key** — the `LIGHTRAG_API_KEY` you set on the server. Stored in the
  config entry, never in code.
- **Mode** — `hybrid` (graph + vector, the sensible default), or `local` /
  `global` / `mix` / `naive`.

Once set, `ask`, the `bkon_brewer.ask` service, and the Assist concierge all use
LightRAG, falling back to local automatically. Ask something and check the
`source` field of the response — `lightrag` or `local` — to see which answered.
