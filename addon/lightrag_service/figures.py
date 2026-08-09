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
