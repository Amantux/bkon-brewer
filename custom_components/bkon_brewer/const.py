"""Constants for the BKON Craft Brewer integration."""
from __future__ import annotations

DOMAIN = "bkon_brewer"

CONF_ADDRESS = "address"
CONF_SIMULATE = "simulate"
CONF_KB_PATH = "kb_path"
CONF_LIGHTRAG_URL = "lightrag_url"
CONF_LIGHTRAG_KEY = "lightrag_api_key"
CONF_RAG_MODE = "rag_mode"
DEFAULT_KB_FILENAME = "bkon_brewer_kb.json"

# Services
SERVICE_BREW = "brew"
SERVICE_MANUAL_PURGE = "manual_purge"
SERVICE_ABORT = "abort"
SERVICE_RESPOND_DIALOG = "respond_dialog"
SERVICE_SEND_RAW = "send_raw"
SERVICE_SAVE_RECIPE = "save_recipe"
SERVICE_DELETE_RECIPE = "delete_recipe"
SERVICE_BREW_SAVED = "brew_saved"
SERVICE_ASK = "ask"
SERVICE_CUSTOMIZE = "customize_recipe"
SERVICE_LINT = "lint_recipe"
SERVICE_DIAGNOSE = "diagnose"
SERVICE_BUILD = "build_recipe"
SERVICE_GET = "get_recipe"
SERVICE_EXPORT = "export_recipes"
SERVICE_IMPORT = "import_recipes"
SERVICE_DOWNLOAD = "download_recipes"
CONF_RECIPE_DIR = "recipe_dir"
DEFAULT_RECIPE_DIR = "bkon_recipes"

# Dispatcher signal carrying parsed BrewerEvents to entities.
SIGNAL_EVENT = f"{DOMAIN}_event"

# Brewer status, surfaced on the status sensor. These are our own labels for
# what the event stream implies; the brewer does not send a "status" as such.
STATUS_DISCONNECTED = "disconnected"
STATUS_IDLE = "idle"
STATUS_BREWING = "brewing"
STATUS_WAITING = "waiting_for_operator"
STATUS_COMPLETE = "complete"
STATUS_ERROR = "error"
