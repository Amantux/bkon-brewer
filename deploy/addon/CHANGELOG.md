# Changelog

## 0.4.0
- Home Assistant ingress: a status page in the sidebar (BKON RAG panel),
  authenticated by HA. The key-guarded API stays reachable on port 9621 for the
  integration.
- AppArmor profile (`bkon_lightrag`): least-privilege confinement matching the
  sibling add-ons — file I/O and the network the service needs, everything else
  default-denied. No privilege drop or Supervisor access, which this service
  does not need.
- Debian slim base via `build.yaml`, matching Edibl / HomeHoard / myMeal. Fixes
  reliable aarch64 wheels for onnxruntime and numpy (the local embedder).

## 0.3.0
- Pluggable generation provider: Ollama (local or Cloud), Anthropic, or any
  OpenAI-compatible endpoint, selected by config. Per-provider namespaced keys;
  SSRF-guarded base URLs.

## 0.2.0
- Self-contained service: local bundled embeddings + cloud generation.

## 0.1.0
- Initial LightRAG service for the BKON concierge.
