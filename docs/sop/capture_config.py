"""Capture settings shared by every screenshot script.

**Why this file exists.** `capture-screens.py` shot at 1440x900 and
`capture-kb-screen.py` shot at 1440x1000, and one knowledge-base screen was
captured taller still. Nothing warned about it; each script was internally
consistent, and each produced correct-looking screenshots.

The damage only appears when the screenshots are put side by side. The
walkthrough renders every screen at the same width, so a 2880x2000 capture
comes out 11% taller than a 2880x1800 one, and the 2880x2742 one 52% taller.
The sidebar is identical markup in all of them and occupies the same 15.8% of
the frame — but stretched over a taller frame it reads as a *different,
narrower* sidebar. The tall shot also shows content below the fold that no
other screen does, which reads as headers appearing and disappearing between
slides of the same role.

So: one viewport, one scale factor, one rule about full-page captures, in one
place both scripts import. `check_uniform` then proves it held, because a
convention nobody checks is exactly how the drift happened.
"""

from __future__ import annotations

from pathlib import Path

#: The one viewport. Every screen in the deck and the walkthrough is shot at
#: this size, so they can be laid side by side without any being rescaled.
VIEWPORT = {"width": 1440, "height": 900}

#: 2x, for legible small type when a screenshot is placed at ~200dpi in the
#: deck. Changing this changes every stored PNG's pixel size.
DEVICE_SCALE_FACTOR = 2

#: What every capture must therefore measure.
EXPECTED_SIZE = (
    VIEWPORT["width"] * DEVICE_SCALE_FACTOR,
    VIEWPORT["height"] * DEVICE_SCALE_FACTOR,
)

#: Never pass `full_page=True`. A full-page shot of a long screen comes out
#: near-square, overflows a 16:9 slide, and — because callout coordinates are
#: measured against `innerHeight` — puts markers in the wrong place.
FULL_PAGE = False


#: The one deliberate full-page capture, and why it is allowed to differ.
#:
#: `70-knowledge-base.png` is a full-height shot of the knowledge-base screen
#: used by `build-kb-slide.py`, where a single tall image is the point. It is
#: *not* used by the walkthrough — placed among viewport-sized screens it was
#: 52% taller than its neighbours, which is what made the same sidebar read as
#: a different component. Exempt here so the deck keeps building; excluded from
#: the walkthrough's journey so it cannot cause that again.
EXEMPT: frozenset[str] = frozenset({"70-knowledge-base.png"})


def check_uniform(
    directory: str | Path,
    expected: tuple[int, int] = EXPECTED_SIZE,
    exempt: frozenset[str] = EXEMPT,
) -> list[str]:
    """Return one problem string per screenshot that is the wrong size.

    An empty list means every capture in `directory` matches. Callers should
    treat a non-empty list as a build failure rather than a warning: a
    mismatched capture is not a cosmetic issue, it is a screen that will look
    like a different application.
    """
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover — Pillow is a capture-time dep
        return ["Pillow is not installed, so capture sizes could not be checked"]

    problems: list[str] = []
    for png in sorted(Path(directory).glob("*.png")):
        if png.name in exempt:
            continue
        with Image.open(png) as im:
            if im.size != expected:
                problems.append(
                    f"{png.name}: {im.size[0]}x{im.size[1]}, expected "
                    f"{expected[0]}x{expected[1]}"
                )
    return problems
