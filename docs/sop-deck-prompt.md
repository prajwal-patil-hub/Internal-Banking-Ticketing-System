# Prompt — Role-Based SOP / User Manual (PPTX)

Reworked for **SUCCESS Bank Internal Ticketing**. Differences from the generic
version it came from are listed at the end, with reasons.

---

## The ask

Create a professional, enterprise-grade **Standard Operating Procedure deck**
(`.pptx`) for the ticketing system in this repository.

This must **not** be an overview presentation. It is a step-by-step
operational guide that walks each role through its complete workflow using
**real screenshots captured from the running application**.

A new joiner should finish the deck able to answer:

> Who am I → what may I do → which screen do I open → what do I click → what do
> I type → what happens next → who picks it up → how does this ticket end?

---

## 1. Capture the screens first — do not draw them

Playwright and Chromium are available (`PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers`).
`python-pptx` is available. So:

1. Start Postgres, an S3-compatible store, the backend and the frontend.
2. Seed demo data (`scripts/seed_dev.py`) so screens are populated — an empty
   dashboard teaches nothing.
3. Log in **as each role in turn** and screenshot every screen in its workflow
   at a consistent viewport (1440×900).
4. Embed those PNGs in the deck.

**If a screen cannot be captured, say so on the slide.** Do not draw a mock-up
of a screen that exists, and do not describe a screen you have not seen.

## 2. Use the real roles

The five roles are `branch_user`, `agent`, `supervisor`, `admin` and
`auditor`, with `is_super_admin` as a second tier on top of `admin`.

**There is no L1/L2 tier, no separate helpdesk queue, and no approval step.**
Do not import that structure from a generic ITSM template — document the
handoffs this system actually has.

Seeded logins are in the README; use them.

## 3. Use the real lifecycle

Nine statuses: `new`, `acknowledged`, `assigned`, `in_progress`, `on_hold`,
`escalated`, `resolved`, `closed`, `reopened`.

Transitions are enforced by `VALID_TRANSITIONS` in
`backend/app/services/ticket_service.py`. Read it and reproduce it exactly.

Two facts a reader will get wrong unless told:

- `closed` is reachable from **any** open state — closing early is a
  withdrawal, not a resolution.
- `resolved` is **not** reachable from `assigned`; the ticket must have been
  worked (`in_progress` or `escalated`) first.

## 4. Document only what exists

Verify each claim against the code before it goes on a slide. In particular:

| Do not claim | Reality |
|---|---|
| Approval workflows | None exist |
| In-app notifications | Email only, via `notification_service` |
| Per-user permissions | One role per user; the `permissions` tables are seeded but never read |
| Ticket merging | Not implemented (duplicate marking is) |
| Customer self-service portal | Every account is an employee account |

If the deck would be more useful with a feature that does not exist, note it as
a gap — do not present it as working.

## 5. Structure

```
01  Title and how to use this deck
02  System overview — what it is for, one diagram
03  Roles and permissions — one table, plus what each cannot do
04  Ticket lifecycle — the real state machine
05  End-to-end journey — swimlane across all five roles
06  Branch user workflow      ── step per slide, real screenshot
07  Agent workflow            ── step per slide, real screenshot
08  Supervisor workflow       ── step per slide, real screenshot
09  Admin workflow            ── step per slide, real screenshot
10  Auditor workflow          ── step per slide, real screenshot
11  Attachments — the rule about internal notes
12  The AI assistant — what it can and cannot do
13  Common scenarios, end to end
14  Quick reference — statuses, who does what, where to click
```

Section count is fixed; **slide count is not**. If the agent workflow needs
twelve steps, it gets twelve slides. Do not compress to hit a target.

## 6. Every workflow slide carries the same six things

```
Step NN — <short imperative title>
[ screenshot, large enough to read ]
① ② ③   numbered callouts on the elements that matter
Action:   what the user does, in one sentence
Result:   what the system does in response
Next:     the following step, or the role that takes over
```

One screen per slide. No collages of five shrunken screenshots.

## 7. Cover the handoffs explicitly

The point of a role-based SOP is the seams. Give each of these its own slide
showing both sides:

- Branch user raises → auto-assignment picks an agent (and **why it prefers
  agents over supervisors**)
- Agent escalates → supervisor receives
- SLA breach → escalation fires automatically, without anyone clicking
- Agent resolves → branch user sees the resolution and its attachments
- Reopen → the ticket returns to the open set

## 8. State the rules that are invisible on screen

Some behaviour cannot be seen in a screenshot and will otherwise be discovered
the hard way:

- **Internal notes and their attachments are invisible to the branch user.**
  The attachment rule is the one most likely to be assumed wrong.
- **Auditors can read everything and write nothing** — every write is refused.
- **A ticket will not escalate twice for the same trigger.**
- **The assistant cannot see more than the signed-in user can**, and cannot
  change anything.
- **Uploads are capped at 15 MB**, and executables and archives are refused.

## 9. Design

Corporate and plain. Consistent type scale, generous margins, a section divider
before each part, page numbers, and a fixed callout style.

No stock imagery, no gradients, no decorative icons. The screenshot is the
content; everything else is scaffolding for it.

## 10. Before delivering, check

- [ ] Every screenshot came from the running app
- [ ] Every role's workflow is complete from login to a finished ticket
- [ ] Every status transition shown is in `VALID_TRANSITIONS`
- [ ] No feature appears that does not exist
- [ ] Permissions on the slides match `core/authz.py`
- [ ] The deck opens without repair prompts in PowerPoint, Keynote and Slides
- [ ] Screenshots are legible at 100% zoom

---

## What changed from the original prompt, and why

| Original | Here | Why |
|---|---|---|
| Requester / L1 / L2 / Manager / Admin | branch_user / agent / supervisor / admin / auditor | The original roles do not exist here. A deck describing an L2 team teaches a structure this system does not have |
| "Use screenshots **or** wireframes" | Screenshots only, captured live | Playwright and Chromium are available, so there is no reason to draw. A drawn screen that disagrees with the real one is worse than no picture |
| Suggested statuses `New → Assigned → … → Closed` | The nine real statuses and their real edges | The original list omits `acknowledged`, `on_hold` and `reopened`, and implies transitions the API rejects |
| Approvals, in-app notifications, merging | Named as **not implemented** | The generic prompt assumes a fuller ITSM product; asserting these would be fiction |
| Ticket flows through tiers | Handoffs get their own slides | With no tiering, the interesting part is the seams — auto-assignment, escalation, resolution visibility |
| — | §8, invisible rules | Added. The internal-note attachment rule cannot be seen in a screenshot and is the one people assume wrong |
| — | "If a screen cannot be captured, say so" | Added, so a gap is visible rather than papered over |
