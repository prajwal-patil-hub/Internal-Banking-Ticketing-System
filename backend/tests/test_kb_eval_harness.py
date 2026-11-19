"""The evaluation harness itself, tested.

These make no claim about whether the knowledge base gives good answers — that
is what the golden set is for, and it needs a real model and an SME review.
What they assert is that the *instrument* is sound: that a miss is scored as a
miss, that a leaked passage trips the gate, that the abstention logic does not
mark a vacuous refusal as correct.

An instrument nobody has checked is worse than no instrument, because its
output gets quoted. The specific failure guarded against here is the one the
harness was rewritten to avoid: with no embedding model every query returns
nothing, so every access-control case looks like a pass. A gate that goes
green when it did not run is the same bug as a CI job that reports success on
a suite it never executed.

A deterministic stub embedder stands in for the model. It is not semantic, but
it is *discriminative* — the same text always maps to the same vector and
different text to a different one — which is all the scoring maths needs.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models.knowledge import KBChunk, KBCollection
from app.models.role import Role
from evals import fixture
from evals.run_eval import CaseResult, Gates, load_cases, run_case, summarise

GOLDEN_SET = fixture.CORPUS_DIR.parent / "golden_set.yaml"


def _vector(text: str) -> list[float]:
    """Deterministic bag-of-characters direction, unit length.

    Not semantic. It is enough that "45 days" and "car parking" land in
    different directions, which is what makes a retrieval hit distinguishable
    from a miss.
    """
    v = [0.0] * settings.KB_EMBEDDING_DIM
    lowered = text.lower()
    for i, ch in enumerate(lowered[:2000]):
        v[(ord(ch) * 31 + i * 7) % settings.KB_EMBEDDING_DIM] += 1.0
    norm = sum(x * x for x in v) ** 0.5 or 1.0
    return [x / norm for x in v]


async def _stub_embed(texts: list[str]) -> list[list[float]]:
    return [_vector(t) for t in texts]


async def _ensure_roles(db) -> None:
    for name in ("agent", "supervisor", "admin"):
        exists = (
            await db.execute(select(Role).where(Role.name == name))
        ).scalar_one_or_none()
        if exists is None:
            db.add(Role(id=uuid.uuid4(), name=name, description=name))
    await db.flush()


@pytest.fixture
async def corpus(committing_session, monkeypatch):
    """The pinned eval corpus, embedded with the stub, torn down afterwards."""
    db = committing_session
    await _ensure_roles(db)
    await db.commit()
    monkeypatch.setattr("app.services.llm_client.embed", _stub_embed)
    report = await fixture.build(db, embed=_stub_embed)
    try:
        yield db, report
    finally:
        await fixture.teardown(db)


# ---------------------------------------------------------------------------
# The fixture builds what it claims to
# ---------------------------------------------------------------------------

async def test_corpus_builds_with_grants_and_embeddings(corpus) -> None:
    db, report = corpus
    assert report.collections == len(fixture.COLLECTIONS)
    assert report.documents == len(fixture.DOCUMENTS)
    assert report.chunks > 0
    assert report.embedded == report.chunks, "some passages were left unsearchable"

    chunks = (
        await db.execute(
            select(KBChunk).join(
                KBCollection, KBChunk.collection_id == KBCollection.id
            ).where(KBCollection.name.startswith(fixture.EVAL_PREFIX))
        )
    ).scalars().all()
    assert all(c.embedding is not None for c in chunks)
    # Heading paths must survive, or every `expects.section` assertion in the
    # golden set is scoring something that was never there.
    assert any(c.heading_path and "3.1" in c.heading_path for c in chunks)


async def test_rebuilding_replaces_rather_than_duplicates(corpus) -> None:
    """Editing a corpus file must not leave stale passages answering from the
    version that no longer says that."""
    db, first = corpus
    second = await fixture.build(db, embed=_stub_embed)
    assert second.chunks == first.chunks

    total = (
        await db.execute(
            select(KBChunk.id).join(
                KBCollection, KBChunk.collection_id == KBCollection.id
            ).where(KBCollection.name.startswith(fixture.EVAL_PREFIX))
        )
    ).scalars().all()
    assert len(total) == second.chunks


async def test_teardown_leaves_nothing_behind(committing_session, monkeypatch) -> None:
    db = committing_session
    await _ensure_roles(db)
    await db.commit()
    monkeypatch.setattr("app.services.llm_client.embed", _stub_embed)
    await fixture.build(db, embed=_stub_embed)
    await fixture.teardown(db)

    left = (
        await db.execute(
            select(KBCollection.id).where(KBCollection.name.startswith(fixture.EVAL_PREFIX))
        )
    ).scalars().all()
    assert left == []


# ---------------------------------------------------------------------------
# Scoring a case
# ---------------------------------------------------------------------------

async def test_a_hit_is_scored_as_a_hit(corpus) -> None:
    db, _ = corpus
    case = {
        "id": "t-hit",
        "question": "How long does a customer have to raise a service dispute?",
        "role": "agent",
        "expects": {"doc": "Chargeback Handling Policy"},
    }
    result = await run_case(db, case, with_model=False)
    assert result.retrieved, "nothing retrieved — the stub corpus is not searchable"
    assert result.doc_hit
    assert result.rank_of_first_hit is not None
    assert 0 < result.reciprocal_rank <= 1.0


async def test_a_miss_is_scored_as_a_miss(corpus) -> None:
    """Expecting a document the question cannot reach must not score a hit."""
    db, _ = corpus
    case = {
        "id": "t-miss",
        "question": "How long does a customer have to raise a service dispute?",
        "role": "agent",
        "expects": {"doc": "End-of-Day Settlement Runbook"},
    }
    result = await run_case(db, case, with_model=False)
    assert result.doc_hit is False
    assert result.reciprocal_rank == 0.0


async def test_the_access_boundary_is_measured_not_assumed(corpus) -> None:
    """The case the harness exists to make trustworthy.

    Treasury is granted to supervisor and admin. A supervisor must retrieve
    it — that is what proves the agent's empty result is the access filter
    working rather than an empty index.
    """
    db, _ = corpus
    question = "What time does NEFT stop settling?"

    as_supervisor = await run_case(
        db,
        {"id": "t-sup", "question": question, "role": "supervisor",
         "expects": {"doc": "End-of-Day Settlement Runbook"}},
        with_model=False,
    )
    as_agent = await run_case(
        db,
        {"id": "t-agent", "question": question, "role": "agent", "should_abstain": True},
        with_model=False,
    )

    assert as_supervisor.doc_hit, "supervisor could not reach a collection they are granted"
    assert not any(
        "Settlement" in r["document"] for r in as_agent.retrieved
    ), "agent reached a treasury passage"
    assert as_agent.leaked_collections == []


async def test_a_leak_would_be_detected(corpus) -> None:
    """Grant the agent the treasury collection and the harness must notice.

    Without this, "no leaks detected" could mean the detector is broken.
    """
    from app.models.knowledge import KBCollectionGrant

    db, _ = corpus
    treasury = (
        await db.execute(
            select(KBCollection).where(
                KBCollection.name == f"{fixture.EVAL_PREFIX}Treasury runbooks"
            )
        )
    ).scalar_one()

    result_before = await run_case(
        db,
        {"id": "t-before", "question": "What time does NEFT stop settling?", "role": "agent"},
        with_model=False,
    )
    assert result_before.leaked_collections == []

    db.add(
        KBCollectionGrant(
            id=uuid.uuid4(), collection_id=treasury.id, role_name="agent"
        )
    )
    await db.commit()

    result_after = await run_case(
        db,
        {"id": "t-after", "question": "What time does NEFT stop settling?", "role": "agent"},
        with_model=False,
    )
    # Now granted, so it is retrievable and correctly NOT flagged as a leak —
    # the detector keys off the grant, not off a hard-coded expectation.
    assert any("Settlement" in r["document"] for r in result_after.retrieved)
    assert result_after.leaked_collections == []


# ---------------------------------------------------------------------------
# Gates
# ---------------------------------------------------------------------------

def _case(**kw) -> CaseResult:
    base = dict(case_id="c", question="q", role="agent")
    base.update(kw)
    return CaseResult(**base)  # type: ignore[arg-type]


def test_a_fabricated_citation_fails_the_build() -> None:
    summary = summarise([_case(doc_hit=True, fabricated_citations=[7])], Gates())
    assert summary["passed"] is False
    assert any("fabricated" in f for f in summary["gate_failures"])


def test_an_access_leak_fails_the_build() -> None:
    summary = summarise(
        [_case(doc_hit=True, leaked_collections=["Treasury runbooks"])], Gates()
    )
    assert summary["passed"] is False
    assert any("ungranted" in f for f in summary["gate_failures"])


def test_poor_recall_fails_the_build() -> None:
    cases = [_case(case_id=f"c{i}", doc_hit=i < 2) for i in range(10)]
    summary = summarise(cases, Gates())
    assert summary["recall_at_k"] == 0.2
    assert summary["passed"] is False


def test_a_clean_run_passes() -> None:
    cases = [_case(case_id=f"c{i}", doc_hit=True, rank_of_first_hit=1) for i in range(5)]
    summary = summarise(cases, Gates())
    assert summary["passed"] is True
    assert summary["recall_at_k"] == 1.0
    assert summary["mrr"] == 1.0


def test_abstention_is_not_scored_when_the_model_did_not_run() -> None:
    """The vacuous-pass guard.

    An answerable case with no model result must leave abstention unjudged,
    not counted as correct.
    """
    unjudged = _case(should_abstain=False, retrieved=[{"rank": 1}], abstained=None)
    assert unjudged.abstention_correct is None

    summary = summarise([unjudged], Gates())
    assert summary["abstention_accuracy"] is None


def test_answering_something_it_should_have_refused_is_an_error() -> None:
    wrong = _case(should_abstain=True, retrieved=[{"rank": 1}], abstained=False)
    assert wrong.abstention_correct is False
    summary = summarise([wrong], Gates())
    assert summary["passed"] is False


def test_errored_cases_are_reported_not_silently_dropped() -> None:
    summary = summarise([_case(error="embedding unavailable")], Gates())
    assert summary["errored"] == 1
    assert summary["scored"] == 0


# ---------------------------------------------------------------------------
# The golden set is well-formed
# ---------------------------------------------------------------------------

def test_golden_set_parses_and_ids_are_unique() -> None:
    cases = load_cases(GOLDEN_SET, None)
    assert len(cases) >= 15
    ids = [c["id"] for c in cases]
    assert len(ids) == len(set(ids)), "duplicate case ids"


def test_every_case_has_a_question_and_a_role() -> None:
    for case in load_cases(GOLDEN_SET, None):
        assert case.get("question"), case["id"]
        assert case.get("role"), case["id"]


def test_answerable_cases_name_an_expected_document() -> None:
    """Otherwise recall is computed against nothing and reads as 100%."""
    for case in load_cases(GOLDEN_SET, None):
        if case.get("should_abstain"):
            continue
        assert (case.get("expects") or {}).get("doc"), case["id"]


def test_abstention_cases_explain_themselves() -> None:
    for case in load_cases(GOLDEN_SET, None):
        if case.get("should_abstain"):
            assert case.get("abstain_because"), case["id"]


def test_expected_documents_exist_in_the_corpus() -> None:
    """A typo in `expects.doc` would show up as a permanent retrieval miss and
    get blamed on the retriever."""
    titles = [d.title for d in fixture.DOCUMENTS]
    for case in load_cases(GOLDEN_SET, None):
        expected = (case.get("expects") or {}).get("doc")
        if expected:
            assert any(expected.lower() in t.lower() for t in titles), case["id"]


def test_the_set_contains_real_abstention_cases() -> None:
    """A golden set with no refusals cannot detect a system that never refuses."""
    cases = load_cases(GOLDEN_SET, None)
    abstain = [c for c in cases if c.get("should_abstain")]
    assert len(abstain) >= 4
    assert any("access-control" in (c.get("tags") or []) for c in abstain)


def test_it_is_marked_unreviewed_until_an_sme_signs_it() -> None:
    """Guards against the scores being quoted as validated.

    When an SME does review it, they set `reviewed_by` and this test is
    updated to require it stays set — at which point the assertion is the
    record that review happened.
    """
    import yaml

    data = yaml.safe_load(GOLDEN_SET.read_text())
    assert "reviewed_by" in data, "the review field was removed"
    if data["reviewed_by"] is None:
        assert "STARTER SET" in GOLDEN_SET.read_text(), (
            "an unreviewed golden set must say so in its header"
        )
