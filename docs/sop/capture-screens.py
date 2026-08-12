"""Capture SOP screenshots *and* the coordinates of the elements they call out.

The first pass placed callout markers by guessing percentages, which put them
next to controls rather than on them. Here the browser reports each element's
real bounding box, normalised to the viewport, so the marker lands where the
reader is meant to look.

Each entry in CALLOUTS is (label, locator). The locator is resolved on the
page; if it does not match, the callout is dropped and reported rather than
placed at a guess.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5199"
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
VP = {"width": 1440, "height": 900}

USERS = {
    "branch":     ("sunita.desai@successbank.local", "Passw0rd@123"),
    "agent":      ("aisha.khan@successbank.local", "Passw0rd@123"),
    "supervisor": ("priya.sharma@successbank.local", "Passw0rd@123"),
    "admin":      ("admin@successbank.local", "Admin@123456"),
    "auditor":    ("deepak.iyer@successbank.local", "Passw0rd@123"),
}

manifest: dict[str, dict] = {}
missing: list[str] = []


def login(page, who):
    e, p = USERS[who]
    page.goto(f"{BASE}/login", wait_until="networkidle")
    page.fill('input[type="email"]', e)
    page.fill('input[type="password"]', p)
    page.click('button[type="submit"]')
    page.wait_for_url(lambda u: "/login" not in u, timeout=20000)
    page.wait_for_timeout(1500)


def shot(page, name, callouts=()):
    """callouts: sequence of (label, locator_fn) where locator_fn(page)->Locator."""
    # Every shot waits, not just the ones that were noticed to be slow. The
    # dashboards looked settled after a fixed 900ms and were not.
    settle(page)
    page.screenshot(path=str(OUT / f"{name}.png"))
    marks = []
    for label, loc_fn in callouts:
        try:
            loc = loc_fn(page).first
            loc.wait_for(state="visible", timeout=2500)
            b = loc.bounding_box()
            if not b:
                raise ValueError("no box")
            # Full box, normalised. The builder places the marker beside the
            # element rather than on top of it — a marker centred on a text
            # field hides the very value the reader is meant to see.
            x0 = b["x"] / VP["width"]
            y0 = b["y"] / VP["height"]
            bw = b["width"] / VP["width"]
            bh = b["height"] / VP["height"]
            cy = y0 + bh / 2
            if not (0 <= x0 <= 1 and 0 <= cy <= 1):
                raise ValueError("off-viewport")
            marks.append({"label": label, "x0": round(x0, 4), "y0": round(y0, 4),
                          "w": round(bw, 4), "h": round(bh, 4),
                          "x": round(x0 + bw / 2, 4), "y": round(cy, 4)})
        except Exception as exc:
            missing.append(f"{name}: {label} ({type(exc).__name__})")
    manifest[name] = {"file": f"{name}.png", "callouts": marks}
    print(f"  {name}: {len(marks)}/{len(callouts)} callouts located")


def settle(page, timeout=15000):
    """Wait for async panels to finish before shooting.

    The ticket page loads its audit trail separately; a fixed sleep caught it
    mid-'Loading…' and put a spinner in the deck.
    """
    # Two different 'not ready yet' signals, and both had to be waited for:
    #
    #  - 'Loading…' text, written with a real ellipsis (U+2026). Checking for
    #    three full stops matched nothing, so the wait passed instantly and a
    #    spinner made it into the deck.
    #  - Tailwind `animate-pulse` skeletons, which carry no text at all. The
    #    dashboards were captured as rows of blank grey cards because of this.
    try:
        page.wait_for_function(
            "() => !/Loading(\\u2026|\\.\\.\\.)/.test(document.body.innerText)"
            " && document.querySelectorAll('.animate-pulse').length === 0",
            timeout=timeout)
    except Exception:
        n = page.evaluate("() => document.querySelectorAll('.animate-pulse').length")
        print(f"    (still loading: {n} skeleton(s) on screen)")
    page.wait_for_timeout(600)


def scroll_to(page, locator_fn, offset=380):
    """Bring an element into view with room above it, instead of guessing pixels.

    A fixed mouse-wheel distance depends on how long the page happens to be;
    when the seeded content changed, the same scroll put the reply box off the
    top of the viewport and the callouts could not be located at all.

    `offset` then nudges past the element. Without it the element lands at the
    bottom edge and the shot is indistinguishable from the unscrolled one, so
    two consecutive slides showed the same view.
    """
    loc = locator_fn(page).first
    loc.scroll_into_view_if_needed(timeout=8000)
    page.mouse.wheel(0, offset)
    page.wait_for_timeout(900)


def T(text):      return lambda p: p.get_by_text(text, exact=False)
def PH(text):     return lambda p: p.get_by_placeholder(text)
def ROLE(r, n):   return lambda p: p.get_by_role(r, name=n)
def CSS(sel):     return lambda p: p.locator(sel)


with sync_playwright() as pw:
    b = pw.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
    ctx = b.new_context(viewport=VP, device_scale_factor=2)
    page = ctx.new_page()

    # ---- login ------------------------------------------------------------
    page.goto(f"{BASE}/login", wait_until="networkidle")
    shot(page, "00-login", [
        ("Your bank email address", CSS('input[type="email"]')),
        ("Your password", CSS('input[type="password"]')),
        ("Sign in", CSS('button[type="submit"]')),
    ])

    # ---- branch user ------------------------------------------------------
    login(page, "branch")
    shot(page, "10-branch-dashboard", [
        ("Dashboard, Tickets and Security — the whole menu for this role", CSS('nav, aside')),
        ("Your ticket counts", CSS('main')),
    ])

    page.goto(f"{BASE}/tickets", wait_until="networkidle")
    shot(page, "11-branch-tickets", [
        ("Search and filters", CSS('input[placeholder*="earch"]')),
        ("New Ticket", ROLE("button", "New Ticket")),
    ])

    page.goto(f"{BASE}/tickets/new", wait_until="networkidle")
    shot(page, "12-branch-create-empty", [
        ("Title — one line naming the problem", CSS('input[name="title"]')),
        ("Description — what happened, and for whom", CSS('textarea[name="description"]')),
        ("Priority", CSS('select[name="priority"]')),
    ])

    page.fill('input[name="title"]', "Duplicate debit on account ending 4417")
    page.fill('textarea[name="description"]',
              "Two identical debits of 12,400 posted on 9 August. Customer has been "
              "charged twice. Screenshot and statement attached.")
    page.select_option('select[name="priority"]', "high")
    page.wait_for_timeout(500)
    shot(page, "13-branch-create-filled", [
        ("Be specific: account, amount, date", CSS('input[name="title"]')),
        ("What happened, and what the customer expects", CSS('textarea[name="description"]')),
        ("Attach evidence — drag files here, or choose them", T("Attachments")),
        ("Priority and category", CSS('select[name="priority"]')),
    ])

    bt = Path("/tmp/branch_ticket.txt").read_text().strip()
    page.goto(f"{BASE}/tickets/{bt}", wait_until="networkidle")
    page.wait_for_selector("text=TKT-", timeout=20000)
    settle(page)
    shot(page, "15-branch-ticket-detail", [
        ("Number, status and SLA countdown", T("SLA")),
        ("Your attachments", T("Attachments")),
        ("Who owns it now", T("ASSIGNEE")),
        ("Add more detail for the agent", PH("Add more detail for the agent…")),
    ])
    scroll_to(page, T("Attach a file"))
    settle(page)
    shot(page, "16-branch-ticket-comments", [
        ("Replies appear here", T("Comments")),
        ("Attach a file to your reply", T("Attach a file")),
    ])
    page.evaluate("() => localStorage.clear()")

    # ---- agent ------------------------------------------------------------
    login(page, "agent")
    shot(page, "20-agent-dashboard", [
        ("SLA Breached — deal with these first", T("SLA Breached")),
        ("Critical open", T("Critical")),
        ("AI panel", T("AI Metrics")),
    ])
    page.goto(f"{BASE}/tickets", wait_until="networkidle")
    shot(page, "21-agent-tickets", [
        ("Filter by status, priority or owner", CSS('select')),
        ("Every ticket in your scope", CSS('main')),
    ])
    page.goto(f"{BASE}/tickets?status_group=open&sla_breached=true", wait_until="networkidle")
    shot(page, "22-agent-breached", [
        ("The filter the tile applied", CSS('input[placeholder*="earch"]')),
    ])

    at = Path("/tmp/rich_ticket.txt").read_text().strip()
    page.goto(f"{BASE}/tickets/{at}", wait_until="networkidle")
    page.wait_for_selector("text=TKT-", timeout=20000)
    settle(page)
    shot(page, "23-agent-ticket-detail", [
        ("Status, SLA countdown, AI category and risk", T("Escalation Timeline")),
        ("The problem as reported", T("Description")),
        ("AI Insights — summarise or suggest", T("AI Insights")),
        ("Evidence the requester attached", T("Attachments")),
    ])
    scroll_to(page, T("Attach a file"))
    settle(page)
    shot(page, "24-agent-ticket-comments", [
        ("Your reply", CSS("textarea")),
        ("Attach files to this reply", T("Attach a file")),
    ])
    page.evaluate("() => localStorage.clear()")

    # ---- supervisor -------------------------------------------------------
    login(page, "supervisor")
    shot(page, "30-supervisor-dashboard", [
        ("Breached — the number that matters most", T("SLA Breached")),
        ("SLA Monitor and Escalations in the menu", CSS('nav, aside')),
    ])
    page.goto(f"{BASE}/sla", wait_until="networkidle")
    shot(page, "31-supervisor-sla", [("On time, at risk, breached", CSS('main'))])
    page.goto(f"{BASE}/escalations", wait_until="networkidle")
    shot(page, "32-supervisor-escalations", [("Escalation events, newest first", CSS('main'))])
    page.evaluate("() => localStorage.clear()")

    # ---- admin ------------------------------------------------------------
    login(page, "admin")
    shot(page, "40-admin-dashboard", [("The full menu", CSS('nav, aside'))])
    page.goto(f"{BASE}/users", wait_until="networkidle")
    shot(page, "41-admin-users", [
        ("Everyone with an account", CSS('main')),
        ("Add a user", ROLE("button", "Add User")),
    ])
    page.goto(f"{BASE}/org", wait_until="networkidle")
    shot(page, "42-admin-org", [("Hierarchy levels and org units", CSS('main'))])
    page.goto(f"{BASE}/branches", wait_until="networkidle")
    shot(page, "43-admin-branches", [("Branches, with live ticket load", CSS('main'))])
    page.goto(f"{BASE}/reports", wait_until="networkidle")
    shot(page, "44-admin-reports", [("Filter the period and scope", CSS('main'))])
    page.goto(f"{BASE}/security", wait_until="networkidle")
    shot(page, "45-admin-security", [("Enrol a second factor", CSS('main'))])
    page.evaluate("() => localStorage.clear()")

    # ---- auditor ----------------------------------------------------------
    login(page, "auditor")
    shot(page, "50-auditor-dashboard", [("The same tiles everyone else sees", CSS('main'))])
    page.goto(f"{BASE}/audit", wait_until="networkidle")
    settle(page)
    shot(page, "51-auditor-audit-log", [("Who changed what, when, from where", CSS('main'))])
    page.goto(f"{BASE}/tickets", wait_until="networkidle")
    shot(page, "52-auditor-tickets", [("No scope limit — every ticket", CSS('main'))])

    b.close()

(OUT / "manifest.json").write_text(json.dumps(manifest, indent=2))
print(f"\n{len(manifest)} screens captured")
if missing:
    print(f"\n{len(missing)} callouts could NOT be located (dropped, not guessed):")
    for m in missing:
        print("  -", m)
