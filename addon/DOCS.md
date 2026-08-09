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

2. **Start it.** The status page appears in the sidebar (Bkon RAIN). First start
   downloads the small embedding model; after that it is offline for embeddings.

3. **Feed it the documents** (from the integration repo):
   ```
   python3 scripts/ingest_lightrag.py --kb bkon_brewer_kb.json \
       --url http://homeassistant.local:9621 --key YOUR_SERVICE_KEY
   ```

4. **Point the integration at it** — Settings → Devices & Services → BKON →
   Configure: the LightRAG URL (`http://homeassistant.local:9621`) and the
   service API key.

## Recipe studio

Open the add-on (its ingress panel in the sidebar) and go to **Recipe studio**.
It pairs a hand-builder with a chat: build a brew sequence step by step, or say
*"a strong small cup, less bitter"* and watch the steps change. The chat drives
the same build / tune / lint / diagnose tools the integration ships, and *"how do
I descale?"* is answered from the machine's documents. Both sides share one
recipe, and the byte gauge shows whether it fits a Bluetooth brew.

**Score it** — the *Score recipe* button (or "score this" in the chat) has the
model rate the recipe out of 100 and comment, grounded in the confirmed ranges,
the byte fit and how the vacuum reads. **Rate it yourself** — give it stars and a
note; they ride along with the `save_recipe` call you copy, and persist via the
integration's `rate_recipe` service.

The chat needs a generation provider set (below) — without one the builder still
works, but the chat will say it can't reach the service. It does **not** need
**Document Q&A**: with that option off the studio still builds, tunes, lints and
diagnoses, and the add-on starts immediately with no embedding model to download.
Only *"how do I descale?"*-style questions need the documents.

## Reading the source

Answers cite the documents they came from. By default a citation opens the
**indexed text** — what the answer was actually drawn from. Upload the original
PDFs and it opens the **document itself**, in your browser's viewer, at the
cited page:

```
python3 scripts/upload_originals.py --dir /path/to/archive \
    --url http://homeassistant.local:9621 --key YOUR_SERVICE_KEY
```

Files are matched to documents by name (`Operation Manual.pdf` → the indexed
`Operation Manual`); videos by their `.info.json` title. Anything unmatched is
skipped and listed. They are stored under `/share/bkon_lightrag/originals` and
served only through Home Assistant's authenticated ingress — delete that folder
to undo it. Run with `--dry-run` first to see what would go.

## Reading the pictures

These documents are mostly pictures. Of 717 pages across the stored PDFs, **620
carry a diagram, a screenshot or a photograph** — one page of the air/water flow
deck has 226 characters of text and a full hydraulic schematic on it. Indexing
only the text indexes the captions of a picture book.

Two steps, once the originals are uploaded:

```
curl -X POST http://homeassistant.local:9621/documents/reindex
```

Extracts the text **per page** (so citations land on the right page) and renders
every page carrying a picture. Fast and free — about a minute for the whole set.

```
curl -X POST 'http://homeassistant.local:9621/documents/caption?limit=25'
```

Describes those pages with the model, in the words a technician would search
for. One model call per page and about 600 pages, so it works in batches and
reports `remaining` — repeat until `done`. Needs a model that can see (gemma and
qwen-vl families do; it will tell you if yours cannot). Run `reindex` once more
afterwards to fold the descriptions into the search index.

Once described, the pictures are searchable, they appear beside the answers that
cite them, and the assistant can choose to send you one when a diagram is a
better answer than a paragraph.

## What the assistant may do

The chat can reach the BKON integration in Home Assistant — but only after you
say so, and only for the four things it needs:

| It wants to | You see | Lasts |
|---|---|---|
| List your recipes, open one | *Let the assistant read your recipe library?* | the conversation |
| Save a recipe | *Save "Morning Ethiopia"?* | that one save |
| Start a brew | *Brew "Morning Ethiopia"?* | that one brew |

Allowing reads is remembered until you close the chat and never written to
storage. Saves and brews are asked every single time — the model can request
one, but only your press performs it. The add-on refuses any other action, so a
model talked into something by a document it read cannot reach the rest of your
Home Assistant. If the add-on has no supervisor connection the tools are absent
rather than broken, and the chat says so.

## Ports

- **Ingress** serves the wiki, the recipe studio and the chat through Home
  Assistant's authenticated proxy — no port to expose. `POST /chat` (one
  tool-using turn) is part of that ingress surface.
- **9621/tcp** is the API. Map it only so the integration (or another LAN
  client) can reach it directly; it is guarded by the service API key.

## Privacy

Embeddings and retrieval are local. Generation runs on the provider you choose;
for a cloud provider, each question's prompt is a billed request. If the key is
wrong or the plan lapses, the integration falls back to its local retriever.
