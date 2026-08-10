# The documents, and reading them as pictures

How the add-on turns 52 service documents into something answerable, with
citations you can open and diagrams the assistant can send you.

The premise, measured rather than assumed: across the 49 stored PDFs there are
**717 pages carrying 297k characters of text, and 620 of those pages carry a
diagram, a screenshot or a photograph.** One page of the air/water flow deck has
226 characters of extractable text and a complete hydraulic schematic on it —
V1 through V13, three tank bodies, the brew chamber, both drain paths.

A text-only index of this corpus is not a thin index. It is an index of the
captions of a picture book. That is why 16 documents had two passages or fewer
while their PDFs ran to dozens of pages, and it is the reason for everything
below.

---

## The stages

Each is separately runnable and resumable, because they differ enormously in
cost. Extraction is a minute; describing is hundreds of model calls.

```
   upload            reindex              caption            extract
originals ──▶ text per page + ──▶ what each picture ──▶ codes · parts ·
  (PDFs)      rendered pages       shows, in prose      labels · verbatim text
                    │                      │                     │
                    └──────────────────────┴─────────────────────┘
                                      │
                              the passage index
                        (prose and pictures, ranked together)
```

### 1. Upload the originals

```bash
python3 scripts/upload_originals.py --dir /path/to/archive \
    --url http://homeassistant.local:9621 --key YOUR_SERVICE_KEY
```

Matched to indexed documents by filename (`Operation Manual.pdf` → the document
`Operation Manual`), videos by their `.info.json` title. Unmatched files are
listed and skipped — a file the index has never heard of cannot be cited, so
storing it only costs space.

The add-on writes them, not the script: `/share` belongs to root. `--dry-run`
shows what would go; `--prune` removes originals for documents no longer
indexed.

### 2. Reindex — `POST /documents/reindex`

Extracts text **per page**, so a citation lands on the page it came from, and
renders every page carrying a picture. About a minute for the whole corpus, and
free.

A page qualifies as visual three ways: one substantial image, several modest
ones adding up, or enough vector drawing to be a schematic. The middle case
exists because of the spare parts catalogue — no single photo on those pages is
large and the pages are nothing but photos. **The first version of this rule
demanded 220px in both dimensions and silently excluded all nine catalogue
pages**, whose photographs are about 300×145.

Pages are rendered **whole** rather than having embedded images pulled out. A
slide with a screenshot and a label beneath it is one idea; the StepByStep
walkthrough's 421 sub-images are fragments of screenshots and none means
anything alone.

> A reindex carries forward everything already known about a figure and
> overwrites only what it recomputes. It once rebuilt each entry by naming the
> fields to keep and destroyed 616 pages of extracted data. Do not enumerate.

### 3. Caption — `POST /documents/caption?limit=25`

Sends each rendered page to a vision model and asks what it shows, in the words
a technician would search for — not "describe this image", which returns prose
about layout. A page with nothing useful comes back `SKIP` and is remembered as
skipped rather than retried.

Descriptions go into the **same index as the prose** and are ranked against it.
A question about a drain line should be able to match a schematic, and it only
can if the schematic's description sits next to the text.

Needs a model that can see. `gemma4:31b` reads menu items straight off a
screenshot of the machine's display; a model that cannot raises
`VisionUnsupported` immediately rather than failing 616 times identically.

### 4. Extract — `POST /documents/extract?limit=20`

A second look, for what a description throws away. Prose loses exactly what is
most useful here: the wording the machine puts on its own screen, part numbers,
what a valve label means.

The error-code pages make the case. `C:3 M:5` has 148 characters of extractable
text; the photograph beside it contains *"Brew chamber not closed. Check the
purge valve… call service at 1-855-353-7378 - option 1."* — and that service
number appears nowhere else in 52 documents.

Four fields per page, one call:

| Field | What |
|---|---|
| `visible_text` | every legible word, verbatim — joins the searchable index |
| `codes` | error code, title, cause, remedy, exact on-screen message |
| `parts` | part number and name |
| `labels` | a diagram label and what it stands for |

Unparseable output costs that page, not the run. A row with no identity — a part
with no number — is dropped rather than stored blank.

Run `reindex` again afterwards to fold the transcriptions into the index.

---

## What comes out

**A searchable index** where roughly half the passages are things that were
pixels. "locking handle is down" now finds the page that says it.

**`GET /facts`** — codes, parts and labels, de-duplicated across pages, each row
citing every page it appeared on. Roughly 40 codes, 146 parts, 210 labels.

**Citations that open the real document.** *Open original ↗* goes to the actual
PDF at the cited page (`#page=N`, served inline so the browser's viewer takes
it). The indexed text stays available as *Text*, since it is what the answer was
drawn from and is searchable in a way a scan is not.

**Multi-page procedures, linked.** A run is a stretch of consecutive illustrated
pages in one document. Crude-sounding, and it works because an unillustrated
page breaks the run — which is exactly what separates one fault from the next in
the error-code deck, where each gets a symptom page and a remedy page. 53 runs
cover 474 of the described figures, and the `Error Codes` pairs fall out as
*"Purge valve and C:3 M:5 error"* → *"Purge valve cleaning and interface
guide"*. A surfaced figure shows *4 of 16* with ‹ › to step through it.

Runs are named from words their labels share, with the brand name excluded
because it is on nearly every label. A run whose pages share nothing gets
"pages 12–18" — honest, where an invented title would not be.

**Two tools for the assistant.** `show_diagram` when a picture *is* the answer —
"which valve is V5?" is better served by the schematic than by three sentences.
`look_up` for exact identifiers, because `19006211` and `C:3 M:5` are not prose,
embeddings are bad at them, and near-enough is wrong.

Neither lets the model invent anything: figures and rows are looked up from the
index, so the assistant reports what the documents say.

---

## Two cautions

**These values were read off photographs by a model.** One misread a service
phone number — *1-855-353-7378* transcribed as *1-800-553-7876*. Where sightings
of the same code disagree, both are kept under `variants` and the assistant is
told to say the documents disagree rather than pick one. A confident wrong
number to call is worse than an acknowledged uncertainty.

**The documents are not in this repository.** They are the owner's archive of
their own machine's documentation, uploaded to their own device and served only
through Home Assistant's authenticated ingress. The index is git-ignored, and
nothing here reproduces vendor text.
