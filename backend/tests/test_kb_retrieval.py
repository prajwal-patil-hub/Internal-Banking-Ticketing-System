"""Retrieval: the access boundary, citation validation, and confidence.

The tests that matter most here are the adversarial ones. A knowledge base
that returns good answers but leaks a restricted collection, or that presents
a fabricated citation as a real one, has failed at the only job that makes it
usable in a bank.

There is no live Postgres in this environment, so the SQL-shaped assertions
inspect the *compiled statement* rather than executing it. That is a real
check — it proves the security predicate is present in the SQL that would be
sent — but it is not a substitute for an integration test against a database
with real grants, and it is not claimed to be.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from app.services.kb_retrieval_service import (
    KB_CONFIDENCE_HIGH,
    Passage,
    accessible_collections,
    derive_confidence,
    expand_query,
    reciprocal_rank_fusion,
    validate_citations,
)


def _user(role_name: str = "agent", *, super_admin: bool = False):
    from app.models.role import Role
    from app.models.user import User

    role = Role(id=uuid.uuid4(), name=role_name, description="")
    role.created_at = role.updated_at = datetime.now(UTC)

    user = User(
        id=uuid.uuid4(),
        email=f"{role_name}@bank.com",
        full_name=role_name.title(),
        password_hash="x",
        role_id=role.id,
        is_active=True,
        mfa_enabled=False,
        failed_login_count=0,
        is_super_admin=super_admin,
    )
    user.role = role
    user.created_at = user.updated_at = datetime.now(UTC)
    return user


def _passage(title: str = "Doc", *, document_id=None, similarity=None) -> Passage:
    return Passage(
        chunk_id=uuid.uuid4(),
        document_id=document_id or uuid.uuid4(),
        document_title=title,
        collection_id=uuid.uuid4(),
        heading_path="3.2 Timelines",
        content="A chargeback must be raised within 45 days.",
        page_from=3,
        page_to=3,
        similarity=similarity,
    )


def _sql(stmt) -> str:
    return str(stmt.compile(compile_kwargs={"literal_binds": False}))


# ---------------------------------------------------------------------------
# Access control
# ---------------------------------------------------------------------------

def test_ordinary_role_is_filtered_by_grants() -> None:
    sql = _sql(accessible_collections(_user("agent")))
    assert "kb_collection_grants" in sql
    assert "role_name" in sql


def test_super_admin_skips_the_grant_join_but_not_the_active_filter() -> None:
    sql = _sql(accessible_collections(_user("admin", super_admin=True)))
    assert "kb_collection_grants" not in sql
    assert "is_active" in sql


def test_read_only_super_admin_does_not_get_a_widened_read() -> None:
    """A super-admin flag widens visibility, but an auditor is still an auditor.

    This mirrors `authz.can_write_tickets`, which checks is_read_only first.
    Getting this backwards would hand the read-only oversight role a view of
    every collection in the bank.
    """
    sql = _sql(accessible_collections(_user("auditor", super_admin=True)))
    assert "kb_collection_grants" in sql, "read-only super admin bypassed the grant join"


def test_every_role_still_gets_the_active_collection_filter() -> None:
    for role in ("agent", "supervisor", "admin", "auditor", "branch_user"):
        assert "is_active" in _sql(accessible_collections(_user(role)))


def test_retrievable_predicate_is_shared_by_both_arms() -> None:
    """The dense and lexical queries must not drift apart.

    `_retrievable` exists so there is one copy of the security predicate; this
    asserts it actually carries all three conditions.
    """
    from app.services.kb_retrieval_service import _retrievable

    clauses = _retrievable(_user("agent"))
    rendered = " ".join(str(c) for c in clauses)
    assert "collection_id" in rendered
    assert "active_version_id" in rendered
    assert "embedding" in rendered


# ---------------------------------------------------------------------------
# Citation validation — the hallucination gate
# ---------------------------------------------------------------------------

def test_a_sentence_whose_only_citation_is_invented_is_removed() -> None:
    """Stripping the marker alone would leave the claim as unattributed prose,
    which is the exact failure the whole design exists to prevent."""
    passages = [_passage("A"), _passage("B")]
    answer, cited, rejected = validate_citations(
        "Raise within 45 days [1]. Fraud gets 120 days [7]. Evidence is needed [2].",
        passages,
    )
    assert "120 days" not in answer
    assert "45 days" in answer and "Evidence" in answer
    assert rejected == [7]
    assert len(cited) == 2


def test_all_citations_invented_leaves_nothing() -> None:
    passages = [_passage("A")]
    answer, cited, rejected = validate_citations("Definitely 90 days [9].", passages)
    assert answer == ""
    assert cited == []
    assert rejected == [9]


def test_a_valid_citation_survives_alongside_an_invalid_one() -> None:
    passages = [_passage("A")]
    answer, cited, rejected = validate_citations("It is 45 days [1][8].", passages)
    assert answer == "It is 45 days [1]."
    assert len(cited) == 1
    assert rejected == [8]


def test_uncited_connective_sentences_are_kept() -> None:
    passages = [_passage("A")]
    answer, cited, _ = validate_citations("Here is the position. It is 45 days [1].", passages)
    assert "Here is the position." in answer
    assert len(cited) == 1


def test_citations_are_deduplicated() -> None:
    passages = [_passage("A")]
    _answer, cited, _ = validate_citations("One [1]. Two [1]. Three [1].", passages)
    assert len(cited) == 1


def test_citation_zero_is_rejected() -> None:
    """[0] is out of range; a naive `n <= len(passages)` check would accept it
    and then index passages[-1], silently citing the wrong document."""
    passages = [_passage("A"), _passage("B")]
    _answer, cited, rejected = validate_citations("Claim [0].", passages)
    assert cited == []
    assert rejected == [0]


def test_no_passages_means_every_citation_is_invalid() -> None:
    answer, cited, rejected = validate_citations("Answer [1].", [])
    assert answer == ""
    assert cited == []
    assert rejected == [1]


# ---------------------------------------------------------------------------
# Confidence
# ---------------------------------------------------------------------------

def test_confidence_is_zero_without_citations() -> None:
    assert derive_confidence([_passage(similarity=0.99)], []) == (0.0, "low")


def test_multi_document_support_scores_above_single_document() -> None:
    doc = uuid.uuid4()
    one = [_passage("A", document_id=doc, similarity=0.9), _passage("A", document_id=doc, similarity=0.9)]
    two = [_passage("A", similarity=0.9), _passage("B", similarity=0.9)]

    c_one, _ = derive_confidence(one, [p.chunk_id for p in one])
    c_two, _ = derive_confidence(two, [p.chunk_id for p in two])
    assert c_two > c_one


def test_lexical_only_retrieval_is_not_presented_as_confidently() -> None:
    """When the dense arm is unavailable every similarity is None; the answer
    should land lower than the same answer with strong vector support."""
    lexical = [_passage("A", similarity=None), _passage("B", similarity=None)]
    dense = [_passage("A", similarity=0.95), _passage("B", similarity=0.95)]

    c_lex, _ = derive_confidence(lexical, [p.chunk_id for p in lexical])
    c_dense, _ = derive_confidence(dense, [p.chunk_id for p in dense])
    assert c_lex < c_dense


def test_bands_follow_the_thresholds_the_api_publishes() -> None:
    strong = [_passage("A", similarity=0.99), _passage("B", similarity=0.98)]
    score, band = derive_confidence(strong, [p.chunk_id for p in strong])
    assert band == "high" and score >= KB_CONFIDENCE_HIGH

    weak = [_passage("A", similarity=0.05)]
    score_w, band_w = derive_confidence(weak, [weak[0].chunk_id])
    assert band_w in {"low", "medium"} and score_w < KB_CONFIDENCE_HIGH


def test_confidence_never_leaves_zero_to_one() -> None:
    for sim in (0.0, 0.5, 1.0):
        ps = [_passage("A", similarity=sim), _passage("B", similarity=sim)]
        score, _ = derive_confidence(ps, [p.chunk_id for p in ps])
        assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# Fusion and query prep
# ---------------------------------------------------------------------------

def test_rrf_rewards_appearing_in_both_arms() -> None:
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    scores = reciprocal_rank_fusion([[a, b], [b, c]])
    assert scores[b] > scores[a] and scores[b] > scores[c]


def test_rrf_handles_an_empty_arm() -> None:
    """The dense arm returns nothing when embeddings are unavailable."""
    a = uuid.uuid4()
    scores = reciprocal_rank_fusion([[], [a]])
    assert scores[a] > 0


def test_acronyms_are_expanded_without_losing_the_original() -> None:
    out = expand_query("What is the NEFT cut-off?")
    assert "NEFT" in out
    assert "national electronic funds transfer" in out


def test_expansion_requires_a_whole_word() -> None:
    """Substring matching would expand 'unaml' or 'skyc'."""
    assert expand_query("Check the unamlicensed record") == "Check the unamlicensed record"


@pytest.mark.parametrize("question", ["", "   "])
def test_expansion_of_empty_input_is_safe(question: str) -> None:
    assert expand_query(question) == question
