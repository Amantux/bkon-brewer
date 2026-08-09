"""Pure helpers shared by the service and its tests.

Kept free of the heavy imports (lightrag, fastembed, fastapi) so the security-
relevant bit -- deciding whether a request is authorised -- can be tested with
nothing installed. Everything here is a plain function over strings.
"""
from __future__ import annotations

import re


def authorized(x_api_key: str | None, authorization: str | None,
               expected: str | None) -> bool:
    """Is a request allowed through?

    Accepts the key either as `X-API-Key: <key>` or `Authorization: Bearer
    <key>`, because the integration sends both and different tools send one or
    the other. An empty expected key means auth is disabled (local trusted
    network) -- an explicit choice the operator makes, not a default we impose,
    and the deployment docs call it out.
    """
    if not expected:
        return True
    if x_api_key and _ct_eq(x_api_key.strip(), expected):
        return True
    if authorization:
        token = authorization.strip()
        if token.lower().startswith("bearer "):
            token = token[7:].strip()
        if _ct_eq(token, expected):
            return True
    return False


def _ct_eq(a: str, b: str) -> bool:
    """Constant-time-ish string compare, so a wrong key cannot be timed out
    character by character. Not a hard guarantee in Python, but it removes the
    trivial early-exit leak and costs nothing."""
    if len(a) != len(b):
        return False
    diff = 0
    for x, y in zip(a, b):
        diff |= ord(x) ^ ord(y)
    return diff == 0


#: LightRAG closes an answer with its own reference list — "[1] Some Chunk
#: (Document Chunks 1-8)", "(Knowledge Graph)" and so on. It names internal
#: retrieval artefacts rather than anything a person can open, and the UI shows
#: real, looked-up citations underneath already. So it is cut rather than shown
#: twice, once uselessly.
_REF_HEADING = re.compile(
    r"\n\s*(?:-{3,}\s*\n\s*)?#{0,6}\s*"
    r"(?:references?|sources?|citations?)\s*:?\s*\n(?:.|\n)*$",
    re.IGNORECASE)


def clean_answer(text: str) -> str:
    """Trim LightRAG's boilerplate so what reaches the user is just the answer."""
    text = (text or "").strip()
    for junk in ("Answer:", "Response:"):
        if text.startswith(junk):
            text = text[len(junk):].strip()

    # Only drop a trailing reference block when it really is one: a heading
    # followed by lines that are all list items or blank. A section that happens
    # to be called "Sources" and contains prose is left alone.
    m = _REF_HEADING.search(text)
    if m:
        tail = m.group(0)
        body = [ln.strip() for ln in tail.splitlines()[1:] if ln.strip()]
        listish = [ln for ln in body
                   if ln.startswith(("*", "-", "•")) or re.match(r"^\[?\d+[\].)]", ln)]
        if body and len(listish) >= max(1, len(body) - 1):
            text = text[:m.start()].rstrip()

    # Inline "[1]" markers point at a list that is now gone.
    text = re.sub(r"\s*\[\d+\](?=[\s.,;:)]|$)", "", text)
    return text.strip()
