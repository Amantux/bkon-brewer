"""Complete, self-contained LightRAG service for the BKON concierge.

One process that does the whole job:

  * embeddings   -- fastembed, a local ONNX model. No embedding server, no local
                    Ollama. The model downloads once (~a few dozen MB) and then
                    runs on CPU forever. This is the "ship the embeddings
                    complete" part: nothing external is needed for retrieval.
  * generation   -- Ollama Cloud. The only thing that leaves the network, and
                    only the prompt does. This is where the subscription is
                    used, and why a Pi that could never run a 3B model locally
                    can still give written answers.
  * orchestration-- LightRAG as a library, wiring the two together into graph
                    retrieval plus generation.

It exposes exactly the three endpoints the Home Assistant integration already
speaks -- POST /query, POST /documents/text, GET /health -- so the integration
needs no changes to use it.

Everything is configured by environment (set from the add-on options or the
compose file); nothing is hard-coded. Run it with:

    uvicorn server:app --host 0.0.0.0 --port 9621
"""
from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager

import numpy as np
from fastapi import FastAPI, Header, HTTPException, Request
from fastembed import TextEmbedding
from lightrag import LightRAG, QueryParam
from lightrag.utils import EmbeddingFunc
from ollama import AsyncClient

from contract import authorized, clean_answer

logging.basicConfig(level=logging.INFO)
_LOG = logging.getLogger("bkon_lightrag")

# --- configuration, all from the environment -------------------------------
API_KEY = os.getenv("LIGHTRAG_API_KEY", "")
WORKING_DIR = os.getenv("WORKING_DIR", "/data/rag_storage")

# Ollama Cloud. The host is the cloud endpoint; the key is the subscription's.
# Model names on the cloud carry a size and often a "-cloud" suffix; the
# operator sets whichever their plan serves.
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "https://ollama.com")
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-oss:120b")

# Local embedding model. bge-small is 384-dim, fast on CPU, and good enough for
# a few hundred short passages. Kept small on purpose -- embedding quality
# barely moves the needle at this corpus size, and a Pi feels every megabyte.
EMBED_MODEL = os.getenv("EMBED_MODEL", "BAAI/bge-small-en-v1.5")
EMBED_DIM = int(os.getenv("EMBED_DIM", "384"))

_embedder: TextEmbedding | None = None
_rag: LightRAG | None = None
_ollama: AsyncClient | None = None


async def _embed(texts: list[str]) -> np.ndarray:
    """Embed a batch locally. fastembed is synchronous, so it runs in a thread
    to keep the event loop free while the ONNX model works."""
    def run() -> np.ndarray:
        return np.array(list(_embedder.embed(texts)), dtype=np.float32)
    return await asyncio.to_thread(run)


async def _llm(prompt: str, system_prompt: str | None = None,
               history_messages: list | None = None, **_) -> str:
    """Generate with Ollama Cloud. The only outbound call in the service."""
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    for m in history_messages or []:
        messages.append(m)
    messages.append({"role": "user", "content": prompt})
    resp = await _ollama.chat(model=LLM_MODEL, messages=messages)
    return resp["message"]["content"]


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Warm the embedder and LightRAG once, at startup, not per request."""
    global _embedder, _rag, _ollama
    _LOG.info("loading local embedder %s (%d-dim)", EMBED_MODEL, EMBED_DIM)
    _embedder = TextEmbedding(EMBED_MODEL)

    headers = {"Authorization": f"Bearer {OLLAMA_API_KEY}"} if OLLAMA_API_KEY else None
    _ollama = AsyncClient(host=OLLAMA_HOST, headers=headers)
    _LOG.info("LLM via Ollama Cloud: %s at %s", LLM_MODEL, OLLAMA_HOST)

    os.makedirs(WORKING_DIR, exist_ok=True)
    _rag = LightRAG(
        working_dir=WORKING_DIR,
        llm_model_func=_llm,
        embedding_func=EmbeddingFunc(
            embedding_dim=EMBED_DIM, max_token_size=512, func=_embed),
    )
    # Newer LightRAG requires explicit storage init; older does it in __init__.
    for step in ("initialize_storages",):
        fn = getattr(_rag, step, None)
        if fn:
            await fn()
    try:
        from lightrag.kg.shared_storage import initialize_pipeline_status
        await initialize_pipeline_status()
    except Exception:                                # noqa: BLE001
        pass
    _LOG.info("LightRAG ready; storage at %s", WORKING_DIR)
    yield


app = FastAPI(title="BKON LightRAG", lifespan=lifespan)


def _guard(x_api_key: str | None, authorization: str | None) -> None:
    if not authorized(x_api_key, authorization, API_KEY):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


@app.get("/health")
async def health():
    return {"status": "ok", "llm": LLM_MODEL, "embed": EMBED_MODEL,
            "ready": _rag is not None}


@app.post("/query")
async def query(request: Request,
                x_api_key: str | None = Header(default=None),
                authorization: str | None = Header(default=None)):
    _guard(x_api_key, authorization)
    body = await request.json()
    q = (body.get("query") or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="query is required")
    mode = body.get("mode") or "hybrid"
    try:
        result = await _rag.aquery(q, param=QueryParam(mode=mode))
    except Exception as ex:                          # noqa: BLE001
        _LOG.exception("query failed")
        raise HTTPException(status_code=502, detail=f"generation failed: {ex}")
    return {"response": clean_answer(result), "mode": mode}


@app.post("/documents/text")
async def insert(request: Request,
                 x_api_key: str | None = Header(default=None),
                 authorization: str | None = Header(default=None)):
    _guard(x_api_key, authorization)
    body = await request.json()
    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")
    await _rag.ainsert(text)
    return {"status": "inserted", "chars": len(text)}
