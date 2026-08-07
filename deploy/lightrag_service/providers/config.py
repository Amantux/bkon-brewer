"""Provider selection and config resolution, per the edibl spec §3.

Two rules from the spec that matter most, both about not shooting yourself in
the foot:

1. **Per-provider namespaced config.** Each vendor's key/model/base URL is read
   from `<PROVIDER>_*` env, so switching provider can never send Anthropic's key
   to Ollama's endpoint. The active provider is chosen by `AI_PROVIDER`.

2. **SSRF guard on any user-supplied base URL.** A base URL that resolves to
   link-local or a cloud metadata endpoint (169.254.169.254, fe80::, IPv4-mapped
   forms) is refused; loopback and LAN are allowed. Enforced before a client is
   ever built.
"""
from __future__ import annotations

import ipaddress
import os
from urllib.parse import urlparse

from .anthropic import AnthropicProvider
from .base import AIProvider, ProviderError
from .ollama import OllamaProvider
from .openai_compat import OpenAICompatProvider


def llm_url_ok(url: str | None) -> bool:
    """Is a base URL safe to call? Blocks SSRF avenues, allows loopback + LAN.

    A hostname that does not parse to an IP is allowed (it is a real DNS name a
    human typed); the block list targets the numeric forms used to reach a
    cloud's metadata service or a link-local address.
    """
    if not url:
        return True                                  # no base URL = vendor default
    host = (urlparse(url).hostname or "").strip("[]")
    if not host:
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return True                                  # a DNS name, not a raw IP
    if ip.version == 6 and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    # Order matters: Python counts 169.254/16 as "private", so the dangerous
    # ranges must be rejected BEFORE the loopback/LAN allow, or cloud-metadata
    # (169.254.169.254) slips through as if it were a LAN address.
    if ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
        return False
    if ip.is_loopback or ip.is_private:
        return True                                  # localhost + LAN are fine
    return True                                      # a public address is allowed


def _env(provider: str, field: str, default: str = "") -> str:
    """Read `<PROVIDER>_<FIELD>` (namespaced), falling back to a bare `<FIELD>`
    so a single-provider deployment can use short names."""
    return (os.getenv(f"{provider.upper()}_{field.upper()}")
            or os.getenv(field.upper()) or default)


def build_provider(env: dict | None = None) -> AIProvider:
    """Build the active provider from the environment. Raises if unusable.

    `env` is injectable so this is testable without touching os.environ.
    """
    getenv = (env or os.environ).get
    provider = (getenv("AI_PROVIDER") or "ollama").strip().lower()

    def field(name: str, default: str = "") -> str:
        return (getenv(f"{provider.upper()}_{name.upper()}")
                or getenv(name.upper()) or default)

    base_url = field("BASE_URL") or field("HOST")
    if not llm_url_ok(base_url):
        raise ProviderError(
            f"Refusing base URL {base_url!r}: it targets a link-local or "
            f"metadata address. Use loopback, a LAN address, or a public host.")

    if provider == "ollama":
        p = OllamaProvider(
            host=base_url or "https://ollama.com",
            model=field("MODEL", "gpt-oss:120b"),
            api_key=field("API_KEY") or getenv("OLLAMA_API_KEY"))
    elif provider == "anthropic":
        p = AnthropicProvider(
            api_key=field("API_KEY"), model=field("MODEL", "claude-sonnet-5"),
            base_url=base_url or None)
    elif provider in ("openai", "openai_compat", "compatible"):
        p = OpenAICompatProvider(
            api_key=field("API_KEY"), model=field("MODEL"),
            base_url=base_url or None)
    else:
        raise ProviderError(
            f"Unknown AI_PROVIDER {provider!r}. Use ollama, anthropic or openai.")

    if not p.available():
        raise ProviderError(
            f"Provider {provider!r} is not fully configured (needs a model, and "
            f"a key for anthropic/openai). Check the {provider.upper()}_* options.")
    return p
