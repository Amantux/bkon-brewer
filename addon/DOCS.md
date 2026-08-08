# BKON LightRAG

Graph-retrieval service for the BKON Brewer concierge. It answers questions from
the brewer's service documents by combining a local embedding model with a
generation model you choose. Embeddings run **locally** (bundled, CPU); only the
prompt for each question leaves the network, to the provider you configure.

This add-on is optional. Without it, the BKON integration answers questions with
its built-in keyword retriever — this upgrades those answers to semantic,
written responses, and the integration falls back automatically if the service
is down.

## Supported hardware

Prebuilt images are published for every architecture Home Assistant OS runs on,
so installing pulls a ready image rather than compiling the embedding runtime
(onnxruntime / fastembed) on the device — which on a Pi-class board would be
slow and fragile.

| Board | Architecture | Image |
|---|---|---|
| **Home Assistant Yellow** (CM4) | aarch64 | `bkon-lightrag-aarch64` |
| Home Assistant Green, Raspberry Pi 4 / 5, CM5 | aarch64 | `bkon-lightrag-aarch64` |
| Home Assistant OS on x86 / NUC / VM | amd64 | `bkon-lightrag-amd64` |

## Setup

1. **Install and configure** this add-on:
   - **Service API key** — a secret of your choosing; set the same value in the
     BKON integration's options.
   - **Generation provider** — `ollama`, `anthropic`, or `openai`.
   - **Model** — e.g. `gpt-oss:120b` (Ollama Cloud) or `claude-sonnet-5`.
   - **Provider API key** — your Ollama Cloud / Anthropic / OpenAI key.
   - **Base URL** — leave blank for the vendor default; point at
     `http://host:11434` for a local Ollama.

2. **Start it.** The status page appears in the sidebar (BKON RAG). First start
   downloads the small embedding model; after that it is offline for embeddings.

3. **Feed it the documents** (from the integration repo):
   ```
   python3 scripts/ingest_lightrag.py --kb bkon_brewer_kb.json \
       --url http://homeassistant.local:9621 --key YOUR_SERVICE_KEY
   ```

4. **Point the integration at it** — Settings → Devices & Services → BKON →
   Configure: the LightRAG URL (`http://homeassistant.local:9621`) and the
   service API key.

## Ports

- **Ingress** serves the status page through Home Assistant's authenticated
  proxy — no port to expose.
- **9621/tcp** is the API. Map it only so the integration (or another LAN
  client) can reach it directly; it is guarded by the service API key.

## Privacy

Embeddings and retrieval are local. Generation runs on the provider you choose;
for a cloud provider, each question's prompt is a billed request. If the key is
wrong or the plan lapses, the integration falls back to its local retriever.
