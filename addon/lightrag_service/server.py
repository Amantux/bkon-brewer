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
    return _PROGRESS.get(id) or {"steps": []}


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
        """Append to this turn's visible trace.

        The loop reports "thinking" before each model call and "tool" before
        each tool call, so a step is finished exactly when the next one starts.
        Marking it that way is what lets the browser show a running list with
        the completed steps ticked, rather than one line that keeps changing
        and loses everything that came before it.
        """
        if not pid:
            return
        if len(_PROGRESS) > _PROGRESS_MAX:
            _PROGRESS.clear()                        # bounded; it is only a hint
        trace = _PROGRESS.setdefault(pid, {"steps": []})["steps"]
        if trace:
            trace[-1]["done"] = True
        trace.append({
            "kind": kind,
            "tool": name,
            "detail": _TOOL_SAYS.get(name, name.replace("_", " ")) if name else "thinking",
            "done": False,
        })
        del trace[:-16]                              # a turn is at most ~9 steps

    async def answer_docs(args: dict, _steps):
        """The one tool that needs the running service: ask the manuals."""
        question = str(args.get("query", "")).strip()
        if not question:
            return {"answer": "No question was given."}, None
        try:
            raw = await _rag.aquery(question, param=_query_param(mode="hybrid"))
            # No sources here on purpose. The companion is deliberately a
            # lightweight surface -- citations live on the Ask page, which is
            # built to show them. Returning them would only pad the transcript
            # with something nothing renders.
            return {"answer": clean_answer(raw)}, None
        except Exception as ex:                       # noqa: BLE001
            # This handler once hid a NameError as "could not reach the
            # documents" -- a wrong variable name read to the user as a service
            # outage, and to me as one too. Log the traceback so the next
            # mistake in here is findable in the add-on log.
            _LOG.exception("answer_docs failed")
            return {"answer": f"Could not reach the documents ({ex})."}, None

    async def show_diagram(args: dict, _steps):
        """Find a diagram, screenshot or photograph worth showing.

        Separate from answer_docs on purpose. answer_docs answers in words and
        may cite a picture in passing; this is the model deciding that a
        picture *is* the answer -- "which valve is V5?" is better served by the
        flow schematic than by three sentences about it. The model chooses to
        call it; it never chooses what the picture is. Figures come from the
        index, so it cannot describe one that does not exist.
        """
        query = str(args.get("query", "")).strip()
        if not query:
            return {"error": "what should the diagram show?"}, None
        figs = _figures()
        kb = _load_kb()
        if not any(v.get("caption") for v in figs.values()):
            return {"figures": [],
                    "note": "no pictures have been described yet"}, None
        if not kb.ready:
            return {"figures": [], "note": "no index"}, None
        seqs = _sequences()
        picked, seen = [], set()
        for hit in kb.search(query, k=30):
            fid = getattr(hit.passage, "figure", "") or next(
                (k for k, v in figs.items()
                 if v.get("doc") == hit.passage.doc
                 and v.get("page") == hit.passage.page and v.get("caption")), "")
            if not fid or fid in seen or fid not in figs:
                continue
            seen.add(fid)
            f = figs[fid]
            picked.append({"id": fid, "doc": f["doc"], "page": f["page"],
                           "label": f.get("label") or "",
                           "caption": (f.get("caption") or "")[:300],
                           "seq": _seq_brief(fid, seqs)})
            if len(picked) == 3:
                break
        return {"figures": picked,
                "note": "" if picked else "nothing matching to show"}, None

    async def look_up(args: dict, _steps):
        """Exact lookup of an error code, a part number or a diagram label.

        Separate from the document search because embeddings are poor at
        exactly the strings that matter most here: "19006211" and "C:3 M:5"
        are identifiers, not prose, and near-enough is wrong. These come from
        the tables read out of the pictures, so the answer is whatever the
        document says -- the model does not get to compose one.
        """
        q = str(args.get("query", "")).strip()
        if not q:
            return {"error": "look up what?"}, None
        hits = _match_facts(_facts(), q)
        if not hits:
            return {"found": [], "note": f"nothing recorded for {q!r}"}, None
        return {"found": hits, "total": len(hits)}, None

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
    # Offered only when there is something to show. A tool the model can call
    # but that can never return anything is worse than no tool.
    if any(v.get("caption") for v in _figures().values()):
        tools["show_diagram"] = show_diagram
    if any(_facts().values()):
        tools["look_up"] = look_up
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


#: What the add-on Configuration tab asked for, captured before the UI's own
#: saved settings overwrite it. Without this the two are indistinguishable at
#: runtime, and a model saved in the UI months ago silently wins over the one
#: the user just typed into Configuration -- with nothing on screen to say so.
_ADDON_ENV: dict[str, str] = {}


def _apply_overrides() -> None:
    """Fold saved UI settings into the environment the provider layer reads."""
    ov = _load_overrides()
    prov = (ov.get("provider") or "").strip().lower()
    if not prov:
        return
    up = prov.upper()
    if not _ADDON_ENV:
        _ADDON_ENV.update({
            "provider": os.environ.get("AI_PROVIDER", ""),
            "model": os.environ.get(f"{up}_MODEL", ""),
        })
    os.environ["AI_PROVIDER"] = prov
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


def _shadowing() -> str | None:
    """A message if the UI's saved model is overriding the configured one."""
    saved = (_load_overrides().get("model") or "").strip()
    configured = (_ADDON_ENV.get("model") or "").strip()
    if saved and configured and saved != configured:
        return (f"Using {saved}, saved here. The add-on Configuration tab says "
                f"{configured} — this setting wins. Clear the model below to "
                f"go back to {configured}.")
    return None


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
        # Named plainly, because the failure it prevents is a user changing the
        # model in Configuration, seeing no difference, and concluding the
        # add-on is broken.
        "shadowing": _shadowing(),
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
    if not name:
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
    if not name:
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


#: Where the original documents live, when the owner has put them there. The
#: indexed text is what the answers are drawn from, but "read the source" means
#: the actual PDF or video, not a reconstruction of it -- so a citation links to
#: this when it exists and falls back to the text when it does not.
ORIGINALS_DIR = os.getenv("ORIGINALS_DIR", "/share/bkon_lightrag/originals")
_MANIFEST = "manifest.json"

#: Only these are served. A whitelist rather than a guess from the extension:
#: this endpoint hands a file to a browser, and the set of things it is willing
#: to hand over should be a decision, not a consequence.
_ORIGINAL_TYPES = {
    ".pdf": "application/pdf",
    ".mp4": "video/mp4",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".txt": "text/plain; charset=utf-8",
}


def _slug(name: str) -> str:
    """A filesystem-safe handle for a document name.

    Document names carry slashes, ampersands, colons and trailing spaces, and
    none of that belongs in a path. Shared by the stored originals and the
    figure ids so the two agree on what a document is called on disk.
    """
    import re as _re
    return _re.sub(r"[^A-Za-z0-9]+", "-", name).strip("-").lower()[:70] or "doc"


def _doc_key(name: str) -> str:
    """A stable, unique handle for a document.

    The slug alone is not unique: this corpus contains "Service Training
    (Part II)" and "Service Training ( Part II)", one space apart, which slug
    identically. Their figures overwrote each other until the digest was added.
    """
    import hashlib
    return f"{_slug(name)}-{hashlib.sha1(name.encode()).hexdigest()[:8]}"


def _manifest() -> dict:
    """doc name -> stored filename. Empty when nothing has been uploaded."""
    try:
        import json as _json
        with open(os.path.join(ORIGINALS_DIR, _MANIFEST), encoding="utf-8") as f:
            data = _json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _original_path(doc: str) -> str | None:
    """The stored original for `doc`, or None.

    The document name arrives from the browser, so it is never joined into a
    path. It is looked up in the manifest, and the result is checked to be
    inside the originals directory before anything is opened -- a manifest is
    written by an authenticated upload, but defence in depth costs two lines.
    """
    name = _manifest().get(doc)
    if not name:
        return None
    root = os.path.realpath(ORIGINALS_DIR)
    full = os.path.realpath(os.path.join(root, name))
    if os.path.commonpath([root, full]) != root or not os.path.isfile(full):
        return None
    if os.path.splitext(full)[1].lower() not in _ORIGINAL_TYPES:
        return None
    return full


@app.post("/documents/original")
async def upload_original(request: Request, doc: str, filename: str,
                          x_api_key: str | None = Header(default=None),
                          authorization: str | None = Header(default=None)):
    """Store one original document. Key-guarded, like the index upload.

    The add-on writes it because /share belongs to root and the add-on is the
    only thing running as root -- which also means this is the only way the
    originals can get there.
    """
    _guard(x_api_key, authorization)
    # Kept verbatim, not stripped. Document names come from the index and one
    # of them really does end in a space; stripping it here filed the original
    # under a name no citation would ever ask for, and the document silently
    # had no original.
    if not (doc or "").strip():
        raise HTTPException(status_code=400, detail="doc is required")
    # An original for a document the index has never heard of can never be
    # cited, so it is only a file taking up room on the device.
    kb = _load_kb()
    if kb.ready and doc not in kb.documents:
        raise HTTPException(
            status_code=404,
            detail=f"{doc!r} is not an indexed document; nothing would ever "
                   f"cite it. Check the name matches the index exactly.")
    ext = os.path.splitext(filename or "")[1].lower()
    if ext not in _ORIGINAL_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"{ext or 'that'} is not a servable type; "
                   f"expected one of {', '.join(sorted(_ORIGINAL_TYPES))}")
    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="empty upload")

    # Stored under a slug, never under the document name: names carry slashes,
    # ampersands and colons, and none of that belongs in a path.
    import hashlib
    import json as _json
    stored = f"{_doc_key(doc)}{ext}"
    try:
        os.makedirs(ORIGINALS_DIR, exist_ok=True)
        with open(os.path.join(ORIGINALS_DIR, stored), "wb") as f:
            f.write(body)
        man = _manifest()
        man[doc] = stored
        with open(os.path.join(ORIGINALS_DIR, _MANIFEST), "w", encoding="utf-8") as f:
            _json.dump(man, f, indent=1, sort_keys=True)
    except OSError as ex:
        raise HTTPException(status_code=500, detail=f"could not store: {ex}")
    return {"stored": True, "doc": doc, "bytes": len(body), "originals": len(man)}


@app.delete("/documents/original")
async def delete_original(doc: str,
                          x_api_key: str | None = Header(default=None),
                          authorization: str | None = Header(default=None)):
    """Remove one stored original. The way back out of an upload."""
    _guard(x_api_key, authorization)
    import json as _json
    man = _manifest()
    if doc not in man:
        raise HTTPException(status_code=404, detail=f"no original for {doc!r}")
    full = _original_path(doc)
    man.pop(doc, None)
    try:
        if full:
            os.remove(full)
        with open(os.path.join(ORIGINALS_DIR, _MANIFEST), "w", encoding="utf-8") as f:
            _json.dump(man, f, indent=1, sort_keys=True)
    except OSError as ex:
        raise HTTPException(status_code=500, detail=f"could not remove: {ex}")
    return {"removed": True, "doc": doc, "originals": len(man)}


# --- figures: the documents are mostly pictures ----------------------------
# Measured over the stored originals: 717 pages, 620 of which carry a diagram,
# a screenshot or a photograph. Indexing only their text indexes the captions of
# a picture book, which is why 16 documents had two passages or fewer while
# their PDFs ran to dozens of pages. So pages are rendered and described, and
# the descriptions are indexed beside the prose.

FIGURES_DIR = os.getenv("FIGURES_DIR", "/share/bkon_lightrag/figures")
_FIG_INDEX = "figures.json"


def _figures() -> dict:
    """id -> {doc, page, caption, label}. Empty until a reindex has run."""
    try:
        import json as _json
        with open(os.path.join(FIGURES_DIR, _FIG_INDEX), encoding="utf-8") as f:
            data = _json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_figures(index: dict) -> None:
    import json as _json
    os.makedirs(FIGURES_DIR, exist_ok=True)
    with open(os.path.join(FIGURES_DIR, _FIG_INDEX), "w", encoding="utf-8") as f:
        _json.dump(index, f, indent=1, sort_keys=True)


def _figure_path(fid: str) -> str | None:
    """The PNG for a figure id, checked the same way an original is."""
    if fid not in _figures():
        return None
    root = os.path.realpath(FIGURES_DIR)
    full = os.path.realpath(os.path.join(root, f"{fid}.png"))
    if os.path.commonpath([root, full]) != root or not os.path.isfile(full):
        return None
    return full


@app.post("/documents/reindex")
async def reindex(request: Request, render: bool = True,
                  x_api_key: str | None = Header(default=None),
                  authorization: str | None = Header(default=None)):
    """Rebuild the passage index from the stored original PDFs.

    Text comes out per page, so a citation lands on the page it came from
    rather than somewhere in the document. Pages carrying a picture are
    rendered and kept; describing them is a separate, slower step
    (/documents/caption) because it costs a model call each and should be
    resumable.

    Everything already learned about a figure -- its description, its label, the
    data read out of it -- survives a reindex. Re-describing 616 pages because
    the text extractor changed would be an expensive way to get the same
    sentences back, and re-reading them would be worse.
    """
    global _kb
    _guard(x_api_key, authorization)
    import figures as F

    man = _manifest()
    if not man:
        raise HTTPException(
            status_code=404,
            detail="No original documents on the device. Upload them first "
                   "with scripts/upload_originals.py.")

    old = _figures()
    # Documents with no PDF (the videos) have nothing to extract, so their
    # passages are carried across from the current index. Rebuilding from the
    # PDFs alone would delete them, and a reindex should not lose documents.
    prior = _load_kb()
    carried = [{"doc": p.doc, "page": p.page, "text": p.text, "url": p.url}
               for p in (prior._passages if prior.ready else [])
               if not (_original_path(p.doc) or "").lower().endswith(".pdf")
               and not getattr(p, "figure", "")]
    passages: list[dict] = list(carried)
    index: dict = {}
    seen_digests: dict[str, str] = {}
    stats = {"documents": 0, "pages": 0, "figures": 0, "duplicates": 0,
             "skipped": []}

    for doc in sorted(man):
        path = _original_path(doc)
        if path is None or not path.lower().endswith(".pdf"):
            continue                                  # videos have no pages
        try:
            ex = F.extract(doc, open(path, "rb").read(), render=render)
        except Exception as exc:                      # noqa: BLE001
            _LOG.exception("could not read %s", doc)
            stats["skipped"].append(f"{doc}: {exc}")
            continue
        stats["documents"] += 1
        for page in ex.pages:
            stats["pages"] += 1
            if page.text:
                passages.append({"doc": doc, "page": page.number,
                                 "text": page.text})
            if not page.visual or not page.png:
                continue
            # Slide decks repeat their backgrounds; an identical rendering is
            # not a second figure, and describing it again would cost a model
            # call to learn the same thing.
            if page.digest in seen_digests:
                stats["duplicates"] += 1
                continue
            fid = f"{_doc_key(doc)}-p{page.number}"
            seen_digests[page.digest] = fid
            try:
                os.makedirs(FIGURES_DIR, exist_ok=True)
                with open(os.path.join(FIGURES_DIR, f"{fid}.png"), "wb") as fh:
                    fh.write(page.png)
            except OSError as exc:
                stats["skipped"].append(f"{doc} p{page.number}: {exc}")
                continue
            # Everything already known about this figure is carried across;
            # only what the extractor recomputes is overwritten. Listing the
            # fields to keep looked tidier and silently discarded `facts` on
            # the first reindex after an extraction run -- 616 pages of model
            # output, gone, because a field added later was not added here.
            index[fid] = {**(old.get(fid) or {}),
                          "doc": doc, "page": page.number}
            stats["figures"] += 1

    # A described figure is a passage like any other, so retrieval ranks a
    # schematic against the prose instead of in a separate world.
    for fid, fig in index.items():
        if not fig.get("caption"):
            continue
        text = fig["caption"]
        seen_text = ((fig.get("facts") or {}).get("visible_text") or "").strip()
        if seen_text:
            text = f"{text}\n\nText in the picture: {seen_text}"
        passages.append(F.as_passage(fig["doc"], fig["page"], text, fid))

    _write_figures(index)
    import json as _json
    try:
        os.makedirs(os.path.dirname(KB_FILE), exist_ok=True)
        with open(KB_FILE, "w", encoding="utf-8") as f:
            _json.dump({"passages": passages}, f)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"could not store: {exc}")
    _kb = None
    kb = _load_kb()
    stats["passages"] = len(passages)
    stats["carried_over"] = len(carried)
    stats["described"] = sum(1 for v in index.values() if v.get("caption"))
    stats["indexed_documents"] = len(kb.documents)
    return stats


@app.post("/documents/caption")
async def caption_figures(limit: int = 25, redo: bool = False,
                          x_api_key: str | None = Header(default=None),
                          authorization: str | None = Header(default=None)):
    """Describe rendered pages with the vision model. Resumable by design.

    There are ~616 of them, each a model call, so this does `limit` at a time
    and can be run until it reports nothing left. Descriptions are written for
    *retrieval* -- they should contain the words a technician would search for
    when they have the problem the page solves.
    """
    _guard(x_api_key, authorization)
    _need_provider()
    import figures as F
    from providers.base import VisionUnsupported

    index = _figures()
    todo = [fid for fid, v in sorted(index.items())
            if redo or not (v.get("caption") or v.get("skipped"))][:max(1, limit)]
    if not todo:
        return {"done": True, "remaining": 0,
                "described": sum(1 for v in index.values() if v.get("caption"))}

    described = failed = skipped = 0
    errors: list[str] = []
    for fid in todo:
        path = _figure_path(fid)
        if path is None:
            continue
        png = open(path, "rb").read()
        try:
            caption = (await _provider.complete(
                F.CAPTION_PROMPT, images=[png], max_tokens=400)).strip()
        except VisionUnsupported as exc:
            # No point grinding through 600 of these to fail identically.
            raise HTTPException(status_code=422, detail=str(exc))
        except Exception as exc:                      # noqa: BLE001
            failed += 1
            errors.append(f"{fid}: {exc}")
            continue
        if F.is_skip(caption):
            index[fid]["skipped"] = True
            skipped += 1
            continue
        label = ""
        try:
            label = (await _provider.complete(
                F.LABEL_PROMPT + "\n\n" + caption, max_tokens=40)).strip()
        except Exception:                             # noqa: BLE001
            pass                                      # a label is a nicety
        index[fid]["caption"] = caption
        index[fid]["label"] = label[:80]
        described += 1

    _write_figures(index)
    remaining = sum(1 for v in index.values()
                    if not (v.get("caption") or v.get("skipped")))
    return {"described": described, "skipped_by_model": skipped,
            "failed": failed, "errors": errors[:5], "remaining": remaining,
            "done": remaining == 0,
            "note": "run /documents/reindex again to fold new descriptions "
                    "into the search index" if described else ""}


@app.post("/documents/extract")
async def extract_facts(limit: int = 20, redo: bool = False,
                        x_api_key: str | None = Header(default=None),
                        authorization: str | None = Header(default=None)):
    """A second look at each picture, for the parts a description loses.

    The descriptions are prose, and prose drops exactly what is most useful
    here: the wording the machine puts on its own screen, part numbers, the
    meaning of a valve label. The error-code pages make the case -- their left
    half is real PDF text, but the photograph of the display carries the remedy
    and the service number, and that text exists nowhere else.

    Same shape as captioning: a batch at a time, resumable, and it stops at once
    if the model cannot see rather than failing identically six hundred times.
    """
    _guard(x_api_key, authorization)
    _need_provider()
    import figures as F
    from providers.base import VisionUnsupported

    index = _figures()
    todo = [fid for fid, v in sorted(index.items())
            if (v.get("caption") or v.get("skipped"))
            and (redo or "facts" not in v)][:max(1, limit)]
    if not todo:
        return {"done": True, "remaining": 0, "note": "nothing left to read"}

    read = failed = 0
    found = {"codes": 0, "parts": 0, "labels": 0, "text": 0}
    errors: list[str] = []
    for fid in todo:
        path = _figure_path(fid)
        if path is None:
            continue
        try:
            raw = await _provider.complete(
                F.EXTRACT_PROMPT, images=[open(path, "rb").read()], max_tokens=1600)
        except VisionUnsupported as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        except Exception as exc:                      # noqa: BLE001
            failed += 1
            errors.append(f"{fid}: {exc}")
            continue
        facts = F.parse_facts(raw)
        index[fid]["facts"] = facts
        read += 1
        for k in ("codes", "parts", "labels"):
            found[k] += len(facts[k])
        if facts["visible_text"]:
            found["text"] += 1

    _write_figures(index)
    remaining = sum(1 for v in index.values()
                    if (v.get("caption") or v.get("skipped")) and "facts" not in v)
    return {"read": read, "failed": failed, "errors": errors[:5],
            "found": found, "remaining": remaining, "done": remaining == 0,
            "note": "run /documents/reindex to make the transcribed text "
                    "searchable" if read else ""}


def _sequences() -> dict:
    """Which figures read together, and where each one sits in its run.

    Many of these documents walk through something a page at a time: the
    operating cycle, a fault and then its remedy, a menu screen by screen.
    Surfacing one page of that in isolation shows a step without the procedure
    it belongs to, which is how you end up reading "inspect the purge valve"
    with no idea that the next page shows how.

    A run is a maximal stretch of consecutive illustrated pages in one
    document. That sounds crude and is not: an unillustrated page breaks the
    run, which is precisely what separates one fault from the next in the
    error-code deck.
    """
    import figures as F

    figs = {k: v for k, v in _figures().items() if v.get("caption")}
    by_doc: dict[str, dict[int, str]] = {}
    for fid, v in figs.items():
        by_doc.setdefault(v["doc"], {})[int(v["page"])] = fid

    out: dict[str, dict] = {}
    for doc, pages in by_doc.items():
        for run in F.runs_of(list(pages)):
            if len(run) < 2:
                continue                     # a lone page is not a sequence
            ids = [pages[n] for n in run]
            name = F.name_run([figs[i].get("label") or "" for i in ids])
            for pos, fid in enumerate(ids):
                out[fid] = {
                    "name": name or f"{doc}, pages {run[0]}-{run[-1]}",
                    "named": bool(name),
                    "index": pos + 1, "total": len(ids),
                    "first": ids[0], "last": ids[-1],
                    "prev": ids[pos - 1] if pos else "",
                    "next": ids[pos + 1] if pos + 1 < len(ids) else "",
                    "ids": ids,
                }
    return out


def _seq_brief(fid: str, seqs: dict | None = None) -> dict:
    """The part of a sequence worth attaching to a surfaced figure."""
    seq = (seqs if seqs is not None else _sequences()).get(fid)
    if not seq:
        return {}
    return {k: seq[k] for k in
            ("name", "named", "index", "total", "prev", "next")}


def _match_facts(data: dict, query: str, limit: int = 6) -> list[dict]:
    """Rows matching a query, identifiers first.

    Ranked rather than filtered, because these are identifiers and a loose
    match is actively misleading: searching "V5" once returned a Siemens power
    supply, whose description contains "208/230V50-60Hz". An exact identifier
    beats a partial one, and a partial one beats a word found in a description
    -- and descriptions are only consulted when no identifier matched at all.
    """
    import re
    needle = re.sub(r"[^a-z0-9]", "", query.lower())
    if not needle:
        return []
    exact, partial, textual = [], [], []
    for kind, key in (("codes", "code"), ("parts", "number"), ("labels", "label")):
        for row in data[kind].values():
            ident = re.sub(r"[^a-z0-9]", "", str(row.get(key, "")).lower())
            hit = {"kind": kind[:-1],
                   **{k: v for k, v in row.items() if k != "seen"}}
            where = (row.get("seen") or [{}])[0]
            hit |= {"doc": where.get("doc"), "page": where.get("page"),
                    "figure": where.get("figure")}
            if ident and ident == needle:
                exact.append(hit)
            elif ident and len(needle) >= 3 and needle in ident:
                partial.append(hit)
            elif len(needle) >= 4 and re.search(
                    r"\b" + re.escape(query.strip().lower()),
                    " ".join(str(v) for k, v in row.items()
                             if k not in ("seen", "variants")).lower()):
                textual.append(hit)
    ranked = exact + partial + (textual if not (exact or partial) else [])
    return ranked[:limit]


def _facts() -> dict:
    """Everything read out of the pictures, gathered and de-duplicated.

    Rows are keyed on their identity -- a code, a part number, a label -- and
    the first sighting wins, with every page that showed it recorded. The same
    error code appears on several pages, and one entry citing three pages is
    more useful than three entries.
    """
    import re
    codes: dict[str, dict] = {}
    parts: dict[str, dict] = {}
    labels: dict[str, dict] = {}
    for fid, v in sorted(_figures().items()):
        facts = v.get("facts") or {}
        where = {"figure": fid, "doc": v.get("doc"), "page": v.get("page")}
        for row in facts.get("codes") or []:
            # Documents write the same fault as "C:3 M:5" and "C3:M5", so the
            # key keeps only what identifies it. Punctuation made one fault
            # into two entries with different remedies.
            key = re.sub(r"[^A-Z0-9]", "", row["code"].upper())
            entry = codes.setdefault(key, {**row, "seen": [], "variants": {}})
            for f in ("title", "cause", "remedy", "message"):
                value = (row.get(f) or "").strip()
                if not value:
                    continue
                if not entry.get(f):
                    entry[f] = value            # a later page fills a gap
                elif value != entry[f]:
                    # Sources disagreeing is worth knowing about, not
                    # smoothing over: a vision model misread a service phone
                    # number on one page, and silently keeping whichever was
                    # seen first would have hidden that entirely.
                    entry["variants"].setdefault(f, [])
                    if value not in entry["variants"][f]:
                        entry["variants"][f].append(value)
            entry["seen"].append(where)
        for row in facts.get("parts") or []:
            entry = parts.setdefault(row["number"], {**row, "seen": []})
            # One page lists a number with no description; another names it.
            # Whichever was read first should not win by being first.
            if not entry.get("name") and row.get("name"):
                entry["name"] = row["name"]
            entry["seen"].append(where)
        for row in facts.get("labels") or []:
            entry = labels.setdefault(row["label"].upper(), {**row, "seen": []})
            if not entry.get("name") and row.get("name"):
                entry["name"] = row["name"]
            entry["seen"].append(where)
    return {"codes": codes, "parts": parts, "labels": labels}


@app.get("/facts")
async def facts(kind: str = "", q: str = "", limit: int = 200):
    """The tables read out of the pictures: error codes, parts, labels."""
    data = _facts()
    if kind and kind not in data:
        raise HTTPException(status_code=400,
                            detail=f"kind must be one of {', '.join(data)}")
    ranked = _match_facts(data, q, limit=500) if q.strip() else None

    def rows(name):
        if ranked is not None:
            return [r for r in ranked if r["kind"] == name[:-1]][:limit]
        return list(data[name].values())[:max(1, min(limit, 500))]

    wanted = [kind] if kind else list(data)
    return {name: rows(name) for name in wanted} | {
        "counts": {k: len(v) for k, v in data.items()}}


@app.get("/documents/sequence")
async def sequence(id: str):
    """Every page of the run this figure belongs to, in order."""
    seq = _sequences().get(id)
    if not seq:
        raise HTTPException(status_code=404,
                            detail=f"{id!r} is not part of a multi-page run")
    figs = _figures()
    return {"name": seq["name"], "named": seq["named"], "total": seq["total"],
            "current": id,
            "pages": [{"id": f, "doc": figs[f]["doc"], "page": figs[f]["page"],
                       "label": figs[f].get("label") or ""}
                      for f in seq["ids"] if f in figs]}


@app.get("/documents/figure")
async def figure_image(id: str):
    """The rendered page behind a figure."""
    full = _figure_path(id)
    if full is None:
        raise HTTPException(status_code=404, detail=f"no figure {id!r}")
    return FileResponse(full, media_type="image/png",
                        headers={"Cache-Control": "private, max-age=86400"})


@app.get("/documents/figures")
async def list_figures(doc: str = "", q: str = "", limit: int = 24):
    """Figures, optionally for one document or matching a search."""
    index = _figures()
    items = [{"id": k, **v} for k, v in index.items() if v.get("caption")]
    if doc:
        items = [i for i in items if i["doc"] == doc]
    if q:
        kb = _load_kb()
        if kb.ready:
            order = {h.passage.figure: n for n, h in
                     enumerate(kb.search(q, k=40)) if h.passage.figure}
            items = [i for i in items if i["id"] in order]
            items.sort(key=lambda i: order[i["id"]])
    else:
        items.sort(key=lambda i: (i["doc"], i["page"]))
    seqs = _sequences()
    for i in items:
        i["seq"] = _seq_brief(i["id"], seqs)
    return {"figures": items[:max(1, min(limit, 60))],
            "total": len(index),
            "described": sum(1 for v in index.values() if v.get("caption"))}


@app.get("/documents/file")
async def original_file(doc: str):
    """The original document itself — the thing a citation should open.

    Served inline so the browser's own PDF viewer takes it and `#page=N` works;
    that is the difference between "here is the document" and "here is the
    document, open at the paragraph the answer came from".
    """
    full = _original_path(doc)
    if full is None:
        raise HTTPException(status_code=404, detail=f"no original for {doc!r}")
    ext = os.path.splitext(full)[1].lower()
    ascii_name = "".join(c if 32 < ord(c) < 127 and c != '"' else "_" for c in doc)
    return FileResponse(
        full, media_type=_ORIGINAL_TYPES[ext],
        headers={"Content-Disposition":
                 f'inline; filename="{ascii_name}{ext}"',
                 "Cache-Control": "private, max-age=3600"})


@app.get("/documents")
async def documents():
    """Every indexed document, for the reader."""
    kb = _load_kb()
    man = _manifest()
    docs = kb.documents if kb.ready else []
    return {"documents": docs,
            "passages": kb.size if kb.ready else 0,
            "originals": sorted(d for d in docs if d in man),
            # Stored originals for documents that are no longer indexed. Listed
            # because --prune could not see them otherwise: it compared against
            # `originals`, which is already filtered to indexed documents, so
            # the orphans it exists to remove were invisible to it.
            "orphans": sorted(d for d in man if d not in docs)}


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


def _cite(question: str, k: int = 6) -> list[dict]:
    """The documents that answer this question, one entry per document.

    Each entry says whether the original document is on the device, so the UI
    can offer a link to the real thing rather than guessing and producing a dead
    one.
    """
    kb = _load_kb()
    if not kb.ready:
        return []
    man = _manifest()
    figs = _figures()
    seqs = _sequences()
    out, seen = [], set()
    for hit in kb.search(question, k=k):
        doc = hit.passage.doc
        if doc in seen:
            continue
        seen.add(doc)
        entry = {"doc": doc, "page": hit.passage.page,
                 "url": getattr(hit.passage, "url", "") or "",
                 "original": doc in man,
                 "excerpt": hit.passage.text.strip()[:220]}
        # If the retrieved passage *is* a described picture, or the page it
        # came from has one, the citation can show it. Most of this corpus is
        # diagrams, so an answer about a valve is far better with the schematic
        # beside it than with a page number.
        fid = getattr(hit.passage, "figure", "") or ""
        if not fid:
            fid = next((k for k, v in figs.items()
                        if v.get("doc") == doc and v.get("page") == hit.passage.page
                        and v.get("caption")), "")
        if fid and fid in figs:
            entry["figure"] = {"id": fid, "label": figs[fid].get("label") or "",
                               "caption": figs[fid].get("caption") or "",
                               "seq": _seq_brief(fid, seqs)}
        out.append(entry)
    return out


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

    sources = _cite(question)
    kb = _load_kb()

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
    # Pictures shown above the sources, because for this corpus the picture
    # usually *is* the answer. Looked up from the retrieved passages, never
    # named by the model -- same rule as the citations.
    shown, seen_fig = [], set()
    for sx in sources:
        fig = sx.get("figure")
        if fig and fig["id"] not in seen_fig:
            seen_fig.add(fig["id"])
            shown.append({**fig, "doc": sx["doc"], "page": sx["page"]})
    return {"answer": answer, "sources": sources[:4], "figures": shown[:2],
            "note": err, "indexed": kb.size if kb.ready else 0}


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
