"""Capture SOP screenshots from the running application.

One PNG per workflow step, at a fixed viewport so every slide is consistent.
Signs in as each role in turn — the screens genuinely differ by role, and a
deck that shows the admin's navigation to a branch user teaches the wrong
thing.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5199"
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "./shots")
OUT.mkdir(parents=True, exist_ok=True)

VIEWPORT = {"width": 1440, "height": 900}

USERS = {
    "branch":     ("sunita.desai@successbank.local", "Passw0rd@123"),
    "agent":      ("aisha.khan@successbank.local", "Passw0rd@123"),
    "supervisor": ("priya.sharma@successbank.local", "Passw0rd@123"),
    "admin":      ("admin@successbank.local", "Admin@123456"),
    "auditor":    ("deepak.iyer@successbank.local", "Passw0rd@123"),
}

captured: list[dict] = []


def shot(page, name: str, note: str = "") -> None:
    page.wait_for_timeout(900)          # let queries settle and charts draw
    path = OUT / f"{name}.png"
    page.screenshot(path=str(path))
    captured.append({"name": name, "file": path.name, "note": note})
    print(f"  captured {name}")


def login(page, who: str) -> bool:
    email, password = USERS[who]
    page.goto(f"{BASE}/login", wait_until="networkidle")
    page.fill('input[type="email"]', email)
    page.fill('input[type="password"]', password)
    page.click('button[type="submit"]')
    try:
        page.wait_for_url(lambda u: "/login" not in u, timeout=15000)
    except Exception:
        print(f"  !! login failed for {who}")
        return False
    page.wait_for_timeout(1200)
    return True


def logout(page) -> None:
    page.evaluate("() => { localStorage.clear(); }")


def visit(page, path: str, name: str, note: str = "") -> None:
    page.goto(f"{BASE}{path}", wait_until="networkidle")
    shot(page, name, note)


with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
    ctx = browser.new_context(viewport=VIEWPORT, device_scale_factor=2)
    page = ctx.new_page()

    # ---- Login screen, before anyone signs in -----------------------------
    page.goto(f"{BASE}/login", wait_until="networkidle")
    shot(page, "00-login", "The sign-in screen every role starts from")

    # ---- Branch user ------------------------------------------------------
    if login(page, "branch"):
        shot(page, "10-branch-dashboard", "What a branch user sees after signing in")
        visit(page, "/tickets", "11-branch-tickets", "Only their own tickets")
        visit(page, "/tickets/new", "12-branch-create-empty", "The raise-a-ticket form")

        # Fill it in so the deck shows a completed form, not an empty one.
        page.fill('input[name="title"]', "Duplicate debit on account ending 4417")
        page.fill(
            'textarea[name="description"]',
            "Two identical debits of 12,400 posted on 9 August. "
            "Customer has been charged twice. Screenshot and statement attached.",
        )
        page.select_option('select[name="priority"]', "high")
        page.wait_for_timeout(400)
        shot(page, "13-branch-create-filled", "The same form, completed")

        # First ticket in their list, for the detail view
        page.goto(f"{BASE}/tickets", wait_until="networkidle")
        try:
            page.locator("a[href^='/tickets/']").first.click()
            page.wait_for_timeout(1500)
            shot(page, "14-branch-ticket-detail", "Following a raised ticket")
        except Exception as e:
            print(f"  !! branch detail: {e}")
        logout(page)

    # ---- Agent ------------------------------------------------------------
    if login(page, "agent"):
        shot(page, "20-agent-dashboard", "The agent's dashboard, with live KPIs")
        visit(page, "/tickets", "21-agent-tickets", "Every ticket in scope")
        visit(page, "/tickets?status_group=open&sla_breached=true",
              "22-agent-breached", "The SLA Breached tile's drill-down")
        page.goto(f"{BASE}/tickets", wait_until="networkidle")
        try:
            page.locator("a[href^='/tickets/']").first.click()
            page.wait_for_timeout(1800)
            shot(page, "23-agent-ticket-detail", "Working a ticket")
            page.mouse.wheel(0, 900)
            page.wait_for_timeout(700)
            shot(page, "24-agent-ticket-comments", "Comments, attachments and the reply box")
        except Exception as e:
            print(f"  !! agent detail: {e}")
        logout(page)

    # ---- Supervisor -------------------------------------------------------
    if login(page, "supervisor"):
        shot(page, "30-supervisor-dashboard", "The supervisor's view")
        visit(page, "/sla", "31-supervisor-sla", "The SLA monitor")
        visit(page, "/escalations", "32-supervisor-escalations", "The escalation queue")
        logout(page)

    # ---- Admin ------------------------------------------------------------
    if login(page, "admin"):
        shot(page, "40-admin-dashboard", "The admin dashboard")
        visit(page, "/users", "41-admin-users", "User administration")
        visit(page, "/org", "42-admin-org", "The org hierarchy")
        visit(page, "/branches", "43-admin-branches", "The branch network")
        visit(page, "/reports", "44-admin-reports", "Reports and exports")
        visit(page, "/security", "45-admin-security", "Enrolling a second factor")
        logout(page)

    # ---- Auditor ----------------------------------------------------------
    if login(page, "auditor"):
        shot(page, "50-auditor-dashboard", "The auditor's dashboard — read only")
        visit(page, "/audit", "51-auditor-audit-log", "The immutable audit trail")
        visit(page, "/tickets", "52-auditor-tickets", "Full visibility, no write controls")
        logout(page)

    browser.close()

(OUT / "index.json").write_text(json.dumps(captured, indent=2))
print(f"\n{len(captured)} screenshots -> {OUT}")
