"""Assemble the captured screens into one self-contained walkthrough page.

    python docs/sop/build-walkthrough.py <shots-dir> <out.html>

The output is a single HTML file with every screenshot embedded, so it opens
from a file:// URL, an email attachment or a shared drive with nothing else
alongside it. That is the whole point: a walkthrough that needs a web server,
or a folder of images kept next to it, is one somebody cannot forward.

Two consequences of embedding, both deliberate:

**Images are data URIs, not `<img src="screens/...">`.** A relative path breaks
the moment the file is moved away from the folder, and a published artifact's
content policy blocks external image loads outright — a linked screenshot would
render as a broken box for every viewer. Encoding at 1400px wide JPEG keeps the
whole set to a few megabytes, and 1400px is already past what anyone reads on a
laptop.

**No `loading="lazy"` on the images.** Lazy loading exists to defer network
fetches; these bytes are already inside the document, so it saves nothing and
only risks an image sitting undecoded when the reader scrolls to it. The first
version had it, and fifteen of thirty-three showed blank.
"""

from __future__ import annotations

import base64
import io
import json
import sys
from pathlib import Path

from PIL import Image

SHOTS = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/sop/screens")
OUT = Path(sys.argv[2] if len(sys.argv) > 2
           else "docs/sop/SUCCESS-Bank-Application-Walkthrough.html")

#: Wide enough that the screenshot is readable, small enough that the whole
#: set stays a few megabytes. Raising this mostly buys file size.
TARGET_WIDTH = 1400
JPEG_QUALITY = 72

# The order a person actually meets these screens, grouped by who they are.
# `note` says what the screen is for. `watch` points at the one thing on it
# that is easy to miss and matters — leave it None where there isn't one
# rather than inventing filler.
JOURNEY: list[tuple[str, str | None, list[tuple[str, str, str, str | None]]]] = [
    ("Signing in", None, [
        ("00-login", "Sign in",
         "Bank email and password. Accounts lock after repeated failures.",
         "A wrong password and an unknown email give the same message and take the "
         "same time — otherwise the form tells an attacker which addresses exist."),
        ("45-admin-security", "Security & two-factor",
         "Password change and TOTP enrolment. Every signed-in role reaches this screen.",
         "Backup codes are single-use and hashed at rest, so a stolen database "
         "yields no working codes."),
    ]),
    ("Branch user — raising a problem", "branch_user", [
        ("10-branch-dashboard", "Their dashboard",
         "Only their own tickets. The org-wide analytics endpoints are never called "
         "for this role.",
         "This used to render four red error cards, because the page requested "
         "agent-only endpoints for everyone."),
        ("11-branch-tickets", "Their tickets",
         "Everything they raised, and nothing else.",
         "The filter is applied server-side, so another ticket cannot be reached by "
         "guessing its URL."),
        ("12-branch-create-empty", "Raise a ticket",
         "The empty form: title, description, category, priority, branch.", None),
        ("13-branch-create-filled", "Filled in, with evidence",
         "Files can be attached while raising, not only afterwards.",
         "Nobody is auto-assigned on submit. The system numbers the ticket and "
         "starts the clock; a supervisor chooses who works it."),
        ("15-branch-ticket-detail", "Watching it progress",
         "Status, owner, SLA state, and the replies they are allowed to see.",
         "Internal notes are absent here — and so are their attachments, which is "
         "the part people assume wrong."),
        ("16-branch-ticket-comments", "The conversation",
         "Replies from the agent, and their own answers back.", None),
    ]),
    ("Agent — working the queue", "agent", [
        ("20-agent-dashboard", "Agent dashboard",
         "What needs attention first: breaches, criticals, escalations.",
         "Every tile is a link. Clicking it opens the ticket list filtered to "
         "exactly the number shown, from the same threshold constant."),
        ("21-agent-tickets", "The full queue",
         "Filterable by status, priority, category and AI risk band.", None),
        ("22-agent-breached", "Filtered to breached",
         "What a dashboard tile opens when you click it.",
         "The number on the card and the row count here cannot disagree — they "
         "read one constant."),
        ("23-agent-ticket-detail", "Working a ticket",
         "Assign, progress, pause the SLA, resolve — plus the AI helpers.",
         "Status moves are checked against the lifecycle by the API. An illegal "
         "jump is refused, not merely hidden."),
        ("24-agent-ticket-comments", "Replying with a fix",
         "A reply, with the corrected document attached to that reply.",
         "A file belongs to the answer that explains it, rather than floating in a "
         "shared pile."),
    ]),
    ("Supervisor — watching the deadlines", "supervisor", [
        ("30-supervisor-dashboard", "Supervisor dashboard",
         "The same tiles, across a wider scope.", None),
        ("31-supervisor-sla", "SLA monitor",
         "Every open deadline, and what is about to miss one.",
         "The worker re-evaluates every five minutes and raises an escalation event "
         "on breach."),
        ("32-supervisor-escalations", "Escalation queue",
         "What the rules lifted, and the timeline of each one.",
         "A ticket does not escalate twice for the same trigger; the worker logs "
         "why when it declines."),
        ("33-supervisor-unassigned", "Unassigned work",
         "Tickets with no owner yet.", None),
        ("34-supervisor-assign-list", "Choosing an owner",
         "Open counts per person, and who is on leave.",
         "Someone on leave is excluded in SQL, so lowest-workload ordering only "
         "considers people who can actually take it."),
    ]),
    ("Knowledge base — asking and curating", None, [
        ("70-kb-answer", "Asking a question",
         "Plain words in; an answer with the passage each claim came from.",
         "Access is applied to the search itself. A passage your role has no grant "
         "on is never retrieved, so it cannot appear in an answer."),
        ("72-kb-abstain", "When it declines",
         "No grounded answer, and what would help instead.",
         "This is a success path, not a fault. Guessing would be the failure."),
        ("71-kb-documents", "Curating documents",
         "Upload, grant roles, re-index. Administrators only.",
         "A collection with no roles granted is flagged as not searchable — "
         "otherwise it accepts uploads and answers nothing."),
        ("70-knowledge-base", "The whole screen",
         "Status, ask panel, collections and documents together.", None),
        ("60-ai-assistant", "The AI assistant",
         "Conversational help grounded in what your role can already open.",
         "It can summarise and suggest. It cannot change a ticket — it tells you "
         "which button to use."),
    ]),
    ("Administrator — running the place", "admin", [
        ("40-admin-dashboard", "Admin dashboard",
         "Everything, across every unit and branch.", None),
        ("41-admin-users", "Users",
         "Who exists, what role they hold, which branch they belong to.",
         "An admin cannot edit a super-admin or grant the flag. Otherwise any admin "
         "could mint one and hold every privilege in two calls."),
        ("46-admin-users-availability", "Availability",
         "Who is on leave, and until when.", None),
        ("47-admin-leave-dialog", "Marking leave",
         "A date range that expires by itself.",
         "Auto-expiring, so nobody has to remember to switch it back off."),
        ("42-admin-org", "Org hierarchy",
         "The reporting tree that scopes ticket visibility.",
         "Visibility is the unit subtree plus anything assigned to you — separate "
         "from role."),
        ("43-admin-branches", "Branch network",
         "Status, manager, capacity and live load per branch.",
         "Open tickets and load are computed from the ticket table, never stored — "
         "a stored count goes stale."),
        ("44-admin-reports", "Reports",
         "The numbers, with PDF and Excel export.", None),
    ]),
    ("Auditor — sees everything, changes nothing", "auditor", [
        ("50-auditor-dashboard", "Auditor dashboard",
         "The same tiles everyone else sees.", None),
        ("52-auditor-tickets", "Every ticket",
         "No scope limit, and no action controls.",
         "The absence of buttons is honesty, not the boundary — the server refuses "
         "every write from this role."),
        ("51-auditor-audit-log", "The audit trail",
         "Who changed what, when, from where, with before and after values.",
         "Two database triggers refuse UPDATE, DELETE and TRUNCATE on this table "
         "for every connection, including the application's own."),
    ]),
]


def encode(name: str) -> str | None:
    """Downscale and encode one screenshot as a data URI."""
    path = SHOTS / f"{name}.png"
    if not path.exists():
        return None
    with Image.open(path) as im:
        width, height = im.size
        rgb = im.convert("RGB")
        if width > TARGET_WIDTH:
            rgb = rgb.resize(
                (TARGET_WIDTH, round(height * TARGET_WIDTH / width)), Image.LANCZOS
            )
        buf = io.BytesIO()
        rgb.save(buf, "JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def collect() -> list[dict]:
    screens, missing = [], []
    for group, role, items in JOURNEY:
        for name, title, note, watch in items:
            src = encode(name)
            if src is None:
                missing.append(name)
                continue
            screens.append({
                "id": name, "group": group, "role": role,
                "title": title, "note": note, "watch": watch, "src": src,
            })
    if missing:
        # Loud, not silent: a walkthrough quietly missing a screen is worse
        # than one that fails to build.
        print(f"  ! {len(missing)} screenshot(s) not found and skipped: "
              f"{', '.join(missing)}", file=sys.stderr)
    return screens


HEAD = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>SUCCESS Bank — Application Walkthrough</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#EDE4D8; --raised:#F0E7DB; --inset:#E8DFCF;
  --sh-dark:#C8BAA8; --sh-light:#FFFFFF;
  --neu-sm:4px 4px 8px var(--sh-dark), -4px -4px 8px var(--sh-light);
  --neu-md:8px 8px 16px var(--sh-dark), -8px -8px 16px var(--sh-light);
  --neu-in:inset 3px 3px 7px var(--sh-dark), inset -3px -3px 7px var(--sh-light);
  --brand:#0F5C5C; --brand-dk:#0A4444; --brand-xs:#D6ECEC;
  --tx:#1A1A1C; --tx-2:#4A4A4C; --tx-3:#8A8A8C;
  --line:rgba(180,160,136,.30);
  --warn:#B45309; --warn-bg:rgba(180,83,9,.10);
  --r2:8px; --r3:12px; --r4:16px; --rf:9999px;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --bg:#1A2828; --raised:#1F2F2F; --inset:#152222;
  --sh-dark:#0E1A1A; --sh-light:#243434;
  --brand:#1A7A7A; --brand-dk:#0F5C5C; --brand-xs:#123333;
  --tx:#E8EFED; --tx-2:#A8BAB8; --tx-3:#7A8E8C;
  --line:rgba(255,255,255,.10);
  --warn:#E0A056; --warn-bg:rgba(224,160,86,.14);
}}
:root[data-theme="dark"]{
  --bg:#1A2828; --raised:#1F2F2F; --inset:#152222;
  --sh-dark:#0E1A1A; --sh-light:#243434;
  --brand:#1A7A7A; --brand-dk:#0F5C5C; --brand-xs:#123333;
  --tx:#E8EFED; --tx-2:#A8BAB8; --tx-3:#7A8E8C;
  --line:rgba(255,255,255,.10);
  --warn:#E0A056; --warn-bg:rgba(224,160,86,.14);
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--tx);
  font-family:Inter,-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;font-size:14px;line-height:1.55}
button{font:inherit;color:inherit;cursor:pointer;border:none;background:none}
button:focus-visible{outline:2px solid var(--brand);outline-offset:2px;border-radius:6px}
img{max-width:100%;display:block}
@media (prefers-reduced-motion:reduce){*{transition:none!important;scroll-behavior:auto!important}}
.top{background:var(--brand);color:#fff;padding:26px 24px}
.top .in{max-width:1340px;margin:0 auto;display:flex;flex-wrap:wrap;gap:16px;align-items:flex-end;justify-content:space-between}
.top h1{margin:0;font-size:clamp(22px,3.4vw,31px);font-weight:700;letter-spacing:-.02em}
.top p{margin:6px 0 0;opacity:.88;max-width:62ch;font-size:14.5px}
.eyebrow{font-family:"IBM Plex Mono",monospace;font-size:11px;letter-spacing:.15em;text-transform:uppercase;opacity:.7;margin:0 0 7px}
.roles{display:flex;gap:6px;flex-wrap:wrap}
.roles button{border-radius:var(--rf);padding:6px 13px;font-size:12.5px;font-weight:600;background:rgba(255,255,255,.14);color:#fff;transition:background 140ms ease}
.roles button:hover{background:rgba(255,255,255,.26)}
.roles button[aria-pressed="true"]{background:#fff;color:var(--brand-dk)}
.wrap{max-width:1340px;margin:0 auto;padding:22px 24px 70px;display:grid;grid-template-columns:266px 1fr;gap:24px;align-items:start}
@media (max-width:980px){.wrap{grid-template-columns:1fr}}
.toc{position:sticky;top:16px;max-height:calc(100vh - 32px);overflow:auto;background:var(--raised);border-radius:var(--r4);box-shadow:var(--neu-md);padding:16px 14px}
@media (max-width:980px){.toc{position:static;max-height:none}}
.toc h2{margin:12px 0 6px;padding:0 8px;font-size:10px;font-weight:600;letter-spacing:.12em;text-transform:uppercase;color:var(--tx-3)}
.toc h2:first-of-type{margin-top:0}
.toc button{display:block;width:100%;text-align:left;padding:7px 10px;border-radius:var(--r2);font-size:13px;color:var(--tx-2);transition:background 130ms ease,color 130ms ease}
.toc button:hover{background:var(--inset);color:var(--tx)}
.toc button[aria-current="true"]{background:var(--brand);color:#fff;font-weight:600}
.count{font-size:11px;color:var(--tx-3);padding:0 8px 10px;font-family:"IBM Plex Mono",monospace}
.stage{min-width:0}
.shot{background:var(--raised);border-radius:var(--r4);box-shadow:var(--neu-md);padding:18px;margin-bottom:22px}
.shot .hd{display:flex;gap:12px;align-items:baseline;flex-wrap:wrap;margin-bottom:4px}
.shot h3{margin:0;font-size:18px;font-weight:700;letter-spacing:-.01em}
.chip{font-size:10px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;padding:3px 9px;border-radius:var(--rf);background:var(--brand-xs);color:var(--brand)}
.shot .note{color:var(--tx-2);font-size:13.5px;margin:0 0 14px;max-width:74ch}
.frame{background:var(--inset);box-shadow:var(--neu-in);border-radius:var(--r3);padding:9px}
.frame img{border-radius:var(--r2);width:100%;height:auto}
.watch{display:flex;gap:11px;align-items:flex-start;margin-top:14px;background:var(--warn-bg);border:1px solid var(--warn);border-radius:var(--r3);padding:11px 14px}
.watch .i{flex:none;width:19px;height:19px;border-radius:var(--rf);background:var(--warn);color:#fff;font-size:11px;font-weight:700;display:flex;align-items:center;justify-content:center;margin-top:1px}
.watch p{margin:0;font-size:13px;color:var(--tx);line-height:1.55}
.watch b{font-weight:600}
.groupbar{display:flex;align-items:baseline;gap:12px;margin:34px 0 14px;flex-wrap:wrap}
.groupbar h2{margin:0;font-size:20px;font-weight:700;letter-spacing:-.015em}
.groupbar span{font-size:12px;color:var(--tx-3);font-family:"IBM Plex Mono",monospace}
.groupbar::after{content:"";flex:1;height:1px;background:var(--line);min-width:30px}
.nav{display:flex;justify-content:space-between;gap:12px;margin-top:8px}
.nav button{background:var(--inset);box-shadow:var(--neu-sm);border-radius:var(--r2);padding:9px 15px;font-size:12.5px;font-weight:500;color:var(--tx-2)}
.nav button:hover{color:var(--tx)}
.nav button[disabled]{opacity:.4;cursor:default}
.empty{background:var(--raised);border-radius:var(--r4);box-shadow:var(--neu-md);padding:34px;text-align:center;color:var(--tx-2)}
footer.end{max-width:1340px;margin:0 auto;padding:20px 24px 60px;border-top:1px solid var(--line);font-family:"IBM Plex Mono",monospace;font-size:11.5px;color:var(--tx-3)}
</style></head><body>
<header class="top"><div class="in">
  <div>
    <p class="eyebrow">SUCCESS Bank &middot; Internal Ticketing</p>
    <h1>Walking through the application</h1>
    <p>Screens captured from the running product &mdash; not drawn. This is what staff actually see, in the order they meet it.</p>
  </div>
  <div class="roles" role="group" aria-label="Filter by role">
    <button data-role="all" aria-pressed="true">All</button>
    <button data-role="branch_user" aria-pressed="false">Branch user</button>
    <button data-role="agent" aria-pressed="false">Agent</button>
    <button data-role="supervisor" aria-pressed="false">Supervisor</button>
    <button data-role="admin" aria-pressed="false">Admin</button>
    <button data-role="auditor" aria-pressed="false">Auditor</button>
  </div>
</div></header>
<div class="wrap">
  <nav class="toc" id="toc" aria-label="Screens"></nav>
  <main class="stage" id="stage"></main>
</div>
<footer class="end">Captured from the running application &middot; SUCCESS Bank Internal Ticketing</footer>
<script>
var SCREENS = """

TAIL = r""";
(function () {
  "use strict";
  var state = { role: "all" };

  function esc(s){return String(s == null ? "" : s).replace(/[&<>"]/g,function(c){
    return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c];});}

  function visible(){
    if (state.role === "all") return SCREENS;
    // A screen with no role belongs to every journey (sign in, knowledge base).
    return SCREENS.filter(function(s){ return s.role === null || s.role === state.role; });
  }

  function render(){
    var list = visible();
    var toc = document.getElementById("toc");
    var stage = document.getElementById("stage");
    if (!list.length){
      toc.innerHTML = "";
      stage.innerHTML = '<div class="empty">No screens for that role.</div>';
      return;
    }
    var seen = {}, tocHtml = "";
    list.forEach(function(s, i){
      if (!seen[s.group]){ seen[s.group] = true; tocHtml += "<h2>"+esc(s.group)+"</h2>"; }
      tocHtml += '<button data-go="'+i+'">'+esc(s.title)+"</button>";
    });
    toc.innerHTML = '<div class="count">'+list.length+" screens</div>" + tocHtml;

    var seen2 = {}, html = "";
    list.forEach(function(s, i){
      if (!seen2[s.group]){
        seen2[s.group] = true;
        var n = list.filter(function(x){ return x.group === s.group; }).length;
        html += '<div class="groupbar"><h2>'+esc(s.group)+"</h2><span>"+n+" screen"+(n===1?"":"s")+"</span></div>";
      }
      // No loading="lazy": the bytes are data URIs already inside the document,
      // so it saves no fetch and only risks an undecoded image on arrival.
      html += '<section class="shot" id="s'+i+'">'+
        '<div class="hd"><h3>'+esc(s.title)+"</h3>"+
          (s.role ? '<span class="chip">'+esc(s.role.replace("_"," "))+"</span>" : "")+
        "</div>"+
        (s.note ? '<p class="note">'+esc(s.note)+"</p>" : "")+
        '<div class="frame"><img decoding="async" alt="'+esc(s.title)+
          ' — screenshot of the running application" src="'+s.src+'"></div>'+
        (s.watch ? '<div class="watch"><span class="i">!</span><p><b>Worth noticing.</b> '+esc(s.watch)+"</p></div>" : "")+
        '<div class="nav">'+
          '<button data-go="'+(i-1)+'"'+(i===0?" disabled":"")+">&larr; Previous</button>"+
          '<button data-go="'+(i+1)+'"'+(i===list.length-1?" disabled":"")+">Next &rarr;</button>"+
        "</div></section>";
    });
    stage.innerHTML = html;
    wire(list.length);
    mark();
  }

  function wire(total){
    var nodes = document.querySelectorAll("[data-go]");
    for (var i=0;i<nodes.length;i++){
      (function(b){
        b.addEventListener("click", function(){
          var n = parseInt(b.getAttribute("data-go"), 10);
          if (n < 0 || n >= total) return;
          var el = document.getElementById("s"+n);
          if (el) el.scrollIntoView({ behavior:"smooth", block:"start" });
        });
      })(nodes[i]);
    }
  }

  // Highlight whichever screen is nearest the top of the viewport.
  function mark(){
    var shots = document.querySelectorAll(".shot");
    var links = document.querySelectorAll("#toc [data-go]");
    function update(){
      var best = 0, bestD = Infinity;
      for (var i=0;i<shots.length;i++){
        var d = Math.abs(shots[i].getBoundingClientRect().top - 90);
        if (d < bestD){ bestD = d; best = i; }
      }
      for (var j=0;j<links.length;j++){
        links[j].setAttribute("aria-current",
          String(parseInt(links[j].getAttribute("data-go"),10) === best));
      }
    }
    window.removeEventListener("scroll", window.__wt);
    window.__wt = update;
    window.addEventListener("scroll", update, { passive:true });
    update();
  }

  var rb = document.querySelectorAll(".roles button");
  for (var k=0;k<rb.length;k++){
    (function(b){
      b.addEventListener("click", function(){
        state.role = b.getAttribute("data-role");
        for (var n=0;n<rb.length;n++) rb[n].setAttribute("aria-pressed", String(rb[n]===b));
        render();
        window.scrollTo({ top:0, behavior:"smooth" });
      });
    })(rb[k]);
  }

  render();
})();
</script></body></html>
"""


def main() -> int:
    screens = collect()
    if not screens:
        print("No screenshots found — run capture-screens.py first.", file=sys.stderr)
        return 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(HEAD + json.dumps(screens, separators=(",", ":")) + TAIL)
    size = OUT.stat().st_size / 1_048_576
    print(f"saved {OUT}  ({len(screens)} screens, {size:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
