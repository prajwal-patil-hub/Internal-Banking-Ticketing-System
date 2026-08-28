"""Draw the recorded callout boxes onto the screenshots, to check aim.

The other two checkers answer "does it fit" and "is it in the right place on
the slide". Neither can answer the question that actually matters: is the
marker pointing at the thing its label describes?

A callout can be located successfully and still be wrong — a CSS locator that
matches a different element returns a perfectly valid bounding box for the
wrong control. This draws each recorded box and its number over the capture so
that misaiming is visible rather than inferred.

    python docs/sop/overlay-callouts.py docs/sop/screens /tmp/overlays
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SHOTS = Path(sys.argv[1])
OUT = Path(sys.argv[2])
OUT.mkdir(parents=True, exist_ok=True)

ACCENT = (194, 91, 46)
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

manifest = json.loads((SHOTS / "manifest.json").read_text())
rows = []

for name, entry in sorted(manifest.items()):
    path = SHOTS / entry["file"]
    if not path.exists():
        print(f"  missing: {entry['file']}")
        continue
    im = Image.open(path).convert("RGB")
    W, H = im.size
    d = ImageDraw.Draw(im)
    big = ImageFont.truetype(FONT, 46)

    # Same reading-order sort the deck applies, so the numbers here are the
    # numbers that will ship. Previewing capture order would show an ordering
    # problem that does not exist, or hide one that does.
    def _marker_y(c: dict) -> float:
        return c.get("y0", 0.0) + 0.045 if c.get("h", 0) > 0.45 else c.get("y", 0.5)

    ordered = sorted(entry["callouts"],
                     key=lambda c: (round(_marker_y(c) / 0.06), c.get("x0", c.get("x", 0))))

    for i, c in enumerate(ordered, start=1):
        x0, y0 = c["x0"] * W, c["y0"] * H
        w, h = c["w"] * W, c["h"] * H
        # The recorded element box, so an over-broad locator is obvious.
        d.rectangle([x0, y0, x0 + w, y0 + h], outline=ACCENT, width=5)
        # The marker goes where the deck will put it: beside a small element,
        # near the top of a tall region.
        cy = _marker_y(c) * H
        cx = max(28, x0 - 34)
        d.ellipse([cx - 28, cy - 28, cx + 28, cy + 28], fill=ACCENT)
        d.text((cx, cy), str(i), font=big, fill=(255, 255, 255), anchor="mm")

    im.thumbnail((900, 900))
    im.save(OUT / f"{name}.png")
    rows.append((name, len(entry["callouts"])))

print(f"{len(rows)} overlays -> {OUT}")
for n, c in rows:
    print(f"  {n:34} {c} callout(s)")
