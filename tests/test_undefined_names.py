#!/usr/bin/env python3
"""No function reads a name that does not exist.

    python3 tests/test_undefined_names.py

Python does not check this until the line runs, so a wrong variable name inside
a rarely-taken branch ships happily. One did: the chat's `answer_docs` tool
queried `question_for_rag`, a local belonging to a different endpoint, and the
resulting NameError was caught by a broad `except` and shown to the user as
"Could not reach the documents". It read as a service outage for as long as it
took anyone to reach that branch -- which was a while, because the model in use
rarely got that far.

A linter would catch this, and the add-on image has none. So this walks the
service's own modules and resolves every name that is *read* against everything
in scope: module globals, enclosing functions, parameters, comprehension and
except targets, imports, and builtins. Anything left over is a name that cannot
resolve at runtime.
"""
import ast
import builtins
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = sorted((ROOT / "addon" / "lightrag_service").rglob("*.py"))

_pass = _fail = 0


def check(name, got, want):
    global _pass, _fail
    if got == want:
        _pass += 1
        print(f"  ok   {name}")
    else:
        _fail += 1
        print(f"  FAIL {name}: got {got!r}, want {want!r}")


BUILTINS = set(dir(builtins)) | {"__file__", "__name__", "__doc__", "__spec__"}


def bound_by(node):
    """Every name this scope binds, without descending into nested scopes."""
    out = set()
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
        a = node.args
        for arg in (*a.posonlyargs, *a.args, *a.kwonlyargs):
            out.add(arg.arg)
        if a.vararg:
            out.add(a.vararg.arg)
        if a.kwarg:
            out.add(a.kwarg.arg)

    body = node.body if isinstance(node.body, list) else [node.body]
    stack = list(body)
    # Decorators and defaults belong to the *enclosing* scope, so they are not
    # walked here; handler_names below picks them up where they are evaluated.
    while stack:
        n = stack.pop()
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(n.name)
            continue                          # its body is a separate scope
        if isinstance(n, ast.Lambda):
            continue
        if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
            out.add(n.id)
        elif isinstance(n, ast.arg):
            out.add(n.arg)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            for alias in n.names:
                out.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(n, ast.ExceptHandler) and n.name:
            out.add(n.name)
        elif isinstance(n, (ast.Global, ast.Nonlocal)):
            out.update(n.names)
        stack.extend(ast.iter_child_nodes(n))
    return out


def loads_in(node):
    """Names this scope *reads*, without descending into nested scopes."""
    out = []
    body = node.body if isinstance(node.body, list) else [node.body]
    stack = list(body)
    while stack:
        n = stack.pop()
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef,
                          ast.ClassDef, ast.Lambda)):
            continue
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
            out.append((n.id, n.lineno))
        stack.extend(ast.iter_child_nodes(n))
    return out


def walk_scopes(node, visible, path, problems):
    """Depth-first through nested scopes, carrying what is visible into each."""
    here = visible | bound_by(node)
    for name, line in loads_in(node):
        if name not in here and name not in BUILTINS:
            problems.append((path, line, name))
    for child in ast.iter_child_nodes(node):
        stack = [child]
        while stack:
            n = stack.pop()
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                walk_scopes(n, here, path, problems)
            elif isinstance(n, ast.ClassDef):
                walk_scopes(n, here, path, problems)
            else:
                stack.extend(ast.iter_child_nodes(n))


problems = []
for f in TARGETS:
    tree = ast.parse(f.read_text(), filename=str(f))
    walk_scopes(tree, set(), f.relative_to(ROOT), problems)

for path, line, name in problems:
    print(f"  FAIL {path}:{line} reads undefined name {name!r}")
check("every name read in the service resolves", len(problems), 0)

# Prove the walker actually detects the bug it was written for, rather than
# passing because it looks at nothing.
sample = ast.parse(
    "def outer():\n"
    "    q = 1\n"
    "    def inner():\n"
    "        return typo_name\n")
found = []
walk_scopes(sample, set(), Path("sample"), found)
check("and it would have caught the original typo",
      [n for _, _, n in found], ["typo_name"])

sample = ast.parse(
    "def outer():\n"
    "    q = 1\n"
    "    def inner():\n"
    "        return q\n")
found = []
walk_scopes(sample, set(), Path("sample"), found)
check("without flagging a legitimate closure", found, [])

print(f"\n{_pass} passed, {_fail} failed")
sys.exit(1 if _fail else 0)
