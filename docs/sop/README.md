# SOP deck — how it is built, and how to rebuild it

`SUCCESS-Bank-Ticketing-SOP.pptx` is generated, not hand-made. Every screenshot
in it came from the application running locally. If a screen changes, rebuild
the deck rather than editing the file — an edited `.pptx` is overwritten by the
next build.

**Hand the PDF to readers.** `SUCCESS-Bank-Ticketing-SOP.pdf` is built from the
same `.pptx` and looks the same in every viewer. A `.pptx` is a description
that each viewer interprets for itself, and lightweight mobile preview apps
interpret this one badly — ghosting shapes from one slide onto the next and
pairing a slide with another slide's screenshot. None of that is in the file;
it is the previewer running out of room. The PDF is drawn rather than
interpreted, so it cannot happen there.

The brief the deck was built to is `docs/sop-deck-prompt.md`.

## Files

| File | What it does |
|---|---|
| `capture-screens.py` | Logs in as each role and screenshots every screen, recording the **real bounding box** of each element a callout points at |
| `build-deck.py` | Assembles the 58-slide deck from those screenshots and `screens/manifest.json` |
| `audit-layout.py` | Checks a built deck for text overflow, overlapping boxes, off-slide shapes and numerals that do not fit their marker |
| `render-pdf.py` | Renders the deck to PDF — the copy to distribute |
| `render-preview.py` | Renders slides to PNG so a build can be eyeballed without PowerPoint |
| `screens/` | The captured PNGs and `manifest.json` (callout coordinates) |

## Rebuilding

You need Postgres, an S3-compatible store, the backend, and the frontend all
running against a **seeded** database — an empty dashboard teaches nothing.

```bash
# 1. seed, then generate real audit rows by driving the API (the seeder writes
#    rows directly, so it produces no audit trail of its own)
python backend/scripts/seed_dev.py --reset

# 2. capture. Needs /tmp/branch_ticket.txt and /tmp/rich_ticket.txt to hold the
#    ids of one ticket raised by the branch user and one worked-on ticket.
python docs/sop/capture-screens.py docs/sop/screens

# 3. build, check, look
python docs/sop/build-deck.py docs/sop/screens docs/sop/SUCCESS-Bank-Ticketing-SOP.pptx
python docs/sop/audit-layout.py docs/sop/SUCCESS-Bank-Ticketing-SOP.pptx     # expect 0 findings
python docs/sop/render-pdf.py docs/sop/SUCCESS-Bank-Ticketing-SOP.pptx \
       docs/sop/SUCCESS-Bank-Ticketing-SOP.pdf
python docs/sop/render-preview.py docs/sop/SUCCESS-Bank-Ticketing-SOP.pptx /tmp/preview
```

Rebuild the PDF whenever the deck changes; the two are committed together and
a stale PDF is worse than none.

`build-deck.py` stamps the current commit onto the title and closing slides. It
reads it from git; pass a third argument to override.

## Two things that are easy to get wrong

**Wait for the page, do not sleep.** `capture-screens.py` waits for `Loading…`
text *and* for Tailwind `animate-pulse` skeletons to disappear. A fixed delay
looks like it works and quietly captures half-rendered dashboards — that is how
a set of blank grey cards ended up in an earlier build, and how a genuine
403-on-every-KPI bug stayed hidden behind them.

**Never guess a callout position.** Callout coordinates come from the browser.
If a locator does not match, the callout is dropped and reported at the end of
the run; it is not placed at an estimate. A marker pointing at the wrong control
is worse than no marker.

## Checking a build

`audit-layout.py` should report **0 findings**. It catches the class of defect
that is invisible until someone opens the file: a label that needs more height
than its box, two text boxes on top of each other, a digit too wide for its
circle. It measures in DejaVu while PowerPoint lays out in Calibri, so it errs
towards reporting problems that will not appear — findings are worth reading,
but a clean run is the bar.

**Screenshots are embedded at the size they are shown** (about 200dpi) and
palette-encoded, not at the 2880x1800 capture size. That is a third of the
file for no visible difference, and the original full-resolution captures stay
in `screens/`. Check the smallest type in a rebuilt deck if you raise the
compression.

`render-preview.py` is a proof sheet, not a faithful renderer. It draws what the
file actually stores, which is the point: it shows the numeral squeezed out of
its circle rather than the one PowerPoint would helpfully re-centre.
