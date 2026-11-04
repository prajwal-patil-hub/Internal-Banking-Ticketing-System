"""Group parsed blocks into retrievable passages.

Fixed-width chunking is the default everywhere and it is wrong for policy
documents: it cuts mid-clause, so the half that says "within 45 days" is
indexed apart from the half that says which transaction type it applies to.
Both halves retrieve; neither is correct.

So the rules here are, in priority order:

1. **Split on headings first.** A section boundary is a real semantic
   boundary — the author put it there.
2. **Never split a table row away from the rows around it.** A row separated
   from its header is data without column names.
3. **Only then fall back to size**, and when falling back, break on sentence
   boundaries rather than character counts.

Every chunk carries its `heading_path` ("3. Chargebacks > 3.2 Timelines") both
as a stored field *and* prefixed into the embedded text. The prefix matters:
the vector has to encode the context, or a passage retrieved on its own scores
as though the section it belongs to did not exist.

Size is measured in characters, not tokens. A real tokenizer would be more
accurate, but it would mean shipping a tokenizer that must stay in lockstep
with whichever embedding model is configured; ~4 chars/token is close enough
for a chunk-size heuristic and has no version to drift.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.services.kb_parsing import Block

#: Sentence-ish boundaries. Deliberately conservative: it requires the
#: terminator to be followed by whitespace and a capital or digit, so "Rs. 500"
#: and "clause 3.2 above" do not become split points.
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")


@dataclass
class Chunk:
    ordinal: int
    content: str
    heading_path: str | None = None
    page_from: int | None = None
    page_to: int | None = None
    #: Kinds of block that went into this chunk, used by tests to assert that
    #: table rows were not merged into prose.
    kinds: set[str] = field(default_factory=set)

    @property
    def char_count(self) -> int:
        return len(self.content)

    def embedding_text(self) -> str:
        """What actually gets embedded — heading path prefixed onto content."""
        if self.heading_path:
            return f"{self.heading_path}\n\n{self.content}"
        return self.content


def _heading_path(stack: list[tuple[int, str]]) -> str | None:
    return " > ".join(text for _lvl, text in stack) if stack else None


def _split_oversized(text: str, limit: int, overlap: int) -> list[str]:
    """Break a too-long run of prose on sentence boundaries.

    Overlap repeats the tail of the previous piece at the head of the next so
    a fact spanning the seam is retrievable from either side.
    """
    if len(text) <= limit:
        return [text]

    sentences = _SENTENCE_END.split(text)
    pieces: list[str] = []
    current = ""

    for sentence in sentences:
        # A single sentence longer than the limit cannot be split further on
        # sentence boundaries; hard-cut it rather than emitting one enormous
        # chunk that dominates every retrieval it appears in.
        if len(sentence) > limit:
            if current:
                pieces.append(current.strip())
                current = ""
            for i in range(0, len(sentence), limit):
                pieces.append(sentence[i : i + limit].strip())
            continue

        candidate = f"{current} {sentence}".strip() if current else sentence
        if len(candidate) > limit and current:
            pieces.append(current.strip())
            tail = current[-overlap:] if overlap else ""
            current = f"{tail} {sentence}".strip() if tail else sentence
        else:
            current = candidate

    if current.strip():
        pieces.append(current.strip())
    return [p for p in pieces if p]


def _split_rows(text: str, limit: int) -> list[str]:
    """Group table rows into chunks without ever cutting inside a row.

    Row boundaries are the only safe split points here, so a single row longer
    than the limit is hard-cut as a last resort — a chunk that cannot be
    indexed at all is worse than one with a mangled column.
    """
    parts: list[str] = []
    current: list[str] = []
    size = 0

    for row in text.split("\n"):
        if len(row) > limit:
            if current:
                parts.append("\n".join(current))
                current, size = [], 0
            for i in range(0, len(row), limit):
                parts.append(row[i : i + limit])
            continue

        if current and size + len(row) + 1 > limit:
            parts.append("\n".join(current))
            current, size = [], 0
        current.append(row)
        size += len(row) + 1

    if current:
        parts.append("\n".join(current))
    return [p for p in parts if p.strip()]


def chunk_blocks(
    blocks: list[Block],
    *,
    max_chars: int,
    overlap_chars: int,
) -> list[Chunk]:
    """Turn parsed blocks into chunks. See the module docstring for the rules."""
    chunks: list[Chunk] = []
    heading_stack: list[tuple[int, str]] = []

    # Buffer of blocks accumulating into the current chunk.
    buffer: list[Block] = []
    buffer_len = 0

    def flush() -> None:
        nonlocal buffer, buffer_len
        if not buffer:
            return

        path = _heading_path(heading_stack)
        pages = [b.page for b in buffer if b.page is not None]
        kinds = {b.kind for b in buffer}
        text = "\n".join(b.text for b in buffer).strip()

        if not text:
            buffer, buffer_len = [], 0
            return

        if "table_row" in kinds:
            # Table rows are not split on sentence boundaries — that would cut
            # between columns. They are still size-capped, though: an earlier
            # version emitted them verbatim, so one 30 MB line in a CSV became
            # one 30 MB chunk. That chunk would be sent whole to the embedding
            # model, pasted whole into every prompt that retrieved it, and
            # rejected outright by the GIN `to_tsvector` index above ~1 MB,
            # failing the insert. Unbounded is not the same as unsplit.
            parts = _split_rows(text, max_chars)
        else:
            parts = _split_oversized(text, max_chars, overlap_chars)

        for part in parts:
            chunks.append(
                Chunk(
                    ordinal=len(chunks),
                    content=part,
                    heading_path=path,
                    page_from=min(pages) if pages else None,
                    page_to=max(pages) if pages else None,
                    kinds=set(kinds),
                )
            )
        buffer, buffer_len = [], 0

    for block in blocks:
        if block.kind == "heading":
            # A heading ends the previous section — rule 1.
            flush()
            # Pop siblings and deeper levels, then push this one.
            while heading_stack and heading_stack[-1][0] >= block.level:
                heading_stack.pop()
            heading_stack.append((block.level, block.text))
            continue

        # Mixing a table row into surrounding prose makes the prose
        # unsplittable and the table unreadable — keep the two apart.
        if buffer and (block.kind == "table_row") != ("table_row" in {b.kind for b in buffer}):
            flush()

        projected = buffer_len + len(block.text) + 1
        if buffer and projected > max_chars:
            flush()

        buffer.append(block)
        buffer_len += len(block.text) + 1

    flush()

    # Ordinals must be dense and gap-free: the unique constraint is
    # (version_id, ordinal), and retrieval orders neighbours by it.
    for i, chunk in enumerate(chunks):
        chunk.ordinal = i

    return chunks
