"""Build the role-based SOP deck from the captured screenshots.

Layout rule from the prompt: one screen per slide, screenshot large enough to
read, numbered callouts on the elements that matter, and the same six fields on
every workflow slide (step, action, result, next).
"""
from __future__ import annotations

import sys
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.util import Emu, Inches, Pt

SHOTS = Path(sys.argv[1])
OUT = Path(sys.argv[2])

# --- palette, taken from the application's own theme ------------------------
TEAL = RGBColor(0x0E, 0x4F, 0x4A)
TEAL_D = RGBColor(0x09, 0x38, 0x34)
CREAM = RGBColor(0xF3, 0xEC, 0xE0)
INK = RGBColor(0x1B, 0x2A, 0x33)
MUTE = RGBColor(0x5B, 0x6B, 0x75)
LINE = RGBColor(0xD6, 0xCE, 0xC0)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
ACCENT = RGBColor(0xC2, 0x5B, 0x2E)
OK = RGBColor(0x1E, 0x7A, 0x53)
WARN = RGBColor(0xB4, 0x7A, 0x14)

W, H = Inches(13.333), Inches(7.5)
prs = Presentation()
prs.slide_width, prs.slide_height = W, H
BLANK = prs.slide_layouts[6]

step_no = 0


def _tb(slide, x, y, w, h, text, size=14, bold=False, color=INK,
        align=PP_ALIGN.LEFT, font="Calibri", spacing=1.15, anchor=MSO_ANCHOR.TOP):
    box = slide.shapes.add_textbox(x, y, w, h)
    tf = box.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    lines = text.split("\n")
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = line
        p.alignment = align
        p.line_spacing = spacing
        for r in p.runs:
            r.font.size = Pt(size)
            r.font.bold = bold
            r.font.color.rgb = color
            r.font.name = font
    return box


def _rect(slide, x, y, w, h, fill, line=None, shape=MSO_SHAPE.RECTANGLE):
    s = slide.shapes.add_shape(shape, x, y, w, h)
    s.fill.solid()
    s.fill.fore_color.rgb = fill
    if line is None:
        s.line.fill.background()
    else:
        s.line.color.rgb = line
        s.line.width = Pt(1)
    s.shadow.inherit = False
    return s


def _bg(slide, color=WHITE):
    _rect(slide, 0, 0, W, H, color)


def footer(slide, label):
    _rect(slide, 0, H - Inches(0.42), W, Inches(0.42), CREAM)
    _tb(slide, Inches(0.55), H - Inches(0.34), Inches(9), Inches(0.25),
        "SUCCESS Bank — Internal Ticketing · Standard Operating Procedure",
        size=9, color=MUTE)
    _tb(slide, W - Inches(2.4), H - Inches(0.34), Inches(1.85), Inches(0.25),
        label, size=9, color=MUTE, align=PP_ALIGN.RIGHT)


# ---------------------------------------------------------------- title -----
def title_slide():
    s = prs.slides.add_slide(BLANK)
    _bg(s, TEAL)
    _rect(s, 0, Inches(2.55), W, Inches(0.06), ACCENT)
    _tb(s, Inches(1.0), Inches(1.35), Inches(11), Inches(0.5),
        "STANDARD OPERATING PROCEDURE", size=15, bold=True, color=CREAM)
    _tb(s, Inches(1.0), Inches(1.75), Inches(11), Inches(1.0),
        "SUCCESS Bank — Internal Ticketing", size=40, bold=True, color=WHITE)
    _tb(s, Inches(1.0), Inches(2.95), Inches(10), Inches(1.4),
        "A role-by-role operational guide.\n"
        "Every screen in this deck was captured from the running application.",
        size=17, color=CREAM, spacing=1.35)
    for i, (role, who) in enumerate([
        ("Branch User", "raises the ticket"),
        ("Agent", "works and resolves it"),
        ("Supervisor", "watches SLA and escalations"),
        ("Admin", "configures the system"),
        ("Auditor", "reads everything, changes nothing"),
    ]):
        x = Inches(1.0) + i * Inches(2.28)
        _rect(s, x, Inches(4.75), Inches(2.05), Inches(1.15), TEAL_D)
        _tb(s, x + Inches(0.18), Inches(4.95), Inches(1.7), Inches(0.3),
            role, size=12.5, bold=True, color=WHITE)
        _tb(s, x + Inches(0.18), Inches(5.28), Inches(1.72), Inches(0.55),
            who, size=9.5, color=CREAM, spacing=1.1)
    _tb(s, Inches(1.0), Inches(6.35), Inches(11), Inches(0.3),
        "Version 1.0  ·  Built at commit c554e3c", size=10, color=CREAM)


# -------------------------------------------------------------- section -----
def section(num, title, blurb):
    s = prs.slides.add_slide(BLANK)
    _bg(s, CREAM)
    _rect(s, 0, 0, Inches(0.28), H, TEAL)
    _tb(s, Inches(1.1), Inches(2.6), Inches(2), Inches(0.6),
        f"SECTION {num}", size=13, bold=True, color=ACCENT)
    _tb(s, Inches(1.1), Inches(3.05), Inches(10.5), Inches(0.9),
        title, size=34, bold=True, color=TEAL)
    _tb(s, Inches(1.1), Inches(4.15), Inches(9.5), Inches(1.0),
        blurb, size=15, color=MUTE, spacing=1.3)
    footer(s, f"Section {num}")


# --------------------------------------------------------------- content ----
def content(title, kicker=""):
    s = prs.slides.add_slide(BLANK)
    _bg(s)
    _rect(s, 0, 0, W, Inches(0.95), TEAL)
    _tb(s, Inches(0.55), Inches(0.2), Inches(11.5), Inches(0.35),
        title, size=23, bold=True, color=WHITE)
    if kicker:
        _tb(s, Inches(0.55), Inches(0.6), Inches(11.5), Inches(0.28),
            kicker, size=11.5, color=CREAM)
    return s


# ------------------------------------------------------- workflow slide -----
def workflow(shot, title, callouts, action, result, nxt, role_tag):
    """One screen, one slide. `callouts` = [(x%, y%, label), …]."""
    global step_no
    step_no += 1
    s = prs.slides.add_slide(BLANK)
    _bg(s)
    _rect(s, 0, 0, W, Inches(0.95), TEAL)
    _rect(s, 0, Inches(0.95), W, Inches(0.04), ACCENT)

    _tb(s, Inches(0.55), Inches(0.17), Inches(1.5), Inches(0.3),
        f"STEP {step_no:02d}", size=12, bold=True, color=ACCENT)
    _tb(s, Inches(0.55), Inches(0.46), Inches(9.2), Inches(0.4),
        title, size=20, bold=True, color=WHITE)
    _tb(s, W - Inches(3.3), Inches(0.35), Inches(2.75), Inches(0.3),
        role_tag.upper(), size=11, bold=True, color=CREAM, align=PP_ALIGN.RIGHT)

    # screenshot — left 8.3", preserving the 1440x900 aspect
    img_x, img_y, img_w = Inches(0.45), Inches(1.25), Inches(8.35)
    img_h = img_w * 900 / 1440
    path = SHOTS / shot
    if path.exists():
        _rect(s, img_x - Inches(0.03), img_y - Inches(0.03),
              img_w + Inches(0.06), img_h + Inches(0.06), LINE)
        s.shapes.add_picture(str(path), img_x, img_y, width=img_w)
    else:
        _rect(s, img_x, img_y, img_w, img_h, CREAM, LINE)
        _tb(s, img_x, img_y + img_h / 2, img_w, Inches(0.4),
            f"[ screen not captured: {shot} ]", size=13, color=ACCENT,
            align=PP_ALIGN.CENTER)

    # numbered callout markers over the screenshot
    for i, (px, py, _) in enumerate(callouts, start=1):
        cx = img_x + Emu(int(img_w * px))
        cy = img_y + Emu(int(img_h * py))
        d = Inches(0.29)
        m = _rect(s, cx - d / 2, cy - d / 2, d, d, ACCENT, shape=MSO_SHAPE.OVAL)
        tf = m.text_frame
        tf.text = str(i)
        tf.paragraphs[0].alignment = PP_ALIGN.CENTER
        r = tf.paragraphs[0].runs[0]
        r.font.size, r.font.bold, r.font.color.rgb = Pt(12), True, WHITE

    # right column
    rx, rw = Inches(9.15), Inches(3.7)
    y = Inches(1.25)
    if callouts:
        _tb(s, rx, y, rw, Inches(0.25), "ON THIS SCREEN", size=10, bold=True, color=ACCENT)
        y += Inches(0.34)
        for i, (_, _, label) in enumerate(callouts, start=1):
            d = Inches(0.24)
            m = _rect(s, rx, y + Inches(0.02), d, d, TEAL, shape=MSO_SHAPE.OVAL)
            tf = m.text_frame
            tf.text = str(i)
            tf.paragraphs[0].alignment = PP_ALIGN.CENTER
            r = tf.paragraphs[0].runs[0]
            r.font.size, r.font.bold, r.font.color.rgb = Pt(10), True, WHITE
            box = _tb(s, rx + Inches(0.34), y, rw - Inches(0.34), Inches(0.5),
                      label, size=10.5, color=INK, spacing=1.1)
            y += Emu(max(Inches(0.36), box.text_frame.paragraphs[0].line_spacing and Inches(0.36)))
        y += Inches(0.12)

    for lab, txt, col in (("ACTION", action, TEAL), ("RESULT", result, OK), ("NEXT", nxt, MUTE)):
        _rect(s, rx, y, Inches(0.05), Inches(0.62), col)
        _tb(s, rx + Inches(0.16), y, rw - Inches(0.16), Inches(0.2),
            lab, size=9.5, bold=True, color=col)
        _tb(s, rx + Inches(0.16), y + Inches(0.2), rw - Inches(0.16), Inches(0.55),
            txt, size=11, color=INK, spacing=1.15)
        y += Inches(0.86)

    footer(s, f"Step {step_no:02d}")
    return s


def table(slide, x, y, w, headers, rows, col_w=None, head_fill=TEAL, size=10.5):
    n_r, n_c = len(rows) + 1, len(headers)
    gt = slide.shapes.add_table(n_r, n_c, x, y, w, Inches(0.4) * n_r).table
    if col_w:
        for i, cw in enumerate(col_w):
            gt.columns[i].width = cw
    for c, htxt in enumerate(headers):
        cell = gt.cell(0, c)
        cell.text = htxt
        cell.fill.solid()
        cell.fill.fore_color.rgb = head_fill
        p = cell.text_frame.paragraphs[0]
        p.runs[0].font.size, p.runs[0].font.bold = Pt(size), True
        p.runs[0].font.color.rgb = WHITE
    for r, row in enumerate(rows, start=1):
        for c, val in enumerate(row):
            cell = gt.cell(r, c)
            cell.text = str(val)
            cell.fill.solid()
            cell.fill.fore_color.rgb = WHITE if r % 2 else CREAM
            p = cell.text_frame.paragraphs[0]
            p.runs[0].font.size = Pt(size - 0.5)
            p.runs[0].font.color.rgb = INK
    return gt


def chip(slide, x, y, w, h, text, fill, tcol=WHITE, size=11, bold=True):
    sh = _rect(slide, x, y, w, h, fill, shape=MSO_SHAPE.ROUNDED_RECTANGLE)
    tf = sh.text_frame
    tf.word_wrap = True
    tf.text = text
    tf.paragraphs[0].alignment = PP_ALIGN.CENTER
    for r in tf.paragraphs[0].runs:
        r.font.size, r.font.bold, r.font.color.rgb = Pt(size), bold, tcol
    return sh


def arrow(slide, x, y, w, h=Inches(0.16), color=MUTE):
    a = _rect(slide, x, y, w, h, color, shape=MSO_SHAPE.RIGHT_ARROW)
    return a


# ===========================================================================
# 01 — Title and overview
# ===========================================================================
title_slide()

s = content("How to use this deck", "Read it in order the first time; use Section 14 as a desk reference after that")
_tb(s, Inches(0.6), Inches(1.4), Inches(5.6), Inches(0.3), "WHAT THIS IS", size=11, bold=True, color=ACCENT)
_tb(s, Inches(0.6), Inches(1.75), Inches(5.6), Inches(2.2),
    "A step-by-step operational guide. Each role is taken from signing in to a "
    "finished ticket, using screens captured from the running application.\n\n"
    "Every workflow slide follows the same shape: what you do, what the system "
    "does back, and who picks it up next.", size=13, color=INK, spacing=1.3)
_tb(s, Inches(0.6), Inches(4.0), Inches(5.6), Inches(0.3), "WHAT IT IS NOT", size=11, bold=True, color=ACCENT)
_tb(s, Inches(0.6), Inches(4.35), Inches(5.6), Inches(1.6),
    "Not a feature tour, and not a specification. Where the system does not do "
    "something people often expect — approvals, in-app notifications, ticket "
    "merging — this deck says so rather than staying silent.",
    size=13, color=INK, spacing=1.3)
_rect(s, Inches(6.9), Inches(1.4), Inches(5.85), Inches(4.6), CREAM)
_tb(s, Inches(7.25), Inches(1.7), Inches(5.2), Inches(0.3), "FIND YOUR ROLE", size=11, bold=True, color=ACCENT)
for i, (r, sec, line) in enumerate([
    ("Branch User", "Section 6", "You raise tickets and follow them"),
    ("Agent", "Section 7", "You work and resolve them"),
    ("Supervisor", "Section 8", "You watch SLA and escalations"),
    ("Admin", "Section 9", "You configure the system"),
    ("Auditor", "Section 10", "You review; you change nothing"),
]):
    y = Inches(2.15) + i * Inches(0.72)
    _rect(s, Inches(7.25), y, Inches(0.05), Inches(0.55), TEAL)
    _tb(s, Inches(7.45), y, Inches(2.2), Inches(0.28), r, size=13, bold=True, color=TEAL)
    _tb(s, Inches(7.45), y + Inches(0.26), Inches(4.6), Inches(0.28), line, size=10.5, color=MUTE)
    _tb(s, Inches(11.3), y + Inches(0.02), Inches(1.2), Inches(0.28), sec, size=10.5, bold=True, color=ACCENT, align=PP_ALIGN.RIGHT)
footer(s, "Overview")

# ===========================================================================
# 02 — System overview
# ===========================================================================
section("02", "What the system is for", "One record for every operational problem, from the moment it is raised to the moment it is closed.")

s = content("The problem it replaces", "Why a shared record beats a shared inbox")
for i, (t, b, col) in enumerate([
    ("Without it",
     "A blocked card is reported by phone. A duplicated debit goes to somebody's "
     "inbox. Nobody can say how long either has been open, who owns it, or what "
     "was decided.", ACCENT),
    ("With it",
     "Every problem gets a number, an owner, a deadline and a history. Months "
     "later an auditor can answer who changed what, and when.", OK),
]):
    x = Inches(0.6) + i * Inches(6.3)
    _rect(s, x, Inches(1.4), Inches(5.9), Inches(2.1), CREAM)
    _rect(s, x, Inches(1.4), Inches(0.06), Inches(2.1), col)
    _tb(s, x + Inches(0.3), Inches(1.65), Inches(5.3), Inches(0.3), t, size=15, bold=True, color=col)
    _tb(s, x + Inches(0.3), Inches(2.05), Inches(5.3), Inches(1.3), b, size=12.5, color=INK, spacing=1.3)

_tb(s, Inches(0.6), Inches(3.85), Inches(12), Inches(0.3), "HOW A TICKET ARRIVES", size=11, bold=True, color=ACCENT)
for i, (t, d) in enumerate([
    ("Portal", "A branch user fills in the form and attaches evidence"),
    ("Email", "A message to the support mailbox becomes a ticket automatically"),
]):
    x = Inches(0.6) + i * Inches(6.3)
    _rect(s, x, Inches(4.25), Inches(5.9), Inches(1.0), WHITE, LINE)
    _tb(s, x + Inches(0.3), Inches(4.45), Inches(2), Inches(0.3), t, size=13, bold=True, color=TEAL)
    _tb(s, x + Inches(0.3), Inches(4.75), Inches(5.3), Inches(0.4), d, size=11, color=MUTE)
_tb(s, Inches(0.6), Inches(5.5), Inches(12), Inches(0.9),
    "Email intake is implemented but off by default (IMAP_ENABLED=false) and needs a real mailbox. "
    "Everything else in this deck works out of the box.", size=11, color=MUTE, spacing=1.25)
footer(s, "Overview")

# ===========================================================================
# 03 — Roles and permissions
# ===========================================================================
section("03", "Roles and permissions", "Five roles, one per user. This is the whole model — there are no per-user overrides.")

s = content("Who can do what", "Enforced server-side in core/authz.py — the interface only hides what the API would refuse anyway")
table(s, Inches(0.5), Inches(1.3), Inches(12.3),
      ["Role", "Tickets", "Users & org", "Audit log", "Escalation queue"],
      [["Branch User", "Own only — raise, comment, attach", "—", "—", "—"],
       ["Agent", "Any in scope — assign, progress, resolve", "—", "—", "—"],
       ["Supervisor", "As agent", "Read directory", "—", "Yes"],
       ["Admin", "As agent", "Full control", "Yes", "Yes"],
       ["Auditor", "Read only — no writes at all", "—", "Yes", "—"]],
      col_w=[Inches(1.9), Inches(4.0), Inches(2.4), Inches(1.7), Inches(2.3)])
_rect(s, Inches(0.5), Inches(4.25), Inches(12.3), Inches(1.15), CREAM)
_rect(s, Inches(0.5), Inches(4.25), Inches(0.06), Inches(1.15), ACCENT)
_tb(s, Inches(0.8), Inches(4.45), Inches(11.8), Inches(0.8),
    "Super admin is a second tier on top of Admin, not a sixth role. Only a super admin can create "
    "another super admin or change one's password — otherwise any admin could take over the account.",
    size=12, color=INK, spacing=1.25)
_tb(s, Inches(0.5), Inches(5.6), Inches(12.3), Inches(0.8),
    "The auditor is read-only everywhere. It can open any ticket, dashboard and report, and every "
    "attempt to write is refused with a 403 — including comments and attachments.",
    size=12, color=MUTE, spacing=1.25)
footer(s, "Roles")

# ===========================================================================
# 04 — Lifecycle
# ===========================================================================
section("04", "The ticket lifecycle", "Nine statuses. The API enforces which moves are legal — an illegal jump is refused, not merely discouraged.")

s = content("Status flow", "Reproduced from VALID_TRANSITIONS in ticket_service.py")
row1 = [("new", TEAL), ("acknowledged", TEAL), ("assigned", TEAL), ("in_progress", TEAL), ("resolved", OK), ("closed", MUTE)]
x = Inches(0.55)
for i, (t, c) in enumerate(row1):
    chip(s, x, Inches(1.55), Inches(1.72), Inches(0.62), t, c, size=11)
    if i < len(row1) - 1:
        arrow(s, x + Inches(1.76), Inches(1.78), Inches(0.28))
    x += Inches(2.04)
for i, (t, c, xx, yy) in enumerate([
    ("on_hold", WARN, Inches(4.65), Inches(2.75)),
    ("escalated", ACCENT, Inches(6.7), Inches(2.75)),
    ("reopened", WARN, Inches(8.75), Inches(2.75)),
]):
    chip(s, xx, yy, Inches(1.72), Inches(0.62), t, c, size=11)
_tb(s, Inches(0.55), Inches(3.6), Inches(12.2), Inches(0.3), "TWO RULES PEOPLE GET WRONG", size=11, bold=True, color=ACCENT)
for i, (t, d) in enumerate([
    ("closed is reachable from any open state",
     "Closing early is a withdrawal — the problem went away, or it was raised in error."),
    ("resolved is NOT reachable from assigned",
     "A ticket must have been worked (in_progress or escalated) first, so 'resolved' means something."),
]):
    y = Inches(3.98) + i * Inches(0.95)
    _rect(s, Inches(0.55), y, Inches(12.2), Inches(0.82), CREAM)
    _tb(s, Inches(0.85), y + Inches(0.12), Inches(11.6), Inches(0.28), t, size=12.5, bold=True, color=TEAL)
    _tb(s, Inches(0.85), y + Inches(0.42), Inches(11.6), Inches(0.32), d, size=11, color=MUTE)
_tb(s, Inches(0.55), Inches(5.95), Inches(12.2), Inches(0.5),
    "on_hold, escalated and reopened re-enter the flow: on_hold and escalated return to in_progress, "
    "and reopened goes back to assigned.", size=11, color=MUTE, spacing=1.25)
footer(s, "Lifecycle")

# ===========================================================================
# 05 — Swimlane
# ===========================================================================
section("05", "End to end, across the roles", "The seams matter more than the steps. This is where a ticket changes hands.")

s = content("Who holds the ticket, and when", "Left to right in time; each band is one role")
lanes = [("BRANCH USER", TEAL), ("AGENT", TEAL_D), ("SUPERVISOR", ACCENT), ("SYSTEM", MUTE)]
lane_h, lane_y0 = Inches(1.12), Inches(1.35)
for i, (name, col) in enumerate(lanes):
    y = lane_y0 + i * lane_h
    _rect(s, Inches(0.5), y, Inches(1.85), lane_h - Inches(0.06), col)
    _tb(s, Inches(0.62), y + Inches(0.36), Inches(1.65), Inches(0.3), name, size=10.5, bold=True, color=WHITE)
    _rect(s, Inches(2.4), y, Inches(10.4), lane_h - Inches(0.06), CREAM if i % 2 == 0 else WHITE, LINE)
steps = [
    (0, 0, "Raise ticket\n+ attach evidence"),
    (3, 1, "Auto-assign\n+ stamp SLA"),
    (1, 2, "Take it,\ninvestigate"),
    (1, 3, "Reply\n+ attach fix"),
    (3, 4, "SLA breach?\nescalate"),
    (2, 5, "Review,\nreassign"),
    (1, 6, "Resolve"),
    (0, 7, "See resolution,\nclose or reopen"),
]
for lane, col_i, label in steps:
    x = Inches(2.55) + col_i * Inches(1.29)
    y = lane_y0 + lane * lane_h + Inches(0.18)
    chip(s, x, y, Inches(1.19), Inches(0.72), label, lanes[lane][1], size=8.5)
footer(s, "End to end")

# ===========================================================================
# 06 — Branch user
# ===========================================================================
section("06", "Branch user workflow", "You raise the problem, supply the evidence, answer questions, and see the resolution.")

workflow("00-login.png", "Sign in", [
    (0.50, 0.42, "Your bank email address"),
    (0.50, 0.53, "Your password"),
    (0.50, 0.64, "Sign in"),
], "Enter your bank email and password, then select Sign in.",
   "You land on your dashboard. If your account has a second factor enabled, "
   "you are asked for a 6-digit code first.",
   "Step 02 — read your dashboard.", "Branch User")

workflow("10-branch-dashboard.png", "Read your dashboard", [
    (0.09, 0.14, "Dashboard, Tickets and Security — the whole menu for this role"),
    (0.55, 0.30, "Your ticket counts"),
    (0.95, 0.93, "The assistant, if you need help"),
], "Check the tiles for anything of yours that is breaching or still open.",
   "Each tile opens the exact list it counts — a tile reading 3 opens three tickets.",
   "Step 03 — open the ticket list.", "Branch User")

workflow("11-branch-tickets.png", "See only your own tickets", [
    (0.50, 0.22, "Filters — status, priority, search"),
    (0.50, 0.50, "Your tickets, newest first"),
], "Scan the list, or filter to what you are looking for.",
   "You see only tickets you raised. This is enforced by the server, not hidden by the page.",
   "Step 04 — raise a new ticket.", "Branch User")

workflow("12-branch-create-empty.png", "Open the new ticket form", [
    (0.45, 0.26, "Title — one line naming the problem"),
    (0.45, 0.45, "Description — what happened, and for whom"),
    (0.45, 0.75, "Priority and category"),
], "Select New Ticket from the ticket list.",
   "An empty form opens. Nothing is submitted until you choose Create Ticket.",
   "Step 05 — fill it in and attach evidence.", "Branch User")

workflow("13-branch-create-filled.png", "Describe it, and attach the evidence", [
    (0.45, 0.26, "Be specific: account, amount, date"),
    (0.45, 0.50, "What happened, and what the customer expects"),
    (0.45, 0.83, "Drag files here, or choose them"),
], "Complete the form and attach a screenshot, statement or spreadsheet. "
   "Up to 15 MB per file; images, PDF, Word, Excel, text and CSV.",
   "Files are held in the browser and uploaded the moment the ticket is created — "
   "so evidence arrives with the report, not after it.",
   "Step 06 — submit and follow it.", "Branch User")

workflow("15-branch-ticket-detail.png", "Follow your ticket", [
    (0.30, 0.13, "Number, status, SLA countdown"),
    (0.86, 0.35, "Your attachments"),
    (0.86, 0.62, "Who owns it now"),
    (0.44, 0.80, "Add more detail for the agent"),
], "Open the ticket from your list to see where it stands.",
   "The ticket was numbered, given SLA deadlines and assigned automatically — "
   "no one had to triage it by hand.",
   "Step 07 — answer questions and read the resolution.", "Branch User")

workflow("16-branch-ticket-comments.png", "Reply, and read the resolution", [
    (0.44, 0.35, "The agent's replies appear here"),
    (0.44, 0.62, "Your reply — you can attach files too"),
], "Answer any question the agent asks, attaching more evidence if needed.",
   "When the agent resolves it, their explanation and any file they attached "
   "appear here together.",
   "If it is fixed, the ticket is closed. If not, it can be reopened.", "Branch User")

s = content("What a branch user cannot see", "Two rules worth knowing before you ask where something went")
for i, (t, d, col) in enumerate([
    ("Internal notes — and their attachments",
     "Agents can mark a note internal. You will not see the note, and you will not see any "
     "file attached to it. It is not hidden in the page; the server refuses to send it.", ACCENT),
    ("Other people's tickets",
     "You see only tickets you raised. Opening someone else's by its link returns nothing.", TEAL),
]):
    y = Inches(1.45) + i * Inches(1.75)
    _rect(s, Inches(0.6), y, Inches(12.1), Inches(1.5), CREAM)
    _rect(s, Inches(0.6), y, Inches(0.06), Inches(1.5), col)
    _tb(s, Inches(0.95), y + Inches(0.22), Inches(11.5), Inches(0.32), t, size=15, bold=True, color=col)
    _tb(s, Inches(0.95), y + Inches(0.63), Inches(11.5), Inches(0.75), d, size=12.5, color=INK, spacing=1.3)
_tb(s, Inches(0.6), Inches(5.1), Inches(12.1), Inches(1.2),
    "If you believe a ticket of yours is missing, it is far more likely that it was raised by a "
    "colleague than that it was deleted — tickets are never deleted, and every change is recorded "
    "in the audit trail.", size=12.5, color=MUTE, spacing=1.3)
footer(s, "Branch User")

# ===========================================================================
# 07 — Agent
# ===========================================================================
section("07", "Agent workflow", "You pick the ticket up, investigate, keep the requester informed, and resolve it.")

workflow("20-agent-dashboard.png", "Start from the dashboard", [
    (0.30, 0.20, "SLA Breached — deal with these first"),
    (0.62, 0.20, "Critical open"),
    (0.85, 0.55, "AI panel: what the model sorted and scored"),
], "Sign in and read the KPI strip before opening anything.",
   "Every tile is a live count and opens the exact list behind it.",
   "Step 09 — open the queue.", "Agent")

workflow("21-agent-tickets.png", "Work the queue", [
    (0.50, 0.22, "Filter by status, priority or assignee"),
    (0.50, 0.55, "Every ticket in your scope"),
], "Filter to unassigned or to your own, and choose what to work on.",
   "Agents see every ticket in their org scope, not just their own.",
   "Step 10 — start with what is breaching.", "Agent")

workflow("22-agent-breached.png", "Deal with breaches first", [
    (0.50, 0.16, "The filter the SLA Breached tile applied"),
    (0.50, 0.50, "Open tickets already past their deadline"),
], "Select the SLA Breached tile on the dashboard.",
   "The list is filtered to exactly the tickets the tile counted — the number "
   "on the card and the length of this list always agree.",
   "Step 11 — open one and investigate.", "Agent")

workflow("23-agent-ticket-detail.png", "Investigate the ticket", [
    (0.30, 0.13, "Status, SLA countdown, AI category and risk"),
    (0.44, 0.42, "AI Insights — summarise, or suggest next steps"),
    (0.86, 0.32, "Evidence the requester attached"),
    (0.86, 0.62, "Reporter, assignee, category, source"),
], "Read the description and the attached evidence, then move the ticket to In Progress.",
   "The status change is recorded in the audit trail with your name, and the "
   "first-response clock stops.",
   "Step 12 — reply, and attach the fix.", "Agent")

workflow("24-agent-ticket-comments.png", "Reply — and attach the fix to your reply", [
    (0.44, 0.30, "The conversation so far"),
    (0.44, 0.62, "Your reply"),
    (0.44, 0.78, "Attach files to this reply"),
    (0.28, 0.88, "Internal note — hidden from the requester"),
], "Write what you found and attach the corrected statement or screenshot.",
   "Files attached here belong to this reply, so the requester sees your fix "
   "beside the answer that explains it.",
   "Step 13 — resolve, or escalate.", "Agent")

s = content("Resolve, or escalate — and what each means", "Both are one action on the ticket page")
for i, (t, d, col) in enumerate([
    ("Resolve", "Use when the problem is fixed. Only available once the ticket has been worked — "
                "you cannot jump straight from Assigned to Resolved, which is what makes 'resolved' "
                "mean something.", OK),
    ("Escalate", "Use when it needs someone else. The ticket moves to Escalated, is reassigned to the "
                 "least-loaded holder of the target role, and an escalation event is recorded. "
                 "Escalating twice for the same reason does nothing — the second is suppressed.", ACCENT),
    ("Put on hold", "Use when you are waiting on someone outside the team. The ticket stays open and "
                    "keeps counting toward your queue.", WARN),
]):
    y = Inches(1.4) + i * Inches(1.55)
    _rect(s, Inches(0.6), y, Inches(12.1), Inches(1.32), CREAM if i % 2 == 0 else WHITE, LINE)
    _rect(s, Inches(0.6), y, Inches(0.06), Inches(1.32), col)
    _tb(s, Inches(0.95), y + Inches(0.2), Inches(11.4), Inches(0.3), t, size=15, bold=True, color=col)
    _tb(s, Inches(0.95), y + Inches(0.58), Inches(11.4), Inches(0.68), d, size=12, color=INK, spacing=1.28)
_tb(s, Inches(0.6), Inches(6.15), Inches(12.1), Inches(0.6),
    "Closing is always available, from any open state — it means the problem went away or the ticket "
    "was raised in error, not that it was solved.", size=11.5, color=MUTE, spacing=1.25)
footer(s, "Agent")

# ===========================================================================
# 08 — Supervisor
# ===========================================================================
section("08", "Supervisor workflow", "You watch the deadlines and the escalations, and step in before a breach becomes a complaint.")

workflow("30-supervisor-dashboard.png", "Watch the team's position", [
    (0.30, 0.20, "Breached — the number that matters most"),
    (0.85, 0.55, "AI panel"),
], "Read the strip; anything breaching needs an owner today.",
   "Supervisors see the same tiles as agents, plus the SLA monitor and escalation queue in the menu.",
   "Step 15 — open the SLA monitor.", "Supervisor")

workflow("31-supervisor-sla.png", "Read the SLA monitor", [
    (0.50, 0.25, "On time, at risk, breached"),
    (0.50, 0.60, "Tickets closest to their deadline"),
], "Work down from the tickets nearest their deadline.",
   "At risk means due within the hour. Breached means the deadline has already passed "
   "and, if a rule matched, escalation has already fired.",
   "Step 16 — review escalations.", "Supervisor")

workflow("32-supervisor-escalations.png", "Review the escalation queue", [
    (0.50, 0.25, "Escalation events, newest first"),
    (0.50, 0.60, "What triggered each, and who it went to"),
], "Check what escalated and whether the target is acting on it.",
   "Escalations arrive here whether raised by hand or fired automatically by the "
   "SLA worker — both run the same engine, so the evidence is identical.",
   "Reassign if the target is wrong; otherwise the agent resolves it.", "Supervisor")

s = content("How escalation actually fires", "Nobody has to be watching for this to happen")
_rect(s, Inches(0.6), Inches(1.35), Inches(12.1), Inches(1.15), CREAM)
_tb(s, Inches(0.95), Inches(1.6), Inches(11.4), Inches(0.7),
    "Every 5 minutes a background worker looks for tickets past their resolution deadline. "
    "For each one it finds, it marks the breach and evaluates the escalation rules.",
    size=13, color=INK, spacing=1.3)
for i, (t, d) in enumerate([
    ("1 — Rule matched", "The most specific rule wins. A category-specific rule beats a catch-all, and priority_threshold is read as a minimum, so a 'high' rule also covers critical."),
    ("2 — Ticket moved", "Status becomes Escalated and it is reassigned to the least-loaded holder of the target role."),
    ("3 — Evidence written", "An escalation_events row records the trigger, the rule and the target."),
    ("4 — People told", "The target and the manager list are emailed after the change commits — a failed email never rolls back the escalation."),
]):
    y = Inches(2.75) + i * Inches(0.9)
    _rect(s, Inches(0.6), y, Inches(12.1), Inches(0.78), WHITE, LINE)
    _tb(s, Inches(0.9), y + Inches(0.11), Inches(3.0), Inches(0.28), t, size=12.5, bold=True, color=TEAL)
    _tb(s, Inches(3.9), y + Inches(0.11), Inches(8.6), Inches(0.6), d, size=11, color=INK, spacing=1.2)
_tb(s, Inches(0.6), Inches(6.45), Inches(12.1), Inches(0.5),
    "A ticket will not escalate twice for the same trigger — otherwise the worker would raise a new "
    "event every five minutes until somebody resolved it.", size=11.5, color=MUTE, spacing=1.25)
footer(s, "Supervisor")

# ===========================================================================
# 09 — Admin
# ===========================================================================
section("09", "Admin workflow", "You decide who exists, what they may do, and how the organisation is shaped.")

workflow("41-admin-users.png", "Manage users", [
    (0.50, 0.20, "Everyone with an account"),
    (0.50, 0.42, "Role — one per user, the whole permission model"),
    (0.88, 0.20, "Add a user"),
], "Create a user, set their role, and place them in an org unit.",
   "The role decides what they may do. There are no per-user permission overrides.",
   "Step 18 — shape the organisation.", "Admin")

workflow("42-admin-org.png", "Shape the organisation", [
    (0.50, 0.30, "Hierarchy levels and org units"),
    (0.50, 0.62, "The tree that decides who sees which tickets"),
], "Define hierarchy levels, then units within them.",
   "The org tree drives ticket visibility: a user sees their unit's subtree, "
   "plus anything assigned to them personally.",
   "Step 19 — maintain the branch network.", "Admin")

workflow("43-admin-branches.png", "Maintain the branch network", [
    (0.50, 0.22, "Branches, with live ticket load"),
    (0.50, 0.55, "Status is separate from active"),
], "Add branches, set managers and capacity, and mark degraded ones.",
   "Ticket counts are computed per request, never stored — a counter that "
   "drifts is wrong forever with nothing to reveal it.",
   "Step 20 — pull reports.", "Admin")

workflow("44-admin-reports.png", "Pull reports", [
    (0.50, 0.25, "Filter the period and the scope"),
    (0.50, 0.62, "The charts you can export"),
    (0.85, 0.20, "Export as CSV, PDF or Excel"),
], "Choose a period, then export.",
   "The export is generated from what is on screen, so it matches the filters "
   "you applied rather than silently re-running an unfiltered query.",
   "Step 21 — protect your own account.", "Admin")

workflow("45-admin-security.png", "Turn on your second factor", [
    (0.45, 0.35, "Scan this with an authenticator app"),
    (0.45, 0.66, "Confirm one code to switch it on"),
], "Open Security, scan the QR code, and enter one code to confirm.",
   "MFA is only switched on once a correct code proves the app is working — "
   "so a failed scan cannot lock you out. Ten single-use recovery codes are "
   "shown once, and never again.",
   "Save the recovery codes somewhere safe before leaving this screen.", "Admin")

s = content("Save the recovery codes", "This is the one screen you cannot go back to")
_rect(s, Inches(0.6), Inches(1.4), Inches(12.1), Inches(1.6), CREAM)
_rect(s, Inches(0.6), Inches(1.4), Inches(0.06), Inches(1.6), ACCENT)
_tb(s, Inches(0.95), Inches(1.68), Inches(11.4), Inches(1.15),
    "Ten recovery codes are shown once, when you switch MFA on. Only their hashes are stored, so "
    "nobody — including an administrator — can show them to you again. Each works once, in place of "
    "a code from your app.", size=14, color=INK, spacing=1.35)
for i, (t, d) in enumerate([
    ("Lost your phone, still have codes", "Use any unused recovery code at sign-in. It works once, then it is spent."),
    ("Lost both", "An administrator clears your enrolment, and you set it up again from scratch."),
    ("Lost the only super admin", "There is no route through the interface, by design. The flag has to be set on the database row."),
]):
    y = Inches(3.3) + i * Inches(0.95)
    _rect(s, Inches(0.6), y, Inches(12.1), Inches(0.8), WHITE, LINE)
    _tb(s, Inches(0.95), y + Inches(0.12), Inches(4.3), Inches(0.28), t, size=12.5, bold=True, color=TEAL)
    _tb(s, Inches(5.4), y + Inches(0.12), Inches(7.0), Inches(0.6), d, size=11.5, color=INK, spacing=1.2)
footer(s, "Admin")

# ===========================================================================
# 10 — Auditor
# ===========================================================================
section("10", "Auditor workflow", "You can open everything and change nothing. Every write is refused by the server.")

workflow("50-auditor-dashboard.png", "See the whole picture", [
    (0.50, 0.20, "The same tiles everyone else sees"),
], "Sign in and read the dashboard.",
   "Auditors have full visibility. What they do not have is any way to change "
   "what they are looking at.",
   "Step 23 — open the audit trail.", "Auditor")

workflow("51-auditor-audit-log.png", "Read the audit trail", [
    (0.50, 0.25, "Filter by entity, action or actor"),
    (0.50, 0.58, "Who changed what, when, and from where"),
], "Filter to the entity or person you are reviewing.",
   "Every state change writes a row: actor, role, IP, request id, and the "
   "values before and after.",
   "Step 24 — inspect any ticket.", "Auditor")

workflow("52-auditor-tickets.png", "Inspect any ticket", [
    (0.50, 0.22, "No scope limit — every ticket is visible"),
    (0.50, 0.55, "Open any of them, read the full history"),
], "Open any ticket and read its comments, attachments and timeline.",
   "Internal notes are visible to an auditor. Write controls are not offered, "
   "and would be refused if called directly.",
   "This is the end of the auditor's workflow — there is nothing to submit.", "Auditor")

s = content("A caveat worth recording", "Honest limitation of the audit trail as it stands today")
_rect(s, Inches(0.6), Inches(1.5), Inches(12.1), Inches(2.0), CREAM)
_rect(s, Inches(0.6), Inches(1.5), Inches(0.06), Inches(2.0), ACCENT)
_tb(s, Inches(0.95), Inches(1.8), Inches(11.4), Inches(0.35),
    "The audit trail is append-only by convention, not by enforcement.", size=16, bold=True, color=ACCENT)
_tb(s, Inches(0.95), Inches(2.3), Inches(11.4), Inches(1.1),
    "The application only ever inserts rows. But there is no database trigger and no revoked "
    "permission, so anything holding the database credentials could alter history. Closing this "
    "is the first item on the outstanding work list.", size=13, color=INK, spacing=1.35)
_tb(s, Inches(0.6), Inches(3.9), Inches(12.1), Inches(0.9),
    "It is recorded here rather than left out, because an auditor is exactly the person who needs to "
    "know how much weight the trail can carry.", size=12.5, color=MUTE, spacing=1.3)
footer(s, "Auditor")

# ===========================================================================
# 11 — Attachments
# ===========================================================================
section("11", "Attachments", "Where files can be added, who can see them, and the one rule people assume wrong.")

s = content("Three places a file can be attached", "The flow is the same in each: choose the files, then they upload once the thing they belong to exists")
for i, (t, d, who) in enumerate([
    ("With the ticket, when it is raised",
     "Evidence travels with the report rather than arriving afterwards.", "Branch user, agent"),
    ("With a reply",
     "The file belongs to that reply, so a fix sits beside the answer explaining it.", "Anyone who can comment"),
    ("From the attachments panel",
     "The file index for the whole ticket; files from replies are marked as such.", "Anyone who can write"),
]):
    y = Inches(1.4) + i * Inches(1.28)
    _rect(s, Inches(0.6), y, Inches(12.1), Inches(1.08), CREAM if i % 2 == 0 else WHITE, LINE)
    _tb(s, Inches(0.95), y + Inches(0.16), Inches(6.4), Inches(0.3), t, size=13.5, bold=True, color=TEAL)
    _tb(s, Inches(0.95), y + Inches(0.52), Inches(6.4), Inches(0.45), d, size=11.5, color=INK, spacing=1.2)
    _tb(s, Inches(7.7), y + Inches(0.16), Inches(4.7), Inches(0.3), "WHO", size=9.5, bold=True, color=ACCENT)
    _tb(s, Inches(7.7), y + Inches(0.44), Inches(4.7), Inches(0.4), who, size=11.5, color=INK)
_tb(s, Inches(0.6), Inches(5.4), Inches(12.1), Inches(1.3),
    "Limits: 15 MB per file. Images, PDF, Word, Excel, text and CSV are accepted. Executables and "
    "archives are refused outright — there is no malware scanner, and an unscanned archive is the "
    "usual way something nasty arrives.", size=12.5, color=MUTE, spacing=1.3)
footer(s, "Attachments")

s = content("The rule people get wrong", "An internal note's attachment is as invisible as the note")
_rect(s, Inches(0.6), Inches(1.4), Inches(5.85), Inches(2.4), CREAM)
_rect(s, Inches(0.6), Inches(1.4), Inches(0.06), Inches(2.4), TEAL)
_tb(s, Inches(0.95), Inches(1.65), Inches(5.2), Inches(0.32), "What agents assume", size=14, bold=True, color=TEAL)
_tb(s, Inches(0.95), Inches(2.08), Inches(5.2), Inches(1.5),
    "\"The note is internal, so the requester will not read my text — but the file I attached "
    "is just a file on the ticket.\"", size=12.5, color=INK, spacing=1.3)
_rect(s, Inches(6.9), Inches(1.4), Inches(5.85), Inches(2.4), CREAM)
_rect(s, Inches(6.9), Inches(1.4), Inches(0.06), Inches(2.4), OK)
_tb(s, Inches(7.25), Inches(1.65), Inches(5.2), Inches(0.32), "What actually happens", size=14, bold=True, color=OK)
_tb(s, Inches(7.25), Inches(2.08), Inches(5.2), Inches(1.5),
    "The file is hidden too. It is filtered from the list and refused on download — "
    "and the refusal is a 404, so the response does not even confirm the note exists.",
    size=12.5, color=INK, spacing=1.3)
_tb(s, Inches(0.6), Inches(4.15), Inches(12.1), Inches(1.2),
    "This matters because the file is usually the sensitive part. Hiding the note while serving its "
    "attachment would leak exactly what the flag exists to withhold.", size=13, color=INK, spacing=1.3)
_rect(s, Inches(0.6), Inches(5.3), Inches(12.1), Inches(1.0), WHITE, LINE)
_tb(s, Inches(0.95), Inches(5.5), Inches(11.4), Inches(0.65),
    "Related: you cannot attach a file to somebody else's comment. Without that rule an agent could "
    "hang a file off the requester's own message, where it would read as something they had sent.",
    size=11.5, color=MUTE, spacing=1.25)
footer(s, "Attachments")

# ===========================================================================
# 12 — Assistant
# ===========================================================================
section("12", "The AI assistant", "It answers questions about the work in front of you. It cannot change anything.")

s = content("What it can and cannot do", "Three properties are enforced by the server, not by the prompt")
for i, (t, d, col) in enumerate([
    ("It cannot see more than you can",
     "Context is fetched through the same visibility rules as the rest of the application. "
     "Point it at a ticket your role cannot open and it is told the ticket is unavailable — "
     "no title, no number, nothing.", OK),
    ("It says when it does not know",
     "Rather than producing generic advice. An assistant that invents ticket facts in a bank "
     "is worse than one that declines.", OK),
    ("It cannot act",
     "It has no write access. It will not change a status, assign a ticket or post a comment. "
     "Everything it produces is for you to act on.", ACCENT),
]):
    y = Inches(1.4) + i * Inches(1.55)
    _rect(s, Inches(0.6), y, Inches(12.1), Inches(1.32), CREAM if i % 2 == 0 else WHITE, LINE)
    _rect(s, Inches(0.6), y, Inches(0.06), Inches(1.32), col)
    _tb(s, Inches(0.95), y + Inches(0.18), Inches(11.4), Inches(0.3), t, size=14, bold=True, color=col)
    _tb(s, Inches(0.95), y + Inches(0.56), Inches(11.4), Inches(0.7), d, size=12, color=INK, spacing=1.25)
_tb(s, Inches(0.6), Inches(6.15), Inches(12.1), Inches(0.7),
    "If it reports that it cannot connect, the cause is almost always the local model rather than the "
    "application. The message it shows includes the specific fix.", size=11.5, color=MUTE, spacing=1.25)
footer(s, "Assistant")

# ===========================================================================
# 13 — Scenarios
# ===========================================================================
section("13", "Common scenarios", "Four situations, start to finish, naming who does what at each hop.")

for title, kicker, rows in [
    ("Scenario A — a duplicated debit",
     "The everyday case: raised with evidence, worked, resolved",
     [("Branch user", "Raises the ticket with a screenshot, the statement and a CSV of the transactions"),
      ("System", "Numbers it, stamps SLA deadlines, assigns the agent with the lightest queue"),
      ("Agent", "Moves it to In Progress, checks the evidence, confirms the duplicate"),
      ("Agent", "Replies with the corrected statement attached to that reply, then resolves"),
      ("Branch user", "Sees the explanation and the corrected file together, and the ticket closes")]),
    ("Scenario B — nobody picked it up",
     "What happens when a deadline passes and no one is watching",
     [("System", "The SLA worker finds the ticket past its resolution deadline"),
      ("System", "Marks the breach, matches the most specific escalation rule"),
      ("System", "Moves it to Escalated, reassigns to the least-loaded holder of the target role"),
      ("System", "Writes an escalation event, then emails the target and the managers"),
      ("Supervisor", "Sees it in the escalation queue and confirms someone is on it")]),
    ("Scenario C — the agent needs more information",
     "The two-way exchange that used to happen over email",
     [("Agent", "Replies asking for the account number and a clearer screenshot"),
      ("Branch user", "Answers on the ticket and attaches the new screenshot"),
      ("Agent", "Continues, adding an internal note with findings the requester should not see"),
      ("Branch user", "Sees neither the internal note nor the file attached to it"),
      ("Agent", "Resolves with a public explanation")]),
    ("Scenario D — it was not actually fixed",
     "Reopening, and what it does to the counts",
     [("Branch user", "Reads the resolution and finds the problem still occurring"),
      ("Branch user", "Reopens the ticket, explaining what is still wrong"),
      ("System", "The ticket returns to the open set and counts against the dashboard again"),
      ("Agent", "Picks it back up from Assigned and works it a second time"),
      ("Agent", "Resolves again — the whole history stays on the one ticket")]),
]:
    s = content(title, kicker)
    for i, (who, what) in enumerate(rows):
        y = Inches(1.35) + i * Inches(1.02)
        col = TEAL if who not in ("System",) else MUTE
        _rect(s, Inches(0.6), y, Inches(2.25), Inches(0.86), col)
        _tb(s, Inches(0.78), y + Inches(0.28), Inches(2.0), Inches(0.3), who, size=12, bold=True, color=WHITE)
        _rect(s, Inches(2.95), y, Inches(9.78), Inches(0.86), CREAM if i % 2 == 0 else WHITE, LINE)
        _tb(s, Inches(3.25), y + Inches(0.2), Inches(9.2), Inches(0.6), what, size=12, color=INK, spacing=1.2)
    footer(s, "Scenarios")

# ===========================================================================
# 14 — Quick reference
# ===========================================================================
section("14", "Quick reference", "The desk copy. Statuses, who does what, and where things live.")

s = content("Status reference", "Who can move a ticket into each state, and what it means")
table(s, Inches(0.5), Inches(1.25), Inches(12.3),
      ["Status", "Means", "Set by"],
      [["new", "Raised, not yet looked at", "System, on creation"],
       ["acknowledged", "Seen, not yet owned", "Agent"],
       ["assigned", "Has an owner", "System or agent"],
       ["in_progress", "Actively being worked", "Agent"],
       ["on_hold", "Waiting on someone outside the team", "Agent"],
       ["escalated", "Handed up — by hand or by SLA breach", "Agent, or the SLA worker"],
       ["resolved", "Fixed; only from in_progress or escalated", "Agent"],
       ["closed", "Finished, or withdrawn; reachable from any open state", "Agent, or the requester"],
       ["reopened", "Was not actually fixed; returns to the open set", "Requester or agent"]],
      col_w=[Inches(2.1), Inches(6.6), Inches(3.6)], size=11)
footer(s, "Reference")

s = content("Where to click", "The shortest path to the thing you need")
table(s, Inches(0.5), Inches(1.25), Inches(12.3),
      ["I want to…", "Go to", "Who can"],
      [["Raise a problem", "Tickets → New Ticket", "Everyone"],
       ["Follow my ticket", "Tickets → open it", "Everyone (own only, for branch users)"],
       ["Find what is breaching", "Dashboard → SLA Breached tile", "Agent and above"],
       ["See what escalated", "Escalations", "Supervisor, admin"],
       ["Check deadlines", "SLA Monitor", "Supervisor, admin"],
       ["Add or change a user", "Users", "Admin"],
       ["Change the org tree", "Org Management", "Admin"],
       ["Export figures", "Reports → CSV / PDF / Excel", "Supervisor, admin, auditor"],
       ["Review who changed what", "Audit", "Admin, auditor"],
       ["Turn on my second factor", "Security", "Everyone"]],
      col_w=[Inches(4.0), Inches(4.3), Inches(4.0)], size=11)
footer(s, "Reference")

s = content("What this system does not do", "Stated plainly, so nobody waits for a feature that is not coming today")
for i, (t, d) in enumerate([
    ("No approval workflow", "Nothing routes for sign-off before proceeding."),
    ("No in-app notifications", "Notifications are email only. There is no bell icon."),
    ("No ticket merging", "Duplicates can be marked as such, but two tickets cannot be combined into one."),
    ("No customer portal", "Every account is an employee account; branch staff raise tickets on customers' behalf."),
    ("No per-user permissions", "One role per user. Anything finer is expressed through the org tree."),
]):
    y = Inches(1.35) + i * Inches(1.0)
    _rect(s, Inches(0.6), y, Inches(12.1), Inches(0.84), CREAM if i % 2 == 0 else WHITE, LINE)
    _tb(s, Inches(0.95), y + Inches(0.14), Inches(4.0), Inches(0.3), t, size=12.5, bold=True, color=ACCENT)
    _tb(s, Inches(5.1), y + Inches(0.14), Inches(7.4), Inches(0.6), d, size=11.5, color=INK, spacing=1.2)
_tb(s, Inches(0.6), Inches(6.5), Inches(12.1), Inches(0.4),
    "If one of these would help, it belongs on the ticket list — not in a workaround.",
    size=11.5, color=MUTE)
footer(s, "Reference")

# ---- close -----------------------------------------------------------------
s = prs.slides.add_slide(BLANK)
_bg(s, TEAL)
_tb(s, Inches(1.0), Inches(2.7), Inches(11), Inches(0.7),
    "Questions, or something here that does not match what you see?",
    size=26, bold=True, color=WHITE)
_tb(s, Inches(1.0), Inches(3.6), Inches(11), Inches(1.4),
    "This deck describes the application at commit c554e3c. If a screen has changed, the deck is "
    "wrong and not the application — raise it so this can be recaptured.\n\n"
    "Operational procedures — deploying, restoring, what to do at 3am — are in docs/runbook.md.",
    size=15, color=CREAM, spacing=1.4)

prs.save(str(OUT))
print(f"saved {OUT}  ({len(prs.slides.__iter__.__self__._sldIdLst)} slides)")
