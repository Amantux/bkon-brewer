"""Constants for the BKON Craft Brewer integration."""
from __future__ import annotations

DOMAIN = "bkon_brewer"

CONF_ADDRESS = "address"
CONF_SIMULATE = "simulate"
CONF_KB_PATH = "kb_path"
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
