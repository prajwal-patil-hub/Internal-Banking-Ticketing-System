# Frontend Specification

**Status: as-built at `c554e3c`.** 15 pages, 15 shared components, 42 tests.

---

## 1. Stack and structure

React 18 · TypeScript · Vite · TailwindCSS · React Query · React Router ·
zustand · Recharts · axios.

```
src/
  app/App.tsx         routes, guards, Suspense boundary
  pages/              15 route components
  components/         15 shared
  features/<domain>/  api.ts + types, one per backend domain
  lib/                api.ts, files.ts, cn.ts
  store/auth.ts       zustand, persisted
  test/setup.ts       vitest + jsdom
```

**Server state is React Query; client state is zustand.** Auth is the only
persisted store. Nothing else is duplicated into local state — a fetched ticket
lives in the query cache and nowhere else.

## 2. Routes and who reaches them

| Path | Page | Roles |
|---|---|---|
| `/login` | LoginPage | anonymous |
| `/dashboard` | DashboardPage | all authenticated |
| `/tickets` | TicketsPage | all |
| `/tickets/new` | CreateTicketPage | all |
| `/tickets/:id` | TicketDetailPage | all (scoped) |
| `/sla` | SLAMonitorPage | admin, supervisor |
| `/escalations` | EscalationsPage | admin, supervisor |
| `/branches` | BranchesPage | admin, supervisor, auditor |
| `/users` | UsersPage | admin |
| `/org` | OrgManagementPage | admin |
| `/reports` | ReportsPage | admin, supervisor, auditor |
| `/audit` | AuditPage | admin, auditor |
| `/security` | SecurityPage | all (own MFA) |
| `/forbidden` | ForbiddenPage | — |

**Route guards are convenience, not security.** They stop someone navigating to
a page that would only 403. Every one of these endpoints enforces the same rule
server-side.

## 3. Loading, error and empty states

Every data view must handle four states. This is a requirement — a page that
renders nothing while loading reads as broken.

| State | Treatment |
|---|---|
| Loading | Skeleton matching the final layout's shape, not a spinner |
| Error | Inline card with the server's message and a Retry button |
| Empty | A sentence saying what would appear here |
| Ready | The content |

Errors always come from `extractError()`, which reads this API's envelope
(`{error: {message}}`). Two pages once read FastAPI's `detail` instead and
silently showed generic text for every failure — including "Only a super admin
can grant super admin privileges", which the user needed to see.

## 4. The dashboard

Nine live tiles: eight in the KPI strip, plus the AI panel.

**Every tile that stands for a set of tickets navigates to that set, filtered
to reproduce its own number.** A card reading "17 breached" that opens an
unfiltered list reads as a broken filter, so the pairing is asserted in the
backend test suite.

| Tile | Opens |
|---|---|
| Open | `?status_group=open` |
| SLA Breached | `?status_group=open&sla_breached=1` |
| Resolved | `?status=resolved&resolved_from=<today>` |
| Critical | `?status_group=open&priority=critical` |
| AI Sorted | `?ai_categorized=1&created_from=<7d>` |
| Via Email | `?source=email&created_from=<today>` |
| Escalated | `/escalations` |
| Avg Resolve | `/reports` |
| AI High Risk | `?status_group=open&ai_risk=high` |
| AI-Assisted Resolved | `?status_group=closed&ai_categorized=1&resolved_from=<7d>` |

**Avg Confidence and Avg Latency deliberately do not navigate.** They describe
the model, not a list of tickets; linking them somewhere arbitrary would be
worse than leaving them inert.

Date boundaries must match the backend's. The KPIs count from midnight UTC, so
the drill-downs do too.

## 5. Attachments

Files attach at three points, and the flow is the same in each: **stage in the
browser, upload once the thing they belong to exists.**

A ticket cannot own a file before it has an id, and neither can a reply. So
`FileStager` holds files while the user is still writing and owns no network
code at all — the page decides when to send them.

### FileStager

| Behaviour | Reason |
|---|---|
| Rejects over 15 MB, keeps the rest of the batch | Dropping the whole selection makes the user re-pick files that were fine |
| Same name + size counts once | That is a double-click, not two documents |
| Offers only accepted types in the picker | Avoids a rejection the user could not have predicted |
| Drag-and-drop and click both work | — |

### Upload ordering

Uploads run **one at a time**. Five screenshots should not open five concurrent
multipart requests, and the failure that matters — storage being down — is the
one where parallelism helps least.

Each file reports its own outcome. If one fails the others still upload, and
the page names the failures. **The ticket is what matters**: if an upload fails
the ticket still exists and the user is told which files to re-attach, rather
than losing a written-out problem report because a screenshot did not go
through.

### Rendering

- Files sent with a reply render **under that reply**, so an agent's fix sits
  beside the answer explaining it.
- The Attachments panel is the file index for the whole ticket and marks
  reply-borne files "from a reply".
- Download goes through the API and saves via a blob URL.

## 6. The assistant widget

- Streams over SSE using `fetch` + `ReadableStream`. **axios cannot be used** —
  XHR buffers the body and the stream arrives as one late blob.
- Falls back to the blocking endpoint if streaming fails, but **only if nothing
  has rendered yet**; otherwise the user would see the answer restart.
- On failure it asks `/ai/health` and appends the hint, because the cause is
  usually a local-Ollama setup problem rather than a bug.
- Sends real page context so "what should I pick up first?" is answerable.

## 7. Auth in the client

- Access token in `localStorage`, attached by a request interceptor.
- **Single-flight refresh on 401.** Three concurrent 401s must produce one
  refresh call: the second would present a token the first had just revoked,
  and the server treats reuse as theft and kills the entire chain.
- The rotated refresh token is stored too — keeping the old one guarantees the
  next refresh fails.
- A failed refresh clears both keys and dispatches `auth:logout`.
- MFA: a `403 MFA_REQUIRED` carries a challenge token; the client collects a
  code or a recovery code and exchanges it at `/auth/mfa/verify`.

## 8. Performance

Route-level `React.lazy` with vendor chunks split by change frequency:

| Chunk | Size | Loaded |
|---|---|---|
| `vendor-charts` | 411 kB | Only on Dashboard/Reports |
| `vendor-react` | 165 kB | Always |
| `vendor-data` | 88 kB | Always |
| `vendor-forms` | 83 kB | Forms only |
| `index` | 88 kB | Always |

Someone opening a ticket does not download the charting library. Assets are
content-hashed and served `immutable`; `index.html` is `no-store`, because it
names the current bundles and a cached copy pins the browser to a deployment
that no longer exists.

## 9. Testing

42 tests under vitest + jsdom, covering where a silent break would hurt:

- `uploadAttachments` — per-file outcomes, serial ordering, progress on failure
- `FileStager` — size rejection, batch survival, duplicates, accepted types
- `refreshAccessToken` — single-flight, latch clearing, credential cleanup
- `files.ts` — size formatting, glyphs, extension fallback

Limits pinned against the server's own values, since those are what drift.

**Not covered:** page-level rendering, routing guards, chart rendering. The
gap worth closing next is a TicketDetailPage test asserting that an internal
comment's attachments never render for a branch user — currently proven
server-side only.

## 10. Conventions

- **Tailwind + CSS custom properties** (`var(--tx)`, `var(--brand)`,
  `var(--err)`) so theming is one place.
- `cn()` merges classes; no string concatenation.
- Icons are inline SVG — no icon package.
- Every interactive element has an accessible name; icon-only buttons carry
  `aria-label`.
- **Known gap:** the file input is hidden and opened by a visible button, so it
  has no accessible name of its own. Fine for mouse and for the button's own
  keyboard path, worth revisiting if the input must be reachable directly.
