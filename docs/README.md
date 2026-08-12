# Documentation

| # | Document | Answers |
|---|---|---|
| 01 | [Product Requirements](01-product-requirements.md) | Who uses this, what it must do, what it deliberately does not do |
| 02 | [Technical Architecture](02-technical-architecture.md) | How it is put together, and the decisions that bite if forgotten |
| 03 | [Security & Access](03-security-and-access.md) | Who can do what, how it is enforced, and what is *not* protected |
| 04 | [Frontend Specification](04-frontend-specification.md) | Routes, states, the attachment flow, performance budget |
| 05 | [Feature Tickets](05-feature-tickets.md) | What is left, sized and sequenced |
| — | [Runbook](runbook.md) | Deploy, roll back, restore, and what to do at 3am |
| — | [Roadmap](roadmap.md) | Phase history |

## These are as-built

They describe the system at `c554e3c`, not a plan for one. Where something is
specified but unimplemented, the document says so — a requirements document
that quietly presents intentions as facts is worse than none.

Two consequences worth stating:

- **They will drift.** Anything asserting a number (326 tests, 90 endpoints,
  7 migrations) is true at that commit and nowhere else. Check before quoting.
- **Gaps are listed as gaps.** No TLS, no malware scanning, audit immutability
  by convention only, no general rate limiting. These are in §9 of the security
  document and as P0/P1 tickets, not omitted to make the picture tidier.

## `architecture.md` is stale

It predates the current code and describes things that do not exist: `core/rbac`
as the enforcement point, `services/sla_engine`, a `notifications` table, an
in-app SSE notification fan-out, and a 60-second scheduler. Document 02 replaces
it. Removing it is ticket **DOC-1**.
