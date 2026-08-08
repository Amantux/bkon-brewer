# Semantic RAG: local embeddings + Ollama Cloud

The concierge answers questions two ways.

**Built-in (always on).** A TF-IDF retriever over the local index — no server,
no model, nothing to configure. It matches on words: fast and explainable, but
literal.

**LightRAG (optional upgrade).** A self-contained graph-RAG service that
understands the documents semantically and writes an answer with a large model.
The upgrade can never be a downgrade: **every question falls back to the
built-in retriever** if the service is unreachable.

## The architecture, and why it splits the way it does

One service (`addon/lightrag_service/`) does the whole job:

| Part | Where it runs | Why |
|---|---|---|
| **Embeddings** | **Local**, bundled (`fastembed`, ONNX, CPU) | Cheap, private, and needs no server — the model downloads once and runs forever. This is the "ship the embeddings complete" half. |
| **Generation** | **Pluggable** — Ollama (local/Cloud), Anthropic, or any OpenAI-compatible endpoint | A Pi cannot run a useful LLM; a cloud model can. Only the prompt leaves the network. Switching vendor is a config change. |
| **Orchestration** | Local (LightRAG) | Wires graph retrieval to generation. |

So retrieval is entirely local and self-contained; the cloud is used only for
the one thing a Pi genuinely can't do. Nothing about the documents is stored in
the cloud — only the prompt for each question is sent, to your own subscription.

## Choosing the model provider

Generation follows the same pluggable-provider pattern the sibling apps use
(Edibl / HomeHoard / myMeal): the service never imports a vendor SDK directly,
so selecting Ollama vs Anthropic vs an OpenAI-compatible endpoint is a config
change, and the unused SDKs need not be installed.

Set `ai_provider` (add-on) or `AI_PROVIDER` (compose), then the matching
namespaced fields — `<PROVIDER>_MODEL`, `<PROVIDER>_API_KEY`, and an optional
`<PROVIDER>_BASE_URL`. Namespacing is deliberate: one vendor's key can never be
sent to another's endpoint on a switch.

| Provider | Model example | Notes |
|---|---|---|
| `ollama` | `gpt-oss:120b` (Cloud) or `llama3.2:3b` (local) | Cloud when no base URL; local by pointing the base URL at your Ollama |
| `anthropic` | `claude-sonnet-5` | Needs an Anthropic API key |
| `openai` | `gpt-4o-mini`, or any compatible model | Point the base URL at OpenAI, Groq, vLLM, LM Studio, … |

Any user-supplied base URL is SSRF-guarded: loopback and LAN are allowed, but a
link-local or cloud-metadata address (169.254.169.254, fe80::) is refused before
a client is built.

## Standing it up

**On the Home Assistant host** — install `addon/` as a local add-on
(copy it into your `/addons` share, then Settings → Add-ons → local repository).
Set three options:

- `service_api_key` — the key the integration presents to this service.
- `ollama_cloud_key` — your Ollama Cloud API key.
- `llm_model` — a model your plan serves, e.g. `gpt-oss:120b` or
  `qwen3-coder:480b-cloud`. Cloud models often carry a `-cloud` suffix.

**On any other box** —

```bash
cd addon
SERVICE_KEY=your-secret OLLAMA_CLOUD_KEY=your-ollama-key docker compose up -d
```

The first start downloads the small embedding model (~a few dozen MB); after
that it is offline for embeddings.

## Feeding it the documents

Same local index the built-in retriever uses — one source of document text:

```bash
python3 scripts/build_kb.py /path/to/bkon-archive --out bkon_brewer_kb.json
python3 scripts/ingest_lightrag.py --kb bkon_brewer_kb.json \
    --url http://homeassistant.local:9621 --key your-secret
```

LightRAG builds its graph in the background; a few hundred passages take a few
minutes on first ingest (each passage is embedded locally and the graph is
extended by the cloud model). The document text is yours to index for your own
machine; it is never committed to this repository.

## Pointing the integration at it

Settings → Devices & Services → BKON → **Configure**:

- **LightRAG URL** — `http://homeassistant.local:9621`. Blank = built-in only.
- **API key** — the `service_api_key` above. Stored in the config entry.
- **Mode** — `hybrid` (default), or `local` / `global` / `mix` / `naive`.

Ask something and check the response's `source` field — `lightrag` or `local` —
to see which path answered.

## Cost and privacy note

Generation runs on your Ollama Cloud plan, so each question is a cloud request
(billed per your subscription). Embeddings and retrieval are local and free.
If the plan lapses or the key is wrong, questions keep working — they just fall
back to the local retriever and the `source` reads `local`.
