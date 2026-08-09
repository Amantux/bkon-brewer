#!/usr/bin/env python3
"""Serving the original documents, and refusing to serve anything else.

    python3 tests/test_originals.py

A citation is only checkable if you can open what it cites. The add-on serves
the original PDFs so "Open original" reaches the actual page rather than a
reconstruction of its text.

That makes one endpoint hand a file from disk to a browser, on the strength of a
name the browser supplied — which is the shape of a directory-traversal bug. So
the lookup never joins the supplied name into a path: it resolves through a
manifest and then checks the result is really inside the originals directory.
Both halves are tested here, including the attacks they exist to stop.

server.py needs fastapi and the LightRAG stack, so the two functions are lifted
out with `ast` and run directly — the same trick test_ha_permission.py uses.
"""
import ast
import os
import sys
import tempfile
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


def top(name):
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name:
            return n
        if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == name:
            return n
    return None


for want in ("_manifest", "_original_path", "_ORIGINAL_TYPES"):
    ok(f"{want} exists", top(want) is not None)

tmp = tempfile.mkdtemp()
env = {"os": os, "ORIGINALS_DIR": tmp, "_MANIFEST": "manifest.json",
       "_ORIGINAL_TYPES": {".pdf": "application/pdf", ".mp4": "video/mp4"}}
mod = ast.Module(body=[top("_manifest"), top("_original_path")], type_ignores=[])
exec(compile(mod, "<originals>", "exec"), env)
manifest, original_path = env["_manifest"], env["_original_path"]

print("\nwith nothing uploaded, nothing is served")
check("an empty manifest is empty, not an error", manifest(), {})
check("and no document has an original", original_path("Operation Manual"), None)

# Lay out a small originals directory the way the upload endpoint would.
import json                                                        # noqa: E402
Path(tmp, "operation-manual-abc123.pdf").write_bytes(b"%PDF-1.4 ...")
Path(tmp, "a-video-def456.mp4").write_bytes(b"\x00\x00\x00 ftypmp42")
Path(tmp, "notes.exe").write_bytes(b"MZ")
Path(tmp, "manifest.json").write_text(json.dumps({
    "Operation Manual": "operation-manual-abc123.pdf",
    "Video: A Video": "a-video-def456.mp4",
    "Gone": "deleted-since.pdf",
    "Dodgy": "notes.exe",
    "Escape": "../../../etc/passwd",
    "Absolute": "/etc/passwd",
}))

print("\nwhat was uploaded is served")
ok("a stored PDF resolves", original_path("Operation Manual").endswith(
    "operation-manual-abc123.pdf"))
ok("a stored video resolves", original_path("Video: A Video").endswith(".mp4"))
ok("and it resolves to a real file", os.path.isfile(original_path("Operation Manual")))

print("\nand nothing else is")
check("a document with no entry", original_path("Installation Manual"), None)
check("an entry whose file has been deleted", original_path("Gone"), None)
# The extension whitelist is the second gate: a manifest is written by an
# authenticated upload, but a servable-types list is a decision, not a guess.
check("a file type the add-on does not serve", original_path("Dodgy"), None)

print("\nthe name from the browser never becomes a path")
# These are the attacks the realpath check exists for. A manifest should never
# contain them -- the point is that it does not matter if one does.
check("a relative escape is refused", original_path("Escape"), None)
check("an absolute path is refused", original_path("Absolute"), None)
# The document name itself is only ever a dict key, so traversal in the *name*
# cannot reach the filesystem at all.
for attack in ("../../etc/passwd", "..\\..\\windows\\system32",
               "/etc/shadow", "Operation Manual/../../../etc/passwd"):
    check(f"a traversal name finds nothing: {attack[:28]}",
          original_path(attack), None)

print("\nthe endpoint that writes them is guarded like the index upload")
up = top("upload_original")
ok("the upload endpoint exists", up is not None)
src = ast.unparse(up)
ok("it requires the service key", "_guard(" in src)
ok("it rejects a type it could not serve later", "_ORIGINAL_TYPES" in src)
ok("it stores under a slug, not the document name", "slug" in src)
ok("and it never writes the supplied filename",
   'os.path.join(ORIGINALS_DIR, stored)' in src)

serve = top("original_file")
ok("the serving endpoint exists", serve is not None)
src = ast.unparse(serve)
ok("it goes through the checked lookup", "_original_path(" in src)
ok("it 404s rather than guessing", "404" in src)
# Inline, or the browser downloads the PDF instead of opening it -- and #page=N
# only works in a viewer.
ok("it serves inline so #page= works", "inline" in src)

print("\nthe browser only offers a link when there is something behind it")
html = (ROOT / "addon" / "webroot" / "index.html").read_text()
ok("there is one citation renderer", "function citeHtml(" in html)
ok("it links to the original", "documents/file?doc=" in html)
ok("at the cited page", '"#page="' in html)
ok("only when the original is there", "if(sx.original)" in html)
ok("the indexed text stays available too", 'data-doc=' in html)
ok("it is shared across script blocks", "window.bkonCite" in html)

print(f"\n{_pass} passed, {_fail} failed")
sys.exit(1 if _fail else 0)
