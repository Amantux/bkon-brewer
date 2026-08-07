"""Pure helpers shared by the service and its tests.

Kept free of the heavy imports (lightrag, fastembed, fastapi) so the security-
relevant bit -- deciding whether a request is authorised -- can be tested with
nothing installed. Everything here is a plain function over strings.
"""
from __future__ import annotations


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


def clean_answer(text: str) -> str:
    """LightRAG sometimes prefixes an answer with its own boilerplate; trim the
    obvious cases so the reply that reaches the user is just the answer."""
    text = (text or "").strip()
    for junk in ("Answer:", "Response:"):
        if text.startswith(junk):
            text = text[len(junk):].strip()
    return text
