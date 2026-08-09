#!/usr/bin/env python3
"""Nothing the assistant does reaches Home Assistant unasked.

    python3 tests/test_ha_permission.py

The add-on holds a supervisor token, so every tool it exposes to the model is a
tool that *could* touch the real machine. The rule is that it never does on the
model's say-so alone: a read needs the user to have allowed reads this session,
and a write comes back as a confirm chip the user presses. Both boundaries live
in server.py, which cannot be imported here (it needs fastapi and the LightRAG
stack), so this reads the source with `ast` instead.

That is on purpose, and it is the point: the failure this guards against is
someone adding a *new* tool that calls Home Assistant and forgetting the guard.
A behavioural test of the tools that exist today would pass happily while the
new one shipped ungated. Walking the tree catches the tool nobody wrote a test
for.
"""
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "addon" / "lightrag_service" / "server.py"

_pass = _fail = 0


def check(name, got, want):
    global _pass, _fail
    if got == want:
        _pass += 1
        print(f"  ok   {name}")
    else:
        _fail += 1
        print(f"  FAIL {name}: got {got!r}, want {want!r}")


def ok(name, cond):
    check(name, bool(cond), True)


tree = ast.parse(SRC.read_text())


def names_used(node):
    """Every bare name and dotted root mentioned anywhere under `node`."""
    out = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Name):
            out.add(n.id)
        elif isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name):
            out.add(f"{n.value.id}.{n.attr}")
    return out


def find_func(name, root=tree):
    for n in ast.walk(root):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name:
            return n
    return None


chat = find_func("chat_turn")
ok("the /chat endpoint exists", chat is not None)

# Home-Assistant-reaching tools live in one dict, `tools_ha`, merged into the
# model's tool table only when a supervisor connection exists. Keeping them in
# one named place is what makes the rest of this file checkable: a new tool
# added anywhere else either cannot reach Home Assistant, or shows up in the
# `ha.`-usage sweep below.
ha_dict = None
for n in ast.walk(chat):
    if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "tools_ha":
        ha_dict = {k.value: ast.unparse(v) for k, v in zip(n.value.keys, n.value.values)}
ok("the Home Assistant tools are declared in one place", ha_dict is not None)

reads = writes = None
for n in ast.walk(chat):
    if isinstance(n, ast.Assign):
        target = getattr(n.targets[0], "id", "")
        if target == "BKON_READS":
            reads = {c.value for c in n.value.elts}
        elif target == "BKON_WRITES":
            writes = {c.value for c in n.value.elts}
check("every Home Assistant tool is classified as a read or a write",
      set(ha_dict or {}), (reads or set()) | (writes or set()))
for name in sorted(writes or ()):
    ok(f"the write {name} is registered through _needs_ok",
       ha_dict[name].startswith("_needs_ok("))

# Every tool the model can call that reaches Home Assistant is a nested `t_*`.
tools = [n for n in ast.walk(chat)
         if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
         and n.name.startswith("t_")]
ok("the chat endpoint defines tools", len(tools) >= 2)

print("\nevery tool that touches Home Assistant asks first")
touching = []
for fn in tools:
    used = names_used(fn)
    if any(u.startswith("ha.") for u in used):
        touching.append(fn.name)
        check(f"{fn.name} consults the session grant", "granted" in used, True)

ok("at least one tool reaches Home Assistant (else this test proves nothing)",
   len(touching) >= 2)

print("\nreads are gated, writes never execute in the tool at all")
for name in ("t_list_recipes", "t_open_recipe"):
    fn = find_func(name, chat)
    ok(f"{name} exists", fn is not None)
    src = ast.unparse(fn)
    ok(f"{name} returns a confirmation request when not granted",
       "awaiting_confirmation" in src)
    # The grant must be checked *before* the call, not after it.
    ok(f"{name} checks the grant before calling out",
       src.index("granted") < src.index("ha.library"))

# Writes are registered through _needs_ok, which returns a stub that only ever
# describes the action. If a write ever gains a `ha.` call, the loop above will
# demand a guard for it too.
needs_ok = find_func("_needs_ok", chat)
ok("_needs_ok exists", needs_ok is not None)
ok("_needs_ok never calls Home Assistant itself",
   not any(u.startswith("ha.") for u in names_used(needs_ok)))
ok("_needs_ok always asks", "awaiting_confirmation" in ast.unparse(needs_ok))

print("\nthe confirm endpoint is a closed list, not a passthrough")
confirm = find_func("chat_confirm")
ok("the confirm endpoint exists", confirm is not None)
allowed = None
for n in ast.walk(confirm):
    if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "ALLOWED":
        allowed = {c.value for c in n.value.elts}
ok("it declares an explicit allow-list", allowed is not None)
check("and it lists exactly the four actions the chips can send", allowed,
      {"save_recipe", "brew_recipe", "list_recipes", "open_recipe"})

src = ast.unparse(confirm)
ok("an unlisted action is refused", "ALLOWED" in src and "400" in src)

# Confirming a *read* only hands over permission -- the assistant runs the read
# itself on the next turn. So that branch must return without calling anything.
grant_branch = None
for n in ast.walk(confirm):
    if isinstance(n, ast.If) and "list_recipes" in ast.unparse(n.test):
        grant_branch = n
ok("confirming a read has its own branch", grant_branch is not None)
branch = ast.unparse(grant_branch.body)
ok("granting a read calls nothing", "ha." not in branch)
ok("and it says so plainly", "grant" in branch and "return" in branch)

print("\nthe browser sends the grant, and never invents one")
html = (ROOT / "addon" / "webroot" / "index.html").read_text()
ok("the page sends the session grant with each turn", "ha_granted:haGranted" in html)
ok("the grant starts false", "let haGranted = false" in html)
ok("only a server-confirmed grant sets it", "if(d.grant) haGranted = true" in html)
# A permission that outlives the conversation it was granted in is a permission
# nobody remembers giving, so the grant must never reach storage.
stored = [ln for ln in html.splitlines()
          if "haGranted" in ln and ("localStorage" in ln or "sessionStorage" in ln)]
check("it is never persisted across sessions", stored, [])

print("\nthe progress trace accumulates rather than overwriting")
# server.py cannot be imported (fastapi, LightRAG), but `note` is a small pure
# closure over two names. Lifting it out and running it is a real test of the
# behaviour the browser depends on: that finished steps stay in the list.
note_fn = find_func("note", chat)
ok("the turn reports progress", note_fn is not None)

env = {"_PROGRESS": {}, "_PROGRESS_MAX": 32,
       "_TOOL_SAYS": {"answer_docs": "reading the manuals"},
       "pid": "p1"}
exec(compile(ast.Module(body=[note_fn], type_ignores=[]), "<note>", "exec"), env)
note = env["note"]
note("thinking")
note("tool", "answer_docs")
note("thinking")
trace = env["_PROGRESS"]["p1"]["steps"]

check("every step is kept", len(trace), 3)
check("in the order they happened",
      [s["detail"] for s in trace],
      ["thinking", "reading the manuals", "thinking"])
check("a step is finished when the next one starts",
      [s["done"] for s in trace], [True, True, False])
check("a tool step names its tool", trace[1]["tool"], "answer_docs")

# An unnamed turn must not accumulate anything -- the browser only sends an id
# when it intends to poll, and a dict that grows without one is a leak.
env["_PROGRESS"].clear(); env["pid"] = ""
note("thinking")
check("no id means no trace", env["_PROGRESS"], {})

# The trace is bounded, or a runaway loop grows it without limit.
env["pid"] = "p2"
for _ in range(40):
    note("tool", "answer_docs")
check("the trace is bounded", len(env["_PROGRESS"]["p2"]["steps"]), 16)

print(f"\n{_pass} passed, {_fail} failed")
sys.exit(1 if _fail else 0)
