"""Reading the documents as they actually are: mostly pictures.

The BKON documents are service training decks, screenshot walkthroughs and
wiring diagrams. Measured across the 49 stored PDFs: 717 pages carrying 297k
characters of text, and **620 of those pages carry a diagram, a screenshot or a
photograph**. A text-only index of this corpus is not a thin index — it is an
index of the captions of a picture book.

So this module does two things to a stored PDF:

*   pulls the text out **per page**, which makes a citation land on the page it
    came from rather than somewhere in the document;
*   renders the pages that carry a picture, so they can be shown to the user and
    described by a model that can see.

A page is rendered whole rather than having its embedded images pulled out
individually. A slide with a screenshot and a label beneath it is one idea, and
one image of the page carries it; the 421 sub-images inside the StepByStep
walkthrough are fragments of screenshots, and none of them means anything alone.

Pure over its inputs -- it takes bytes and returns data. The service decides
where to store things; the model does the describing.
"""
from __future__ import annotations

import hashlib
import io
import re
from dataclasses import dataclass, field

#: Below this, an image on the page is furniture -- a logo, a rule, a bullet.
#: Measured against the corpus: the real diagrams and screenshots are all
#: comfortably larger, and the repeated brand marks are all smaller.
_MIN_IMAGE_PX = 220

#: A page with this many vector drawing operations is a diagram even if it has
#: no raster image on it at all -- the air/water flow schematics are drawn, not
#: photographed.
_MIN_DRAWINGS = 40

#: Enough to read a screenshot's UI text without producing megabyte PNGs. The
#: corpus renders at roughly 90 KB a page here.
RENDER_DPI = 110


@dataclass(slots=True)
class Page:
    """One page of a document: its text, and its picture if it has one."""

    number: int                       # 1-based, as a citation would say it
    text: str
    visual: bool = False
    png: bytes = b""
    digest: str = ""                  # of the rendered page, for de-duplication


@dataclass(slots=True)
class Extract:
    doc: str
    pages: list[Page] = field(default_factory=list)

    @property
    def visual_pages(self) -> list[Page]:
        return [p for p in self.pages if p.visual]


def extract(doc: str, pdf_bytes: bytes, *, render: bool = True,
            dpi: int = RENDER_DPI) -> Extract:
    """Text per page, and a rendering of every page that carries a picture.

    Raises RuntimeError if PyMuPDF is missing, so a deployment without it fails
    with a sentence rather than an ImportError halfway down a stack trace.
    """
    try:
        import pymupdf
    except ImportError as ex:                        # pragma: no cover
        raise RuntimeError(
            "PyMuPDF is not installed; the add-on cannot read PDFs") from ex

    out = Extract(doc=doc)
    with pymupdf.open(stream=io.BytesIO(pdf_bytes), filetype="pdf") as pdf:
        for i, page in enumerate(pdf, start=1):
            text = (page.get_text("text") or "").strip()
            big = [im for im in page.get_images(full=True)
                   if im[2] >= _MIN_IMAGE_PX and im[3] >= _MIN_IMAGE_PX]
            visual = bool(big) or len(page.get_drawings()) > _MIN_DRAWINGS
            p = Page(number=i, text=text, visual=visual)
            if visual and render:
                p.png = page.get_pixmap(dpi=dpi).tobytes("png")
                p.digest = hashlib.sha1(p.png).hexdigest()
            out.pages.append(p)
    return out


#: What to ask about a page. Written for retrieval rather than for a reader: the
#: description is indexed and searched, so it should contain the words someone
#: would use when they have the problem the page solves. "Describe this image"
#: gets prose about layout; this asks for the content.
CAPTION_PROMPT = """This is one page from a service or training document for the
BKON Craft Brewer, a commercial vacuum coffee brewer.

Describe what the page shows, so that a technician searching for it later can
find it. Cover:
- what the picture is (a wiring diagram, a screenshot of the machine's display,
  a photograph of a part, an exploded parts view, a flow schematic, a table)
- the specific parts, menu items, error codes, numbers or labels visible in it
- what task it would help someone do

Write 2-4 sentences of plain prose. No preamble, no markdown, no bullet points.
If the page carries no useful picture -- a title slide, a logo, a blank page --
reply with exactly: SKIP"""

#: A short handle for the figure, shown as its label in the UI.
LABEL_PROMPT = """In 3-7 words, title this page as a figure caption would.
No quotes, no trailing full stop. Examples: "Brew chamber exploded view",
"Error code list, C:3 faults", "Water flow schematic"."""

SKIP = "SKIP"

#: A second pass over a picture, for the things a description throws away.
#:
#: A description is prose, and prose loses exactly what is most useful about
#: these pages: the machine's own dialog text, part numbers, valve labels. The
#: error-code pages are the clearest case -- the left half is real PDF text, but
#: the *photograph* of the display carries the wording the machine actually
#: shows and the service number to call, and none of that is in the text layer.
#:
#: Asked as one call with several fields rather than several passes, because a
#: page is looked at once either way and the model already has it in front of it.
EXTRACT_PROMPT = """Read this page from a BKON Craft Brewer service document and
return ONLY a JSON object, no other text, with exactly these keys:

{"visible_text": "", "codes": [], "parts": [], "labels": []}

- visible_text: every word legible in the pictures on this page, transcribed
  verbatim -- screen messages, callouts, labels, part numbers, phone numbers.
  Do not summarise and do not add anything that is not written there. Use "" if
  the page has no pictures with words in them.
- codes: for each error or fault code shown, an object
  {"code": "C:3 M:5", "title": "Chamber Not Sealed", "cause": "", "remedy": "",
   "message": ""} where message is the exact on-screen text if one is shown.
- parts: for each part listed, {"number": "19006169", "name": "Connector, Elbow"}
- labels: for each labelled component in a diagram,
  {"label": "V5", "name": "Proportional Valve"} -- only where the page says what
  the label means. Do not guess from the letter.

Use empty lists for anything the page does not contain. Copy text exactly as
written; never invent a part number, a code or a meaning."""


def parse_facts(raw: str) -> dict:
    """The extraction JSON, defensively.

    A model asked for JSON usually returns JSON, sometimes fenced, occasionally
    with a sentence in front. Anything unparseable becomes empty rather than an
    exception -- one page's bad output should cost that page, not the run.
    """
    import json

    text = (raw or "").strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    else:
        start, depth = text.find("{"), 0
        if start < 0:
            return _empty_facts()
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    text = text[start:i + 1]
                    break
    try:
        obj = json.loads(text)
    except ValueError:
        return _empty_facts()
    if not isinstance(obj, dict):
        return _empty_facts()

    out = _empty_facts()
    out["visible_text"] = str(obj.get("visible_text") or "").strip()[:4000]
    for key, fields in (("codes", ("code", "title", "cause", "remedy", "message")),
                        ("parts", ("number", "name")),
                        ("labels", ("label", "name"))):
        for row in (obj.get(key) or [])[:60]:
            if not isinstance(row, dict):
                continue
            clean = {f: str(row.get(f) or "").strip()[:400] for f in fields}
            # The first field is the identity of the row; without it the row
            # says nothing and would only pollute a lookup.
            if clean[fields[0]]:
                out[key].append(clean)
    return out


def _empty_facts() -> dict:
    return {"visible_text": "", "codes": [], "parts": [], "labels": []}


def is_skip(caption: str) -> bool:
    """Did the model say there is nothing worth indexing here?

    Checked loosely: models append a full stop, or wrap it in a sentence. A
    page wrongly kept is clutter in the index; a page wrongly dropped is
    invisible. Both are cheap, so this errs toward believing the model.
    """
    t = (caption or "").strip().strip(".\"' ").upper()
    # As a whole word, or "Skipping the purge is covered on page 4" reads as a
    # refusal and a real description is silently thrown away.
    return re.match(r"SKIP\b", t) is not None


def as_passage(doc: str, page: int, caption: str, figure_id: str) -> dict:
    """A described figure, in the same shape as a text passage.

    Figures go into the same index as the text on purpose. A question like
    "where does the drain line connect?" should be able to match a schematic,
    and it only can if the schematic's description is sitting in the index next
    to the prose -- searched the same way, ranked against it, cited beside it.
    """
    return {"doc": doc, "page": page, "text": caption,
            "kind": "figure", "figure": figure_id}
