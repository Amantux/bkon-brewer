"""Complete, self-contained LightRAG service for the BKON concierge.

One process that does the whole job:

  * embeddings   -- fastembed, a local ONNX model. No embedding server, no local
                    Ollama. The model downloads once (~a few dozen MB) and then
                    runs on CPU forever. This is the "ship the embeddings
                    complete" part: nothing external is needed for retrieval.
  * generation   -- the pluggable provider layer (providers/): Ollama (local or
                    Cloud), Anthropic, or any OpenAI-compatible endpoint,
                    selected by AI_PROVIDER. The only thing that leaves the
                    network, and only the prompt does. A Pi that could never run
                    a useful model locally points this at a cloud subscription.
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
from fastapi.responses import FileResponse, HTMLResponse

# fastembed and lightrag are imported inside the lifespan, not here: with the
# LightRAG half switched off they are never touched, so the studio starts
# without paying for an ONNX runtime it will not use.

import ha
import scoring
import studio_tools
from chat import run_chat
from contract import authorized, clean_answer
from providers.config import build_provider, llm_url_ok

logging.basicConfig(level=logging.INFO)
_LOG = logging.getLogger("bkon_lightrag")

# --- configuration, all from the environment -------------------------------
#: Stamped into the page and reported by /config, so which build you are looking
#: at is answerable rather than guessed.
ADDON_VERSION = os.getenv("ADDON_VERSION", "dev")

API_KEY = os.getenv("LIGHTRAG_API_KEY", "")
WORKING_DIR = os.getenv("WORKING_DIR", "/data/rag_storage")

# LightRAG is optional. Off, the container still serves the wiki and the recipe
# studio -- building, tuning, linting and diagnosing need no documents, only a
# generation provider -- and starts immediately, with no embedding model to
# download and no graph storage on disk. On, `answer_docs` and /query join in.
# Both halves live in this one image; the toggle decides what is loaded.
ENABLE_LIGHTRAG = os.getenv("ENABLE_LIGHTRAG", "true").strip().lower() not in (
    "0", "false", "no", "off")

# Generation goes through the pluggable provider layer (providers/), selected
# by AI_PROVIDER: ollama (local or cloud), anthropic, or any OpenAI-compatible
# endpoint. Per the edibl chat-and-providers spec -- no vendor SDK is imported
# here, and switching provider is a config change.

# Local embedding model. bge-small is 384-dim, fast on CPU, and good enough for
# a few hundred short passages. Kept small on purpose -- embedding quality
# barely moves the needle at this corpus size, and a Pi feels every megabyte.
EMBED_MODEL = os.getenv("EMBED_MODEL", "BAAI/bge-small-en-v1.5")
EMBED_DIM = int(os.getenv("EMBED_DIM", "384"))

_embedder = None
_rag = None
_provider = None
_provider_error: str | None = None   # why, when the provider could not be built
_query_param = None          # lightrag.QueryParam, bound at startup when enabled


async def _embed(texts: list[str]) -> np.ndarray:
    """Embed a batch locally. fastembed is synchronous, so it runs in a thread
    to keep the event loop free while the ONNX model works."""
    def run() -> np.ndarray:
        return np.array(list(_embedder.embed(texts)), dtype=np.float32)
    return await asyncio.to_thread(run)


async def _llm(prompt: str, system_prompt: str | None = None,
               history_messages: list | None = None, **_) -> str:
    """Generate via the selected provider. The only outbound call here.

    LightRAG asks for a single completion; the provider layer decides which
    vendor serves it. History, when present, folds into the prompt since this
    layer is single-turn -- LightRAG carries its own context."""
    if history_messages:
        prior = "\n".join(m.get("content", "") for m in history_messages)
        prompt = f"{prior}\n{prompt}" if prior else prompt
    return await _provider.complete(prompt, system=system_prompt)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Warm the provider, and the embedder and LightRAG when they are enabled."""
    global _embedder, _rag, _provider, _query_param

    # The provider is needed for chat and scoring -- but not for the wiki or the
    # recipe builder, which are pure client-side. A misconfigured provider used
    # to raise here and take the whole add-on down on boot, so a missing API key
    # meant a crash loop and a blank sidebar panel rather than a usable page with
    # one broken feature. Now it is recorded and surfaced per-request.
    global _provider_error
    try:
        _apply_overrides()          # UI settings win over the add-on options
        _provider = build_provider()
        _provider_error = None
        _LOG.info("LLM provider: %s", _provider.name)
    except Exception as ex:                          # noqa: BLE001
        _provider, _provider_error = None, str(ex)
        _LOG.error("LLM provider not configured: %s", ex)
        _LOG.error("The wiki and recipe builder still work; chat and scoring "
                   "need a provider. Set it in the add-on configuration.")

    if _provider is None and ENABLE_LIGHTRAG:
        _LOG.error("Skipping LightRAG startup: it generates answers through the "
                   "provider, which is not configured.")
        yield
        return

    if not ENABLE_LIGHTRAG:
        _LOG.info("LightRAG disabled; serving the wiki and recipe studio only. "
                  "Document Q&A (/query, answer_docs) is off; the integration "
                  "falls back to its built-in retriever.")
        yield
        return

    from fastembed import TextEmbedding
    from lightrag import LightRAG, QueryParam
    from lightrag.utils import EmbeddingFunc
    _query_param = QueryParam

    # The model is baked into the image at FASTEMBED_CACHE (see the Dockerfile),
    # so this loads from disk rather than downloading on first start.
    cache = os.getenv("FASTEMBED_CACHE") or None
    _LOG.info("loading local embedder %s (%d-dim)%s", EMBED_MODEL, EMBED_DIM,
              f" from {cache}" if cache else "")
    _embedder = (TextEmbedding(EMBED_MODEL, cache_dir=cache) if cache
                 else TextEmbedding(EMBED_MODEL))

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


def _need_provider() -> None:
    """Refuse the model-backed endpoints with the actual reason."""
    if _provider is None:
        raise HTTPException(
            status_code=503,
            detail=(f"No generation provider: {_provider_error}"
                    if _provider_error else
                    "The generation provider is still starting."))


def _need_rag() -> None:
    """Refuse the document endpoints when the LightRAG half is switched off."""
    if _provider is None and ENABLE_LIGHTRAG:
        _LOG.error("Skipping LightRAG startup: it generates answers through the "
                   "provider, which is not configured.")
        yield
        return

    if not ENABLE_LIGHTRAG:
        raise HTTPException(
            status_code=501,
            detail="LightRAG is disabled in this add-on's configuration; "
                   "document Q&A is unavailable. The recipe studio still works.")
    if _rag is None:
        raise HTTPException(status_code=503, detail="LightRAG still starting")


def _guard(x_api_key: str | None, authorization: str | None) -> None:
    if not authorized(x_api_key, authorization, API_KEY):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


WEBROOT = os.getenv("WEBROOT", "/app/webroot")


@app.get("/", response_class=HTMLResponse)
async def home():
    """The project wiki, served through Home Assistant ingress.

    Ingress authenticates the viewer (the Supervisor proxy), so this is open --
    unlike /query and /documents/text, which the integration reaches over the
    LAN and which stay key-guarded. Static, self-contained, read-only.
    """
    index = os.path.join(WEBROOT, "index.html")
    if os.path.exists(index):
        # Revalidate every load. Without this the page ships only an ETag, and a
        # browser is free to serve a heuristically-cached copy -- which means an
        # add-on update can land and the user still sees the previous build,
        # bugs included, with no way to tell.
        return FileResponse(index, headers={
            "Cache-Control": "no-cache, must-revalidate",
            "X-Bkon-Version": ADDON_VERSION})
    provider = _provider.name if _provider else "not started"
    return HTMLResponse(
        f"<!doctype html><meta charset=utf-8><title>BKON LightRAG</title>"
        f"<body style='font-family:system-ui;max-width:34rem;margin:3rem auto'>"
        f"<h1>&#9749; BKON LightRAG</h1><p>Service up. Provider: <code>{provider}</code>. "
        f"Wiki asset missing.</p>")


@app.get("/health")
async def health():
    return {"status": "ok",
            "provider": _provider.name if _provider else None,
            "provider_error": _provider_error,
            "lightrag": ENABLE_LIGHTRAG,
            "embed": EMBED_MODEL if ENABLE_LIGHTRAG else None,
            "ready": _provider is not None and (_rag is not None or not ENABLE_LIGHTRAG)}


@app.post("/query")
async def query(request: Request,
                x_api_key: str | None = Header(default=None),
                authorization: str | None = Header(default=None)):
    _guard(x_api_key, authorization)
    _need_rag()
    body = await request.json()
    q = (body.get("query") or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="query is required")
    mode = body.get("mode") or "hybrid"
    try:
        result = await _rag.aquery(q, param=_query_param(mode=mode))
    except Exception as ex:                          # noqa: BLE001
        _LOG.exception("query failed")
        raise HTTPException(status_code=502, detail=f"generation failed: {ex}")
    return {"response": clean_answer(result), "mode": mode}


#: What each turn is doing right now, keyed by the id the browser sends. Small,
#: in-memory and deliberately lossy: progress that outlives its turn is noise.
_PROGRESS: dict = {}
_PROGRESS_MAX = 32

#: Plain-language names, so the user reads what is happening rather than a
#: function name. Anything unlisted degrades to a readable version of its own id.
_TOOL_SAYS = {
    "build_recipe": "building the recipe",
    "adjust_recipe": "tuning the recipe",
    "lint_recipe": "checking it over",
    "diagnose": "looking up the fault",
    "score_recipe": "scoring the recipe",
    "answer_docs": "reading the manuals",
    "list_recipes": "fetching your recipes",
    "open_recipe": "opening the recipe",
    "save_recipe": "asking permission to save",
    "brew_recipe": "asking permission to brew",
}


@app.get("/chat/progress")
async def chat_progress(id: str = ""):
    """What the turn with this id is doing. Polled while a reply is pending."""
    return _PROGRESS.get(id) or {"state": "", "detail": ""}


@app.post("/chat")
async def chat_turn(request: Request):
    """One turn of the recipe-studio chat, with tool use.

    Served through ingress like the wiki, so it is open at the app boundary --
    the Supervisor authenticates the viewer -- unlike /query, which the
    integration reaches over the LAN and which stays key-guarded.

    The tools are the very logic the integration ships (build / adjust / lint /
    diagnose, from the vendored core); `answer_docs` reaches this service's own
    RAG. The model drives them through the provider-agnostic loop in chat.py, so
    tool use works the same on Ollama, Anthropic or an OpenAI-compatible model.
    """
    _need_provider()
    body = await request.json()
    message = (body.get("message") or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="message is required")
    steps = body.get("steps") or []
    history = body.get("history") or []
    context = str(body.get("context") or "")[:2000]
    pid = str(body.get("progress_id") or "")[:64]

    def note(kind, name=""):
        if not pid:
            return
        if len(_PROGRESS) > _PROGRESS_MAX:
            _PROGRESS.clear()                        # bounded; it is only a hint
        _PROGRESS[pid] = {
            "state": kind,
            "detail": _TOOL_SAYS.get(name, name.replace("_", " ")) if name else "thinking",
        }

    async def answer_docs(args: dict, _steps):
        """The one tool that needs the running service: ask the manuals."""
        question = str(args.get("query", "")).strip()
        if not question:
            return {"answer": "No question was given."}, None
        try:
            raw = await _rag.aquery(question_for_rag, param=_query_param(mode="hybrid"))
            return {"answer": clean_answer(raw)}, None
        except Exception as ex:                       # noqa: BLE001
            return {"answer": f"Could not reach the documents ({ex})."}, None

    async def score_tool(_args: dict, cur_steps):
        """Score the current recipe. Needs the provider, so it is a closure."""
        crit = await scoring.score_recipe(_provider, cur_steps)
        return {"score": crit.score, "verdict": crit.verdict,
                "comment": crit.comment,
                "dimensions": [{"name": d.name, "rating": d.rating,
                                "comment": d.comment} for d in crit.dimensions],
                "suggestions": crit.suggestions}, None

    # --- the machine-facing tools ------------------------------------------
    # Deliberately narrow: every one of these calls a bkon_brewer service and
    # nothing else. The add-on holds a Supervisor token that could call any
    # service in Home Assistant, so the allow-list is the boundary -- the model
    # never gets to name a domain.
    BKON_READS = {"list_recipes", "open_recipe"}
    BKON_WRITES = {"save_recipe", "brew_recipe"}

    # Whether the assistant may reach Home Assistant at all is the user's call,
    # made per session in the chat, not assumed because the token happens to
    # exist. Granting is remembered for the session only.
    granted = bool(body.get("ha_granted"))

    async def t_list_recipes(_args, _steps):
        if not granted:
            return {"awaiting_confirmation": True, "action": "list_recipes",
                    "name": "your recipe library",
                    "why": "reads the recipe list from Home Assistant"}, None
        try:
            recs = await ha.library()
        except ha.HaError as ex:
            return {"error": str(ex)}, None
        return {"recipes": [{"name": r.get("name"), "steps": len(r.get("steps") or []),
                             "rating": r.get("rating") or 0,
                             "brewed": r.get("brew_count") or 0,
                             "notes": (r.get("notes") or "")[:80]}
                            for r in recs]}, None

    async def t_open_recipe(args, _steps):
        name = str(args.get("name") or "").strip()
        if not granted:
            return {"awaiting_confirmation": True, "action": "open_recipe",
                    "name": name or "a recipe",
                    "why": "reads that recipe from Home Assistant"}, None
        try:
            recs = await ha.library()
        except ha.HaError as ex:
            return {"error": str(ex)}, None
        match = next((r for r in recs if str(r.get("name","")).lower() == name.lower()), None)
        if match is None:
            return {"error": f"no recipe named {name!r}",
                    "available": [r.get("name") for r in recs][:12]}, None
        steps = [{"type": st.get("type"), "values": {k: str(v) for k, v in (st.get("values") or {}).items()}}
                 for st in (match.get("steps") or [])]
        return {"opened": match.get("name"), "steps": len(steps)}, steps

    # Writes never happen here. They come back as a request the UI turns into a
    # confirm/decline chip, so the user authorises the physical action -- not the
    # model, and not a sentence the model was persuaded to read.
    def _needs_ok(action, name, why):
        async def ask(args, _steps):
            target = str(args.get("name") or name or "").strip()
            if not target:
                return {"error": "which recipe?"}, None
            return {"awaiting_confirmation": True, "action": action,
                    "name": target, "why": why}, None
        return ask

    tools_ha = {
        "list_recipes": t_list_recipes,
        "open_recipe": t_open_recipe,
        "save_recipe": _needs_ok("save_recipe", None, "writes to your Home Assistant library"),
        "brew_recipe": _needs_ok("brew_recipe", None, "starts a brew on the machine"),
    }

    # Documents are offered only when there are documents to reach; with the
    # LightRAG half off the tool is absent, not broken. Scoring only needs the
    # provider, so it is always available.
    have_docs = ENABLE_LIGHTRAG and _rag is not None
    tools = studio_tools.registry_for(
        answer_docs if have_docs else None, score_recipe=score_tool)
    if ha.available():
        tools.update(tools_ha)

    try:
        turn = await run_chat(_provider, message, steps, tools,
                              history=history, context=context, on_step=note)
    except Exception as ex:                           # noqa: BLE001
        _LOG.exception("chat failed")
        raise HTTPException(status_code=502, detail=f"chat failed: {ex}")
    _PROGRESS.pop(pid, None)
    return {"reply": turn.reply, "steps": turn.steps,
            "actions": [{"tool": a.tool, "args": a.args, "result": a.result}
                        for a in turn.actions]}


# Settings set from the UI live here and win over the add-on options. Written to
# /data, which is the add-on's own persistent volume -- the same place its
# options already live, and not reachable from outside the container.
SETTINGS_FILE = os.getenv("SETTINGS_FILE", "/data/ui_settings.json")


def _load_overrides() -> dict:
    try:
        import json
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            return json.load(f) or {}
    except (OSError, ValueError):
        return {}


def _apply_overrides() -> None:
    """Fold saved UI settings into the environment the provider layer reads."""
    ov = _load_overrides()
    prov = (ov.get("provider") or "").strip().lower()
    if not prov:
        return
    os.environ["AI_PROVIDER"] = prov
    up = prov.upper()
    if ov.get("model"):
        os.environ[f"{up}_MODEL"] = ov["model"]
    if ov.get("api_key"):
        os.environ[f"{up}_API_KEY"] = ov["api_key"]
    # An empty base_url is meaningful (it means "the vendor default"), so it is
    # only cleared when the key is present and blank.
    if "base_url" in ov:
        if ov["base_url"]:
            os.environ[f"{up}_BASE_URL"] = ov["base_url"]
        else:
            os.environ.pop(f"{up}_BASE_URL", None)


def _rebuild_provider() -> None:
    global _provider, _provider_error
    try:
        _apply_overrides()
        _provider = build_provider()
        _provider_error = None
        _LOG.info("LLM provider: %s", _provider.name)
    except Exception as ex:                          # noqa: BLE001
        _provider, _provider_error = None, str(ex)
        _LOG.error("LLM provider not configured: %s", ex)


@app.post("/config")
async def save_config(request: Request):
    """Set the provider, model and key from the UI, and apply them now.

    Reaching the add-on's Configuration tab is awkward on a phone, and a key you
    cannot set is a feature you cannot use. This is on the ingress surface, which
    Home Assistant authenticates, and the key is written to the add-on's own
    /data volume -- never echoed back, never logged.
    """
    body = await request.json()
    allowed = ("provider", "model", "api_key", "base_url")
    ov = _load_overrides()
    for k in allowed:
        if k in body:
            ov[k] = str(body[k] or "")
    # A blank key means "keep the one already saved", so clearing a field by
    # accident cannot silently sign you out.
    if not ov.get("api_key"):
        ov.pop("api_key", None)
    try:
        import json
        os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(ov, f)
    except OSError as ex:
        raise HTTPException(status_code=500, detail=f"could not save: {ex}")

    _rebuild_provider()
    return {"saved": True, "enabled": _provider is not None,
            "provider": _provider.name if _provider else None,
            "error": _provider_error}


@app.post("/config/models")
async def list_models(request: Request):
    """Ask the provider what models it actually has.

    Takes the provider and key from the request rather than what is saved, so
    the list can be fetched before anything is committed -- you pick a model you
    know exists instead of typing one from memory and finding out later.
    """
    import aiohttp
    body = await request.json()
    provider = (body.get("provider") or "").strip().lower()
    key = (body.get("api_key") or "").strip()
    base = (body.get("base_url") or "").strip().rstrip("/")
    if not key:                              # fall back to the saved one
        key = (_load_overrides().get("api_key") or "").strip()
        if not key:
            up = provider.upper()
            key = os.getenv(f"{up}_API_KEY", "")

    try:
        if provider == "ollama":
            host = base or "https://ollama.com"
            if not llm_url_ok(host):
                raise HTTPException(status_code=400, detail="that base URL is refused")
            url, headers = f"{host}/api/tags", {}
            if key:
                headers["Authorization"] = f"Bearer {key}"
            pick = lambda d: [m["name"] for m in (d.get("models") or []) if m.get("name")]
        elif provider == "anthropic":
            url = (base or "https://api.anthropic.com") + "/v1/models"
            headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
            pick = lambda d: [m["id"] for m in (d.get("data") or []) if m.get("id")]
        else:                                 # openai-compatible
            url = (base or "https://api.openai.com/v1") + "/models"
            headers = {"Authorization": f"Bearer {key}"}
            pick = lambda d: [m["id"] for m in (d.get("data") or []) if m.get("id")]

        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=headers) as resp:
                data = await resp.json(content_type=None)
                if resp.status >= 400:
                    return {"models": [], "error":
                            f"{provider} returned {resp.status}: {str(data)[:160]}"}
                return {"models": sorted(pick(data))[:200]}
    except HTTPException:
        raise
    except Exception as ex:                   # noqa: BLE001
        return {"models": [], "error": str(ex)[:200]}


@app.get("/config")
async def assistant_config():
    """What the UI needs to know about the model, before it asks for anything.

    The Edibl pattern: the page reads this once and adapts, rather than firing a
    request and interpreting a failure. It carries no secrets -- whether a key is
    set, never the key itself -- so it is safe on the open ingress surface.
    """
    return {
        "enabled": _provider is not None,
        "provider": _provider.name if _provider else None,
        "model": getattr(_provider, "model", None) if _provider else None,
        "error": _provider_error,
        "lightrag": ENABLE_LIGHTRAG,
        "documents_ready": bool(ENABLE_LIGHTRAG and _rag is not None),
        "home_assistant": ha.available(),
        "version": ADDON_VERSION,
        # What to change, in the user's terms, when it is not working.
        "saved_here": {k: v for k, v in _load_overrides().items() if k != "api_key"},
        "key_saved": bool(_load_overrides().get("api_key")),
        "setup_hint": (
            None if _provider is not None else
            "Open this add-on's Configuration tab and set ai_provider plus a "
            "model — and an api_key for anthropic/openai, or for Ollama Cloud. "
            "For a local Ollama set base_url to http://<host>:11434."),
    }


# --- recipes: the studio acts on Home Assistant's library directly ----------

@app.get("/recipes")
async def list_recipes():
    """Every saved recipe, from Home Assistant — the one source of truth."""
    try:
        return {"connected": True, "recipes": await ha.library()}
    except Exception as ex:                          # noqa: BLE001
        return {"connected": False, "recipes": [], "error": str(ex)}


@app.post("/recipes")
async def save_recipe(request: Request):
    """Create or update a recipe in Home Assistant, rating and notes included."""
    body = await request.json()
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    data = {"name": name, "steps": body.get("steps") or []}
    for k in ("rating", "notes", "journal"):
        if body.get(k) not in (None, "", []):
            data[k] = body[k]
    try:
        await ha.call_service("save_recipe", data)
    except ha.HaError as ex:
        raise HTTPException(status_code=502, detail=str(ex))
    return {"saved": True, "name": name}


@app.post("/recipes/delete")
async def delete_recipe(request: Request):
    body = await request.json()
    name = (body.get("name") or "").strip()
    if not name and action not in ("list_recipes",):
        raise HTTPException(status_code=400, detail="name is required")
    try:
        await ha.call_service("delete_recipe", {"name": name})
    except ha.HaError as ex:
        raise HTTPException(status_code=502, detail=str(ex))
    return {"deleted": True, "name": name}


@app.post("/recipes/brew")
async def brew_recipe(request: Request):
    """Brew a saved recipe. The one thing that genuinely needs the brewer."""
    body = await request.json()
    name = (body.get("name") or "").strip()
    if not name and action not in ("list_recipes",):
        raise HTTPException(status_code=400, detail="name is required")
    try:
        await ha.call_service("brew_saved", {"name": name})
    except ha.HaError as ex:
        raise HTTPException(status_code=502, detail=str(ex))
    return {"brewing": True, "name": name}


@app.post("/chat/confirm")
async def chat_confirm(request: Request):
    """Carry out an action the user just approved in the chat.

    The model can only ever *request* one of these; nothing here is reachable
    from a tool call. The allow-list is the boundary: two actions, both on
    bkon_brewer, so a persuaded model cannot reach the rest of Home Assistant.
    """
    # The complete set of things the assistant may ever cause. Reads are here
    # too: the point is that nothing reaches Home Assistant without the user
    # having said so at least once this session.
    ALLOWED = {"save_recipe", "brew_recipe", "list_recipes", "open_recipe"}
    body = await request.json()
    action = str(body.get("action") or "")
    name = str(body.get("name") or "").strip()
    if action not in ALLOWED:
        raise HTTPException(status_code=400, detail=f"not an allowed action: {action!r}")
    if not name and action not in ("list_recipes",):
        raise HTTPException(status_code=400, detail="name is required")
    try:
        if action in ("list_recipes", "open_recipe"):
            # Granting is all this does; the assistant re-runs the read itself
            # on the next turn, now that permission is held.
            return {"done": True, "action": action, "grant": True,
                    "message": "The assistant can read your recipes for this session."}
        if action == "save_recipe":
            data = {"name": name, "steps": body.get("steps") or []}
            for k in ("rating", "notes"):
                if body.get(k) not in (None, ""):
                    data[k] = body[k]
            await ha.call_service("save_recipe", data)
            return {"done": True, "action": action, "name": name,
                    "message": f'Saved "{name}".'}
        await ha.call_service("brew_saved", {"name": name})
        return {"done": True, "action": action, "name": name,
                "message": f'Brewing "{name}".'}
    except ha.HaError as ex:
        raise HTTPException(status_code=502, detail=str(ex))


@app.post("/recipes/export-bbp")
async def export_bbp_to_www(request: Request):
    """Write the .bbp where Home Assistant serves it, and say where.

    A blob download does not work here: the panel runs inside Home Assistant's
    ingress iframe, and a sandboxed iframe cannot start a download — the click
    is swallowed with no error. So the integration writes the file to
    /config/www and we hand back the /local URL, which opens as an ordinary
    top-level navigation and downloads normally.
    """
    body = await request.json()
    data = {"menu_name": str(body.get("menu_name") or "Home Assistant"),
            "filename": str(body.get("filename") or "hamenu.bbp")}
    try:
        await ha.call_service("export_bbp", data)
    except ha.HaError as ex:
        raise HTTPException(status_code=502, detail=str(ex))
    return {"written": True, "url": f"/local/bkon/{data['filename']}",
            "filename": data["filename"],
            "warning": "Experimental — the category framing is unconfirmed."}


@app.post("/recipes/note")
async def note_recipe(request: Request):
    """Add a tasting-journal entry against a saved recipe."""
    body = await request.json()
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    data = {"name": name}
    for k in ("changes", "taste", "rating", "when"):
        if body.get(k) not in (None, ""):
            data[k] = body[k]
    try:
        await ha.call_service("add_tasting_note", data)
    except ha.HaError as ex:
        raise HTTPException(status_code=502, detail=str(ex))
    return {"noted": True, "name": name}


# --- documents: answers with the source they came from ----------------------

KB_FILE = os.getenv("KB_FILE", "/data/kb.json")
_kb = None


def _load_kb():
    """The passage index, used for provenance -- which document an answer came from.

    LightRAG writes the prose; this says where it came from. Keeping the two
    separate means a citation is looked up, not generated, so the model cannot
    invent a source that does not exist.
    """
    global _kb
    if _kb is None:
        from bkon_core.knowledge import KnowledgeBase
        _kb = KnowledgeBase.from_file(KB_FILE)
    return _kb


@app.post("/documents/index")
async def upload_index(request: Request,
                       x_api_key: str | None = Header(default=None),
                       authorization: str | None = Header(default=None)):
    """Store the passage index the citations are looked up in."""
    global _kb
    _guard(x_api_key, authorization)
    body = await request.json()
    passages = body.get("passages")
    if not isinstance(passages, list):
        raise HTTPException(status_code=400, detail="passages[] is required")
    import json as _json
    try:
        os.makedirs(os.path.dirname(KB_FILE), exist_ok=True)
        with open(KB_FILE, "w", encoding="utf-8") as f:
            _json.dump({"passages": passages}, f)
    except OSError as ex:
        raise HTTPException(status_code=500, detail=f"could not store: {ex}")
    _kb = None                                    # reload on next use
    kb = _load_kb()
    return {"stored": True, "passages": len(passages), "documents": len(kb.documents)}


@app.get("/documents")
async def documents():
    """Every indexed document, for the reader."""
    kb = _load_kb()
    return {"documents": kb.documents if kb.ready else [], "passages": kb.size if kb.ready else 0}


@app.get("/documents/read")
async def read_document(doc: str, q: str = ""):
    """The passages of one document, in order — a citation you can open and read.

    The PDFs themselves are not on the device (and are not ours to serve), so a
    "link to the document" is its indexed text, which is what the answer was
    drawn from anyway.
    """
    kb = _load_kb()
    if not kb.ready:
        raise HTTPException(status_code=404, detail="no index")
    passages = [p for p in kb._passages if p.doc == doc]
    if not passages:
        raise HTTPException(status_code=404, detail=f"no document named {doc!r}")
    return {"doc": doc, "pages": [{"page": p.page, "text": p.text} for p in passages]}


@app.post("/ask")
async def ask_docs(request: Request):
    """Answer from the machine's documents, and say which ones.

    Deliberately modest about citation: the sources are the documents the
    retriever actually matched, not per-sentence footnotes. That is enough to
    check an answer without pretending to a precision the retrieval does not
    have.
    """
    body = await request.json()
    question = (body.get("question") or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="question is required")
    # Prior turns fold into the query so a follow-up ("and if that fails?") is
    # answered in context rather than as a fresh question.
    history = body.get("history") or []
    if history:
        prior = " ".join(str(h.get("content", ""))[:200] for h in history[-3:])
        question_for_rag = f"{prior}\n{question}"[:1200]
    else:
        question_for_rag = question

    sources = []
    kb = _load_kb()
    if kb.ready:
        seen = set()
        for hit in kb.search(question, k=6):
            doc = hit.passage.doc
            if doc in seen:
                continue
            seen.add(doc)
            sources.append({"doc": doc, "page": hit.passage.page,
                            "url": getattr(hit.passage, "url", "") or "",
                            "excerpt": hit.passage.text.strip()[:220]})

    answer, err = "", None
    if ENABLE_LIGHTRAG and _rag is not None and _provider is not None:
        try:
            raw = await _rag.aquery(question_for_rag, param=_query_param(mode="hybrid"))
            answer = clean_answer(raw)
        except Exception as ex:                   # noqa: BLE001
            err = str(ex)[:200]
    elif not sources:
        err = "No documents indexed yet."

    if not answer and sources:
        # No model, or it failed — the passages are still a real answer.
        answer = sources[0]["excerpt"]
        err = err or "Answered from the index directly (no model answer available)."
    return {"answer": answer, "sources": sources[:4], "note": err,
            "indexed": kb.size if kb.ready else 0}


@app.post("/lint")
async def lint(request: Request):
    """Check a recipe and report every problem with its fix. No model needed."""
    from bkon_core import diagnostics
    from bkon_core.protocol import recipe as R
    body = await request.json()
    try:
        core = [R.Step(R.StepType(s["type"]), dict(s.get("values", {})))
                for s in (body.get("steps") or [])]
    except (KeyError, ValueError) as ex:
        raise HTTPException(status_code=400, detail=f"bad step: {ex}")
    findings = diagnostics.lint_recipe(core)
    errors = sum(1 for f in findings if f.severity >= diagnostics.Severity.ERROR)
    try:
        size = len(R.encode(core).encode("utf-8")) if core else 0
    except Exception:                                # noqa: BLE001
        size = 0
    return {
        "ok": errors == 0,
        "errors": errors,
        "bytes": size,
        "findings": [{"severity": f.label(), "message": f.message, "fix": f.fix,
                      "step": f.step_index} for f in findings],
    }


@app.post("/compose")
async def compose(request: Request):
    """Compile a description into a recipe. No model needed.

    The compiler is deterministic and grounded in the published base recipes, so
    this works with no provider configured -- describing a drink is the one part
    of the studio that should never depend on a key.
    """
    from bkon_core import nl_recipe
    body = await request.json()
    c = nl_recipe.compile_recipe(str(body.get("description") or ""))
    return {
        "style": c.style,
        "summary": c.summary(),
        "steps": [{"type": str(s.type), "values": {k: str(v) for k, v in s.values.items()}}
                  for s in c.steps],
        "targets": [{"what": t.what, "value": t.value, "honoured": t.honoured}
                    for t in c.targets],
        "unmet": c.unmet,
    }


@app.post("/export/bbp")
async def export_bbp(request: Request):
    """Build a .bbp menu file from the posted recipes and return it for download.

    EXPERIMENTAL, and the response says so in a header as well as the docs: the
    container checksum and step records are confirmed against real device files,
    the category framing is not. See docs/BBP_FORMAT.md.
    """
    from fastapi.responses import Response
    from bkon_core.protocol import bbp
    from bkon_core.protocol import recipe as R

    body = await request.json()
    incoming = body.get("recipes")
    if not incoming:                      # a single recipe from the builder
        incoming = [{"name": body.get("name", "Recipe"),
                     "steps": body.get("steps") or []}]
    recipes = []
    for rec in incoming:
        try:
            core = [R.Step(R.StepType(s["type"]), dict(s.get("values", {})))
                    for s in (rec.get("steps") or [])]
        except (KeyError, ValueError) as ex:
            raise HTTPException(status_code=400, detail=f"bad step: {ex}")
        recipes.append({"name": str(rec.get("name", "Recipe"))[:255],
                        "code": str(rec.get("code", ""))[:60],
                        # prepare() is what makes a portion match a real menu:
                        # brew-out appended, wire rules applied.
                        "portions": [(bbp.PORTIONS[0], R.prepare(core))]})
    blob = bbp.build_menu([{"name": str(body.get("menu_name", "Home Assistant")),
                            "colour": (168, 98, 31), "recipes": recipes}])
    name = str(body.get("filename") or "hamenu")[:8] + ".bbp"
    return Response(
        content=blob, media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{name}"',
                 "X-Bkon-Experimental": "category framing unconfirmed; "
                                        "compare with a real Export to Recipe File"})


@app.post("/score")
async def score_endpoint(request: Request):
    """Score one recipe and return the critique.

    Part of the ingress surface, like /chat. Takes ``{"steps": [...]}`` and
    returns the model's score, verdict, per-dimension comments and suggestions,
    with the objective facts (byte fit, linter findings) it was grounded on.
    """
    _need_provider()
    body = await request.json()
    steps = body.get("steps") or []
    try:
        crit = await scoring.score_recipe(_provider, steps)
    except Exception as ex:                            # noqa: BLE001
        _LOG.exception("scoring failed")
        raise HTTPException(status_code=502, detail=f"scoring failed: {ex}")
    return {
        "score": crit.score, "verdict": crit.verdict, "comment": crit.comment,
        "dimensions": [{"name": d.name, "rating": d.rating, "comment": d.comment}
                       for d in crit.dimensions],
        "suggestions": crit.suggestions, "facts": crit.facts,
    }


@app.post("/documents/text")
async def insert(request: Request,
                 x_api_key: str | None = Header(default=None),
                 authorization: str | None = Header(default=None)):
    _guard(x_api_key, authorization)
    _need_rag()
    body = await request.json()
    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")
    # LightRAG extracts entities through the LLM, so an insert fails when the
    # provider does. It used to swallow that and answer "inserted" regardless,
    # which made a whole ingest look like it worked while indexing nothing.
    before = _doc_count()
    try:
        await _rag.ainsert(text)
    except Exception as ex:                          # noqa: BLE001
        _LOG.exception("insert failed")
        raise HTTPException(status_code=502, detail=f"insert failed: {ex}")
    after = _doc_count()
    if after <= before:
        raise HTTPException(
            status_code=502,
            detail="The document was accepted but indexed nothing — LightRAG "
                   "extracts entities through the model, so this usually means "
                   "the generation provider is not working. Check Settings.")
    return {"status": "inserted", "chars": len(text), "documents": after}


def _doc_count() -> int:
    """How many documents LightRAG holds, for verifying an insert landed."""
    try:
        store = getattr(_rag, "full_docs", None)
        data = getattr(store, "_data", None)
        return len(data) if data is not None else 0
    except Exception:                                # noqa: BLE001
        return 0
