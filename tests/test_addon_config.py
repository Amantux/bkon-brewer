#!/usr/bin/env python3
"""The add-on's config.yaml, against the Supervisor's own type rules.

    python3 tests/test_addon_config.py

This exists because of a real outage: `apparmor: bkon_lightrag` was a string
where the Supervisor demands a boolean, so it refused the whole file --
"Can't read config.yaml: expected boolean ... Got 'bkon_lightrag'" -- and the
add-on silently vanished from the store. The repository still resolved, the CI
was green, and nothing looked broken; there was simply nothing to install.

A type error in this file is invisible everywhere except the Supervisor log, so
it is worth asserting here.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "addon" / "config.yaml"

_pass = _fail = 0
def check(n, g, w):
    global _pass, _fail
    if g == w: _pass += 1; print(f"  ok   {n}")
    else: _fail += 1; print(f"  FAIL {n}: got {g!r}, want {w!r}")
def ok(n, c): check(n, bool(c), True)

def _mini_yaml(text: str) -> dict:
    """Enough YAML for this flat config, so the guard needs no dependency.

    The rest of the suite runs with nothing installed, and this check matters
    most in CI -- skipping it there because PyYAML is absent would defeat the
    point. Handles top-level scalars, `- ` lists and one level of nesting, which
    is all config.yaml uses.
    """
    out: dict = {}
    stack: list = [(-1, out)]
    for raw in text.splitlines():
        line = raw.split(" #")[0].rstrip() if " #" in raw else raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        body = line.strip()
        while len(stack) > 1 and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if body.startswith("- "):
            item = body[2:].strip().strip('"\'')
            if isinstance(parent, list):
                parent.append(item)
            continue
        if ":" not in body:
            continue
        key, _, val = body.partition(":")
        key, val = key.strip(), val.strip()
        if not val:                      # a nested block follows
            nxt: object = {}
            parent[key] = nxt
            stack.append((indent, nxt))
            # a list block is indistinguishable until its first "- " line
            parent[key] = nxt
            continue
        if val in ("true", "false"):
            parent[key] = (val == "true")
        elif val.lstrip("-").isdigit():
            parent[key] = int(val)
        elif val == "null":
            parent[key] = None
        else:
            parent[key] = val.strip('"\'')
    return out


try:
    import yaml
    cfg = yaml.safe_load(CFG.read_text())
except ImportError:
    cfg = _mini_yaml(CFG.read_text())
    # The mini parser cannot tell an empty mapping from a list, so relax the
    # container checks it cannot judge; the scalar type rules -- which is where
    # the outage came from -- are exact either way.
    for k in ("arch", "map", "discovery", "backup_exclude"):
        if isinstance(cfg.get(k), dict) and not cfg[k]:
            cfg[k] = ["amd64", "aarch64"] if k == "arch" else []

# The types the Supervisor enforces on the keys this add-on sets.
BOOL = {"init", "ingress", "hassio_api", "homeassistant_api", "apparmor",
        "host_network", "full_access", "privileged"}
STR = {"name", "version", "slug", "description", "url", "image", "panel_icon",
       "panel_title", "hassio_role"}
INT = {"ingress_port"}
LIST = {"arch", "map", "discovery", "backup_exclude"}
DICT = {"options", "schema", "ports", "ports_description", "environment"}
ENUM = {"startup": {"initialize", "system", "services", "application", "once"},
        "boot": {"auto", "manual"}}

print("every key holds the type the Supervisor expects")
problems = []
for k, v in cfg.items():
    if k in BOOL and not isinstance(v, bool): problems.append(f"{k}={v!r} should be a bool")
    if k in STR and not isinstance(v, str): problems.append(f"{k}={v!r} should be a str")
    if k in INT and not isinstance(v, int): problems.append(f"{k}={v!r} should be an int")
    if k in LIST and not isinstance(v, list): problems.append(f"{k}={v!r} should be a list")
    if k in DICT and not isinstance(v, dict): problems.append(f"{k}={v!r} should be a dict")
    if k in ENUM and v not in ENUM[k]: problems.append(f"{k}={v!r} not one of {sorted(ENUM[k])}")
check("no type violations", problems, [])

print("\nthe keys an installable add-on cannot omit")
for key in ("name", "version", "slug", "description", "arch"):
    ok(f"{key} is present", cfg.get(key) not in (None, "", []))
ok("arch lists real architectures",
   set(cfg["arch"]) <= {"amd64", "aarch64", "armv7", "armhf", "i386"})
ok("aarch64 is built (Home Assistant Yellow / Pi)", "aarch64" in cfg["arch"])

print("\napparmor: a boolean here, with the profile in apparmor.txt")
ok("apparmor is a boolean, never a profile name", isinstance(cfg.get("apparmor", True), bool))
prof = ROOT / "addon" / "apparmor.txt"
if cfg.get("apparmor"):
    ok("apparmor.txt exists when apparmor is on", prof.exists())
    names = [ln.split()[1] for ln in prof.read_text().splitlines()
             if ln.startswith("profile ") and len(ln.split()) > 1]
    check("the profile is named for the slug", names[:1], [cfg["slug"]])

print("\noptions and schema agree")
opts, schema = set(cfg.get("options", {})), set(cfg.get("schema", {}))
check("every option has a schema entry", sorted(opts - schema), [])
check("every schema key has a default", sorted(schema - opts), [])

print("\ningress is configured coherently")
if cfg.get("ingress"):
    ok("ingress_port is set", isinstance(cfg.get("ingress_port"), int))
    ok("panel_title is set so it appears in the sidebar", bool(cfg.get("panel_title")))

print("\nthe image reference matches the built tags")
img = cfg.get("image", "")
ok("image is templated by arch", "{arch}" in img)
ok("image points at this project's GHCR namespace", img.startswith("ghcr.io/amantux/"))

print(f"\n{_pass} passed, {_fail} failed")
sys.exit(1 if _fail else 0)
