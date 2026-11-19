# Where a model would make this application faster

Status: **analysis and proposal**. Nothing here is built.

The brief was "introduce a model wherever it can make things faster". This
walks the application and answers that, in the order the work is worth doing.

The conclusion is not the obvious one. **Most of the speed available here comes
from taking the language model *off* the path a person is waiting on, and
putting embeddings *on* it.** A bigger or better LLM makes every number below
worse, not better.

## What the code actually does today

Established by reading it, not by assuming:

| Fact | Where |
|---|---|
| Ticket search is `ILIKE '%term%'` on title, description and number | `routes/tickets.py:392-398` |
| A leading wildcard cannot use a B-tree index, so every search is a sequential scan | — |
| The knowledge base has a GIN `to_tsvector` index *and* a pgvector HNSW index | migration `0009` |
| Tickets have neither. No embedding column, no similarity lookup, nowhere | `models/ticket.py`, `ticket_service.py` |
| `AIService.categorize_ticket()` is written, works, and has four passing tests | `ai_service.py:148`, `tests/test_ai_service.py` |
| **Nothing calls it.** No route, no worker, no service | grep across `app/` |
| Portal ticket creation performs no AI at all — zero references | `ticket_service.py` |
| `ai_category` and `ai_risk_score` are written in exactly one place: email intake | `email_service.py:342,344` |
| So the "AI Sorted" KPI (`ai_category IS NOT NULL`) can only ever count email tickets | `routes/dashboard.py:118-120` |
| `redis==5.0.8` is a declared dependency. It is imported nowhere | `pyproject.toml`, grep |
| `AI_TIMEOUT_SECONDS = 180`, and summarise/suggest run inside the request | `config.py:100`, `ticket_ai.py:152,169` |

Two of these deserve to be stated plainly, because they are the same class of
defect this project has caught before — something that looks finished and never
runs.

**A tested classifier that nobody calls.** `categorize_ticket` has four tests
covering its happy path, markdown-fence stripping, invalid JSON and API
failure. All pass. The function is correct. It is also dead: the only
categorisation that ever happens is a different code path inside email intake.
The tests are why this went unnoticed — a green suite reported health for code
that was never reachable.

**An AI enrichment layer that only one channel gets.** A ticket raised in the
portal has no category and no risk score, forever. This is the same asymmetry
already fixed for `ai-summarize` (recorded in PR #5: "read a column only email
intake ever writes, so a portal-raised ticket always showed *AI summary not yet
generated*"). The fix there was applied to summarisation only; categorisation
and risk still have it.

It also quietly mislabels a dashboard metric. "AI Sorted" presents as an AI
coverage number and is structurally a *channel* number — it rises when more
email arrives, and no amount of AI working well on portal tickets can move it.

---

## 1. Embed tickets, and show the agent what was done last time

**The biggest saving, and it reuses infrastructure that already exists.**

Most banking tickets are repeats. A UPI transfer stuck for two hours, a card
declined abroad, a disputed ATM debit — the bank has resolved each of these
hundreds of times. The slow part of an agent's job is not typing; it is
*finding the precedent*: the ticket from three weeks ago that looked like this
one, and what actually fixed it.

Today there is no way to do that. `ILIKE '%card declined%'` finds tickets
containing that literal phrase and misses "debit card refused at POS", which is
the same problem in different words.

The pieces are already built and tested for the knowledge base: pgvector in the
same Postgres instance, an HNSW index with `vector_cosine_ops`,
`nomic-embed-text` at 768 dimensions, and a chunking and embedding pipeline
with a two-phase write so nothing is ever half-indexed.

What to add:

- An `embedding vector(768)` column on `tickets`, plus an HNSW index. The same
  shape as `kb_chunks`, for the same reasons.
- Embed `title + description` **at intake, in the existing assignment worker**
  — which already runs every five minutes under a Postgres advisory lock
  (`assignment_worker.py:38-47`). Nobody waits for this.
- On the ticket detail screen: the five most similar **resolved** tickets, each
  with its resolution. No model call at read time — a vector index lookup, so
  single-digit milliseconds rather than the seconds an LLM round-trip costs.

**Why this is the first item:** it saves human minutes, not machine
milliseconds, and human minutes are what the bank is paying for. It also adds
no new failure mode to the request path, because the expensive half happens
before anyone asks.

**The security rule it must follow:** similarity is not a permission. A branch
user must never see another branch's ticket because the vectors were close. The
precedent panel is agent-and-above, and the query carries the same scope filter
the ticket list already applies. `kb_retrieval_service.accessible_collections`
is the pattern to copy — a single `WHERE` that a later performance rewrite
cannot flatten away.

## 2. Point the retrieval service that already exists at tickets

`kb_retrieval_service` already does dense retrieval, lexical retrieval, and
Reciprocal Rank Fusion over the two. That is a better search than the ticket
list has, and it is written, reviewed and tested.

Once tickets carry embeddings, the ticket search box can use it instead of
`ILIKE`. That removes a sequential scan from the most-used screen in the
product, and makes the search understand that "not working" and "declined" are
the same complaint.

Deliberately second, not first: it changes a screen every role uses daily, so
it wants the embeddings proven on the quieter precedent panel first.

## 3. Wake the dead classifier — at intake, not on request

`categorize_ticket` works. Call it. But call it in the **worker**, not in the
create-ticket request.

- Agent opens a portal ticket and the category is already there, as it is for
  email tickets today.
- Nobody waits on `glm4`. Ticket creation stays as fast as it is now.
- The "AI Sorted" KPI starts measuring what its label claims.

The cost of getting this wrong is worth naming: a mis-categorised ticket routes
to the wrong desk. So the category stays **advisory and visibly editable**, as
the email path already treats it — the model proposes, the agent disposes, and
the correction is what feeds item 5.

## 4. Precompute the summary instead of making someone wait for it

Today an agent clicks *Summarise*, and the request blocks on `glm4` with a
180-second timeout. On a long ticket thread that is a real wait, and the agent
is staring at a spinner for information the system could have had ready.

Generate it on arrival, in the same worker, and store it. The button becomes
instant. Keep an explicit *Regenerate* for when the thread has moved on since.

Same model, same token cost, same output — the only thing that changes is who
is waiting, and the answer becomes nobody. This is the cheapest latency win in
the application and it needs no new model at all.

## 5. Later: a small trained model where the LLM is overkill

Categorisation and risk scoring are **classification**, and an LLM is an
expensive way to classify. Once there are enough labelled examples, a gradient
boosting model (scikit-learn, LightGBM) does in about a millisecond what `glm4`
does in seconds — deterministically, on CPU, with no prompt to drift.

**The labels already exist as a by-product.** Every time an agent corrects a
category, that is a labelled example: the text, the model's guess, and the
right answer. Capture those corrections from day one of item 3, and the
training set builds itself. Do not start here — start by collecting the labels.

For a bank, the determinism matters more than the speed. A regulator asking why
a complaint was scored high-risk can be shown a feature importance table and a
decision path. A prompt is not an explanation, and "the model said so" is not
an audit answer. This is the one place where a *smaller*, older, less impressive
model is the more defensible engineering choice.

Rough threshold: a few thousand corrected tickets per category before the
trained model beats the LLM. Below that, the LLM's general knowledge wins.

## 6. Use the Redis that is already a dependency

`redis==5.0.8` is installed in every image and imported nowhere.

The dashboard runs six aggregate queries per user, refreshed every thirty
seconds (`STALE = 30_000`, `refetchInterval: STALE`). For every admin and
supervisor looking at the same scope, those six queries compute the same
numbers from the same rows. With twenty supervisors watching a dashboard, that
is 120 aggregate queries a minute producing six distinct answers.

Cache the aggregates on the scope key with a thirty-second TTL — matching the
refresh interval the client already assumes, so no one sees staler data than
they do now. Near-zero database load, and an instant dashboard.

This is not a model at all, which is rather the point: it is the largest
machine-time saving on the list and it needs no AI.

---

## What not to do

**Do not reach for a bigger model.** Every item above either removes a model
call from the waiting path or replaces one with a vector lookup. Swapping
`glm4` for something larger makes items 3 and 4 slower and changes nothing
else. If a model is ever swapped, the reason should be answer *quality* — and
that is unmeasured until `evals/golden_set.yaml` has a subject expert's name on
it instead of `reviewed_by: null`.

**Do not add streaming to hide latency.** The chat already streams, correctly.
Streaming a summary the system could have computed an hour ago is making a
spinner more entertaining instead of deleting the wait.

## Order, and why

| # | Change | Saves | Risk | Needs |
|---|---|---|---|---|
| 6 | Redis cache on dashboard aggregates | DB load, page load | Very low | Nothing new |
| 4 | Precompute summaries at intake | Up to 180s per click | Very low | Nothing new |
| 3 | Call the existing classifier in the worker | Agent triage time | Low | Nothing new |
| 1 | Ticket embeddings + precedent panel | Agent research time | Medium | A migration |
| 2 | Hybrid retrieval for ticket search | Search time and quality | Medium | Item 1 |
| 5 | Trained classifier | Model latency, auditability | Higher | Labels from 3 |

Items 6, 4 and 3 need **no new technology** — they use a dependency already
installed, a worker already running, and a function already written and tested.
That is most of the available win, and it can be had this week.

## Measure first

This project has been bitten repeatedly by things that looked done and were
never exercised: a layout audit passing while markers pointed at the wrong
controls, a citation validator blind to the token it existed to reject, two
capture scripts that had silently drifted apart. A performance list assembled
by reading code has the same weakness.

So before building any of it, instrument it. `RequestContextMiddleware` already
carries a request id; add server-timing for the dashboard aggregates, the
ticket list query and each AI call, and look at a day of real traffic. The
ranking above is a hypothesis about where the time goes. It should be checked
against where the time actually goes, and this document should be edited when
the numbers disagree with it.
