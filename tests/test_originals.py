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
ok("it stores under a derived key, not the document name", "_doc_key(" in src)
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

print("\nthe upload only accepts documents the index knows")
# Two bugs found on the first real upload, both of which produced an original
# that no citation could ever reach.
src = ast.unparse(top("upload_original"))
ok("the document name is not stripped", "doc = (doc or '').strip()" not in src)
# One indexed document really is named with a trailing space. Stripping it
# filed the original under a name nothing asks for, and it silently had none.
ok("blank is still rejected", "if not (doc or '').strip()" in src)
ok("an unindexed document is refused", "kb.documents" in src and "404" in src)

# Orphans have to be *reported*, or the prune that removes them cannot find
# them: the `originals` list is filtered to indexed documents, so anything
# orphaned is by definition absent from it.
docs_ep = None
for n in tree.body:
    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "documents":
        docs_ep = n
ok("the document listing exists", docs_ep is not None)
src = ast.unparse(docs_ep)
ok("it reports which documents have an original", "'originals'" in src)
ok("and which stored originals are orphaned", "'orphans'" in src)

rm = top("delete_original")
ok("an upload can be undone", rm is not None)
src = ast.unparse(rm)
ok("removal is key-guarded too", "_guard(" in src)
ok("it removes the file, not just the entry", "os.remove(" in src)
ok("and it goes through the checked lookup", "_original_path(" in src)

print("\ntwo documents one space apart do not become one")
# This corpus really does contain "Service Training (Part II)" and
# "Service Training ( Part II)". They slug identically, so figure ids built
# from the slug collided and 21 figures overwrote each other.
key_fn = top("_doc_key")
ok("there is a unique document key", key_fn is not None)
env2 = {}
exec(compile(ast.Module(body=[top("_slug"), key_fn], type_ignores=[]),
             "<key>", "exec"), env2)
slug, doc_key = env2["_slug"], env2["_doc_key"]

a, b = "Service Training (Part II)", "Service Training ( Part II)"
check("their slugs really do collide", slug(a), slug(b))
ok("but their keys do not", doc_key(a) != doc_key(b))
check("the key is stable across calls", doc_key(a), doc_key(a))
ok("and it stays filesystem-safe",
   all(c.isalnum() or c == "-" for c in doc_key("Air/Water: Flow & Return")))
# Long names must not collide once truncated either.
long_a = "A" * 90 + "one"
long_b = "A" * 90 + "two"
ok("long names stay distinct", doc_key(long_a) != doc_key(long_b))

print("\na reindex does not lose documents that have no PDF")
# The three videos have no pages to extract. Rebuilding from the PDFs alone
# deleted them from the index, which is data loss dressed up as a refresh.
re_src = ast.unparse(top("reindex"))
ok("passages for non-PDF documents are carried across", "carried" in re_src)
ok("and reported, so the carry-over is visible", "carried_over" in re_src)

print("\nserving a figure is guarded exactly like serving an original")
# Same shape of risk: a file handed to a browser on the strength of an id the
# browser supplied. The id is looked up in the figure index and the resolved
# path checked to be inside the figures directory.
fp = top("_figure_path")
ok("the figure lookup exists", fp is not None)
fsrc = ast.unparse(fp)
ok("it refuses an id it does not know", "_figures()" in fsrc)
ok("it checks the resolved path is inside the directory", "commonpath" in fsrc)
ok("and that the file is really there", "isfile" in fsrc)

env3 = {"os": os, "FIGURES_DIR": tmp, "_FIG_INDEX": "figures.json"}
exec(compile(ast.Module(body=[top("_figures"), fp], type_ignores=[]),
             "<fig>", "exec"), env3)
figure_path = env3["_figure_path"]
Path(tmp, "figures.json").write_text(json.dumps({
    "real-p1": {"doc": "D", "page": 1, "caption": "a schematic"},
    "gone-p9": {"doc": "D", "page": 9, "caption": "missing file"},
    "../../etc/passwd": {"doc": "X", "page": 1},
}))
Path(tmp, "real-p1.png").write_bytes(b"\x89PNG\r\n\x1a\n")
ok("a stored figure resolves", (figure_path("real-p1") or "").endswith("real-p1.png"))
check("an unknown id finds nothing", figure_path("nope-p1"), None)
check("a known id whose file is gone finds nothing", figure_path("gone-p9"), None)
check("and an id shaped like a path finds nothing",
      figure_path("../../etc/passwd"), None)

print("\nthe agent can send a picture, but never invent one")
chat_fn = None
for n in ast.walk(tree):
    if isinstance(n, ast.AsyncFunctionDef) and n.name == "chat_turn":
        chat_fn = n
show = None
for n in ast.walk(chat_fn):
    if isinstance(n, ast.AsyncFunctionDef) and n.name == "show_diagram":
        show = n
ok("show_diagram is a tool", show is not None)
ssrc = ast.unparse(show)
ok("it searches the index rather than composing an answer", "kb.search(" in ssrc)
ok("it only returns figures that exist", "figs" in ssrc)
ok("it says so when there is nothing to show", "note" in ssrc)
# A tool that can never return anything is worse than no tool.
csrc = ast.unparse(chat_fn)
ok("and it is only offered once figures have been described",
   "v.get('caption')" in csrc and "tools['show_diagram']" in csrc)

print("\ncaptioning is resumable, and fails fast on a blind model")
cap = top("caption_figures")
ok("the captioning endpoint exists", cap is not None)
csrc2 = ast.unparse(cap)
ok("it is key-guarded", "_guard(" in csrc2)
ok("it works in batches", "limit" in csrc2)
ok("it reports what is left", "remaining" in csrc2)
# 616 identical failures is a waste of everyone's time.
ok("a model that cannot see stops the run", "VisionUnsupported" in csrc2)
ok("and a page the model calls useless is remembered, not retried",
   "skipped" in csrc2)

print("\na surfaced figure knows the procedure it belongs to")
seq_fn = top("_sequences")
ok("sequences are derived, not stored", seq_fn is not None)
ssrc = ast.unparse(seq_fn)
ok("only described figures count", "caption" in ssrc)
ok("a lone page is not a sequence", "len(run) < 2" in ssrc)
ok("and each page knows its neighbours", "'prev'" in ssrc and "'next'" in ssrc)

brief = top("_seq_brief")
ok("there is one shape for attaching it", brief is not None)
# Attached everywhere a figure can appear, or stepping works in one place and
# not another for no reason the user can see.
for fn in ("_cite", "chat_turn", "list_figures"):
    node = top(fn) or next((n for n in ast.walk(tree)
                            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                            and n.name == fn), None)
    ok(f"{fn} attaches it", "_seq_brief(" in ast.unparse(node))

full = top("sequence")
ok("the whole run can be fetched", full is not None)
ok("it 404s for a figure that is not in one", "404" in ast.unparse(full))

html2 = (ROOT / "addon" / "webroot" / "index.html").read_text()
ok("the browser shows the position in the run", 'class="dg-seq"' in html2)
ok("with previous and next", 'class="pv"' in html2 and 'class="nx"' in html2)
ok("stepping stays inside the figure already on screen",
   'documents/sequence?id=' in html2)
ok("and the ends of a run are not clickable", "disabled" in html2)

print("\na reindex keeps what was learned about a figure")
# It once carried `caption` and `label` across by naming them, which silently
# discarded `facts` -- 616 pages of extraction, destroyed by a refresh. Nothing
# is listed by name now, so a field added later cannot be forgotten here.
re_src2 = ast.unparse(top("reindex"))
ok("prior state is carried wholesale",
   "**old.get(fid) or {}" in re_src2 or "**(old.get(fid) or {})" in re_src2)
ok("and no field is enumerated to keep",
   "'caption': prior.get(" not in re_src2 and '"caption": prior.get(' not in re_src2)
# The bug that made this matter: extraction output lives under `facts`.
ok("so extracted facts survive", "facts" not in re_src2.split("index[fid] =")[1][:200])

print("\none fault, however the document punctuates it")
# The corpus writes the same fault as "C:3 M:5" and "C3:M5". Keyed on the raw
# string they became two entries with different remedies -- and the assistant
# would answer with whichever it happened to find.
facts_src = ast.unparse(top("_facts"))
ok("the code key keeps only what identifies the fault",
   "[^A-Z0-9]" in facts_src)
# A vision model misread a service phone number on one page: 1-855-353-7378
# became 1-800-553-7876. Keeping the first sighting silently would have hidden
# that, and a wrong number to call is a real cost.
ok("fields that disagree are recorded, not smoothed over", "variants" in facts_src)
chat_src = (ROOT / "addon" / "lightrag_service" / "chat.py").read_text()
ok("and the assistant is told to report the disagreement",
   "variants" in chat_src and "disagree" in chat_src)

print(f"\n{_pass} passed, {_fail} failed")
sys.exit(1 if _fail else 0)
