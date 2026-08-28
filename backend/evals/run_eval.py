"""Measure the knowledge base against the golden set.

The system was built so that certain failures are impossible by construction:
a citation cannot point at a passage that was not retrieved, and a passage the
caller has no grant on is never selected. Those are guarantees, and the
integration tests already prove them.

What no amount of construction can tell you is whether the thing is *useful* —
whether the passage retrieved is the one a person wanted, and whether the
answer built from it is right. That needs examples with known answers, which
is what this measures.

## This needs a live embedding model, and refuses to run without one

The first version of this file claimed a "deterministic tier" that could score
retrieval in CI with no model. That was wrong, and wrong in the specific way
this whole system exists to avoid.

Retrieval filters on `embedding IS NOT NULL` — an un-embedded passage is not
searchable, which is correct: a half-indexed document must not answer
questions. But it means that with no embedding model *every* query retrieves
nothing. The access-control cases would then "pass" because the restricted
passage was not returned — not because the access filter worked, but because
nothing was returned to anybody. A green gate that proves nothing is worse
than no gate, and it is the same failure as a test suite that reports success
when it never ran.

So: no embeddings, no score. The harness exits rather than printing numbers it
cannot stand behind.

What CI *can* check without a model is the machinery — scoring maths, gate
logic, leak detection — and that lives in `tests/test_kb_eval_harness.py`
with a stub embedder. Those tests assert the harness is correct; they make no
claim about the knowledge base being good.

## Two passes

**Retrieval** (default) — embeds each question, runs the real retrieval path,
scores what comes back. Needs the embedding model only.

**Generation** (`--with-model`) — additionally asks for an answer and scores
correctness, abstention and citation integrity. Needs the chat model too, is
slower, and is non-deterministic.

## What is scored

  recall@k     did any expected passage make the top k
  MRR          how near the top the first correct passage landed
  section hit  did the best passage carry the expected heading path
  abstention   did it refuse when it should, and only then
  citations    every citation resolves to a retrieved passage (hard gate)
  leakage      no passage from an ungranted collection ever appears (hard gate)

## Usage

    python -m evals.run_eval --build            # (re)build the corpus, then score
    python -m evals.run_eval                    # retrieval only
    python -m evals.run_eval --with-model       # adds generation
    python -m evals.run_eval --json out.json    # machine-readable
    python -m evals.run_eval --tag access-control

Exit code is non-zero when a hard gate fails, so CI can depend on it.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings
from app.models.knowledge import KBCollection
from app.models.role import Role
from app.models.user import User
from app.services import llm_client
from app.services.kb_retrieval_service import (
    KBRetrievalService,
    accessible_collections,
)
from evals import fixture

GOLDEN_SET = Path(__file__).parent / "golden_set.yaml"

#: How many retrieved passages count as a hit. Matches KB_CONTEXT_TOP_N — the
#: passages that actually reach the prompt. Scoring a wider window would
#: flatter the system by counting passages the model never saw.
TOP_K = settings.KB_CONTEXT_TOP_N


# ---------------------------------------------------------------------------
# Gates — the conditions under which this exits non-zero
# ---------------------------------------------------------------------------

@dataclass
class Gates:
    """Thresholds that fail the build.

    Two are absolute and must never be relaxed: a fabricated citation and a
    cross-collection leak are correctness failures, not quality ones. The
    retrieval floors are deliberately modest — they exist to catch a broken
    index, not to certify quality, and raising them before an SME review would
    be scoring a ruler against itself.
    """

    max_fabricated_citations: int = 0
    max_access_leaks: int = 0
    min_recall_at_k: float = 0.80
    min_abstention_accuracy: float = 0.90


@dataclass
class CaseResult:
    case_id: str
    question: str
    role: str
    tags: list[str] = field(default_factory=list)
    should_abstain: bool = False

    retrieved: list[dict] = field(default_factory=list)
    expected_doc: str | None = None
    expected_section: str | None = None

    doc_hit: bool = False
    section_hit: bool = False
    rank_of_first_hit: int | None = None
    leaked_collections: list[str] = field(default_factory=list)

    # Generative tier; None when the model was not run.
    answered: bool | None = None
    abstained: bool | None = None
    abstain_reason: str | None = None
    fabricated_citations: list[int] = field(default_factory=list)
    facts_found: list[str] = field(default_factory=list)
    facts_missing: list[str] = field(default_factory=list)
    confidence: float | None = None
    error: str | None = None

    @property
    def reciprocal_rank(self) -> float:
        return 1.0 / self.rank_of_first_hit if self.rank_of_first_hit else 0.0

    @property
    def abstention_correct(self) -> bool | None:
        """Did it refuse exactly when it should have?

        For an access-control case the deterministic tier can answer this on
        its own: retrieving nothing *is* the refusal, and it is the only
        acceptable outcome. For everything else the model has to have run.
        """
        if self.should_abstain and not self.retrieved:
            return True
        if self.abstained is None:
            return None
        return self.abstained == self.should_abstain


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

async def _user_for_role(db: AsyncSession, role_name: str) -> User:
    """A throwaway in-memory user carrying the role under test.

    Never added to the session: the retrieval predicate only reads
    `user.role.name` and `user.is_super_admin`, so persisting an eval user
    would put rows in the operator's database for no benefit.
    """
    role = (
        await db.execute(select(Role).where(Role.name == role_name))
    ).scalar_one_or_none()
    if role is None:
        raise SystemExit(
            f"Role {role_name!r} does not exist in this database. "
            "Run `python scripts/seed_dev.py` first."
        )
    user = User(
        id=uuid.uuid4(),
        email=f"eval-{role_name}@invalid",
        full_name=f"eval:{role_name}",
        password_hash="",
        role_id=role.id,
        is_active=True,
        mfa_enabled=False,
        failed_login_count=0,
        is_super_admin=False,
    )
    user.role = role
    return user


# ---------------------------------------------------------------------------
# Scoring one case
# ---------------------------------------------------------------------------

async def run_case(
    db: AsyncSession, case: dict[str, Any], *, with_model: bool
) -> CaseResult:
    role = case.get("role", "agent")
    expects = case.get("expects") or {}

    result = CaseResult(
        case_id=case["id"],
        question=case["question"],
        role=role,
        tags=list(case.get("tags") or []),
        should_abstain=bool(case.get("should_abstain")),
        expected_doc=expects.get("doc"),
        expected_section=expects.get("section"),
    )

    user = await _user_for_role(db, role)
    service = KBRetrievalService(db)

    try:
        passages = await service.retrieve(user, case["question"])
    except llm_client.EmbeddingError as exc:
        result.error = f"embedding unavailable: {exc}"
        return result

    for rank, p in enumerate(passages[:TOP_K], start=1):
        result.retrieved.append(
            {
                "rank": rank,
                "document": p.document_title,
                "section": p.heading_path,
                "similarity": p.similarity,
                "excerpt": p.content[:160],
            }
        )
        if result.expected_doc and result.expected_doc.lower() in p.document_title.lower():
            if not result.doc_hit:
                result.doc_hit = True
                result.rank_of_first_hit = rank
            if (
                result.expected_section
                and p.heading_path
                and result.expected_section in p.heading_path
            ):
                result.section_hit = True

    # Access leakage, checked against the collections the role may actually read.
    if passages:
        seen_ids = {p.collection_id for p in passages}
        allowed_ids = set((await db.execute(accessible_collections(user))).scalars().all())
        for cid in seen_ids - allowed_ids:
            name = (
                await db.execute(select(KBCollection.name).where(KBCollection.id == cid))
            ).scalar_one_or_none()
            result.leaked_collections.append(name or str(cid))

    if not with_model:
        return result

    answer = await service.answer(user, case["question"])
    result.abstained = answer.abstained
    result.abstain_reason = answer.abstain_reason
    result.answered = not answer.abstained
    result.confidence = answer.confidence
    result.fabricated_citations = list(answer.rejected_citations)

    if answer.answer:
        haystack = answer.answer.lower()
        for fact in expects.get("facts") or []:
            (result.facts_found if fact.lower() in haystack else result.facts_missing).append(fact)

    return result


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def summarise(results: list[CaseResult], gates: Gates) -> dict[str, Any]:
    scored = [r for r in results if not r.error]
    answerable = [r for r in scored if not r.should_abstain]
    refusable = [r for r in scored if r.should_abstain]

    recall = (
        sum(1 for r in answerable if r.doc_hit) / len(answerable) if answerable else 0.0
    )
    mrr = (
        sum(r.reciprocal_rank for r in answerable) / len(answerable) if answerable else 0.0
    )
    section = (
        sum(1 for r in answerable if r.section_hit)
        / sum(1 for r in answerable if r.expected_section)
        if any(r.expected_section for r in answerable)
        else 0.0
    )

    judged = [r for r in scored if r.abstention_correct is not None]
    abstention = (
        sum(1 for r in judged if r.abstention_correct) / len(judged) if judged else None
    )

    fabricated = sum(len(r.fabricated_citations) for r in scored)
    leaks = sum(1 for r in scored if r.leaked_collections)

    failures: list[str] = []
    if fabricated > gates.max_fabricated_citations:
        failures.append(
            f"{fabricated} fabricated citation(s) survived validation "
            f"(limit {gates.max_fabricated_citations})"
        )
    if leaks > gates.max_access_leaks:
        failures.append(
            f"{leaks} case(s) retrieved a passage from an ungranted collection "
            f"(limit {gates.max_access_leaks})"
        )
    if answerable and recall < gates.min_recall_at_k:
        failures.append(
            f"recall@{TOP_K} {recall:.0%} is below the {gates.min_recall_at_k:.0%} floor"
        )
    if abstention is not None and abstention < gates.min_abstention_accuracy:
        failures.append(
            f"abstention accuracy {abstention:.0%} is below the "
            f"{gates.min_abstention_accuracy:.0%} floor"
        )

    return {
        "cases": len(results),
        "scored": len(scored),
        "errored": len(results) - len(scored),
        "answerable": len(answerable),
        "should_abstain": len(refusable),
        "recall_at_k": round(recall, 4),
        "mrr": round(mrr, 4),
        "section_accuracy": round(section, 4),
        "abstention_accuracy": round(abstention, 4) if abstention is not None else None,
        "fabricated_citations": fabricated,
        "access_leaks": leaks,
        "gate_failures": failures,
        "passed": not failures,
    }


def render(results: list[CaseResult], summary: dict[str, Any], *, with_model: bool) -> str:
    lines: list[str] = []
    w = 74
    lines.append("=" * w)
    lines.append("KNOWLEDGE BASE — GOLDEN SET")
    lines.append("=" * w)
    lines.append(
        f"{summary['cases']} cases · {summary['answerable']} answerable · "
        f"{summary['should_abstain']} should abstain"
        + (f" · {summary['errored']} errored" if summary["errored"] else "")
    )
    lines.append(f"tier: {'deterministic + generative' if with_model else 'deterministic only'}")
    lines.append("")

    lines.append("RETRIEVAL")
    lines.append(f"  recall@{TOP_K:<12} {summary['recall_at_k']:.0%}")
    lines.append(f"  MRR{'':<15} {summary['mrr']:.3f}")
    lines.append(f"  section accuracy{'':<3} {summary['section_accuracy']:.0%}")
    lines.append("")

    lines.append("INTEGRITY (hard gates)")
    lines.append(f"  fabricated citations {summary['fabricated_citations']}")
    lines.append(f"  access leaks         {summary['access_leaks']}")
    if summary["abstention_accuracy"] is not None:
        lines.append(f"  abstention accuracy  {summary['abstention_accuracy']:.0%}")
    else:
        lines.append("  abstention accuracy  n/a — needs --with-model")
    lines.append("")

    misses = [r for r in results if not r.should_abstain and not r.doc_hit and not r.error]
    if misses:
        lines.append(f"RETRIEVAL MISSES ({len(misses)})")
        for r in misses:
            top = r.retrieved[0]["document"] if r.retrieved else "nothing retrieved"
            lines.append(f"  {r.case_id}")
            lines.append(f"    wanted: {r.expected_doc}")
            lines.append(f"    got:    {top}")
        lines.append("")

    wrong_abstention = [
        r for r in results if r.abstention_correct is False
    ]
    if wrong_abstention:
        lines.append(f"ABSTENTION ERRORS ({len(wrong_abstention)})")
        for r in wrong_abstention:
            what = "answered but should have refused" if r.should_abstain else "refused but should have answered"
            lines.append(f"  {r.case_id}: {what}")
            if r.abstain_reason:
                lines.append(f"    reason given: {r.abstain_reason}")
        lines.append("")

    leaked = [r for r in results if r.leaked_collections]
    if leaked:
        lines.append(f"ACCESS LEAKS ({len(leaked)}) — investigate before anything else")
        for r in leaked:
            lines.append(f"  {r.case_id} as {r.role}: {', '.join(r.leaked_collections)}")
        lines.append("")

    if with_model:
        factual = [r for r in results if r.facts_missing]
        if factual:
            lines.append(f"ANSWERS MISSING EXPECTED FACTS ({len(factual)})")
            for r in factual:
                lines.append(f"  {r.case_id}: missing {', '.join(r.facts_missing)}")
            lines.append("")

    errored = [r for r in results if r.error]
    if errored:
        lines.append(f"ERRORED ({len(errored)})")
        for r in errored:
            lines.append(f"  {r.case_id}: {r.error}")
        lines.append("")

    lines.append("=" * w)
    if summary["passed"]:
        lines.append("PASS — all gates met")
    else:
        lines.append("FAIL")
        for f in summary["gate_failures"]:
            lines.append(f"  · {f}")
    lines.append("=" * w)

    if not with_model:
        lines.append("")
        lines.append(
            "Note: answer correctness was not measured. Re-run with --with-model\n"
            "against a live Ollama to score generation."
        )
    lines.append(
        "\nThe golden set has not been reviewed by subject-matter experts.\n"
        "Retrieval scores say the index works; they do not say the answers are\n"
        "good. See the header of evals/golden_set.yaml."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def load_cases(path: Path, tag: str | None) -> list[dict[str, Any]]:
    data = yaml.safe_load(path.read_text())
    cases = data.get("cases") or []
    if tag:
        cases = [c for c in cases if tag in (c.get("tags") or [])]
    return cases


async def _embeddings_available() -> bool:
    """One probe, so the run fails in two seconds rather than case by case."""
    try:
        vectors = await llm_client.embed(["probe"])
    except llm_client.EmbeddingError:
        return False
    return bool(vectors)


async def main_async(args: argparse.Namespace) -> int:
    cases = load_cases(Path(args.golden_set), args.tag)
    if not cases:
        print("No cases matched.", file=sys.stderr)
        return 2

    if not await _embeddings_available():
        print(
            "Cannot score: no embedding model is reachable.\n"
            "\n"
            "This is a refusal, not a failure. Retrieval requires an embedding\n"
            "per passage, so without the model every query returns nothing —\n"
            "and every access-control case would 'pass' because nothing was\n"
            "retrieved for anybody. Those numbers would be meaningless.\n"
            "\n"
            f"Start Ollama and run: ollama pull {settings.KB_EMBEDDING_MODEL}",
            file=sys.stderr,
        )
        return 2

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    results: list[CaseResult] = []
    async with session_factory() as db:
        if args.build or not await fixture.is_built(db):
            report = await fixture.build(db, embed=llm_client.embed)
            print(
                f"Corpus: {report.documents} documents, {report.chunks} passages, "
                f"{report.collections} collections.\n"
            )
        for case in cases:
            results.append(await run_case(db, case, with_model=args.with_model))
    await engine.dispose()

    gates = Gates()
    if args.no_gates:
        gates = Gates(
            max_fabricated_citations=10**6,
            max_access_leaks=10**6,
            min_recall_at_k=0.0,
            min_abstention_accuracy=0.0,
        )

    summary = summarise(results, gates)
    print(render(results, summary, with_model=args.with_model))

    if args.json:
        Path(args.json).write_text(
            json.dumps(
                {
                    "summary": summary,
                    "cases": [vars(r) for r in results],
                },
                indent=2,
                default=str,
            )
        )
        print(f"\nWrote {args.json}")

    return 0 if summary["passed"] else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Score the knowledge base.")
    parser.add_argument("--golden-set", default=str(GOLDEN_SET))
    parser.add_argument(
        "--build",
        action="store_true",
        help="Rebuild the pinned corpus before scoring. Required after editing evals/corpus/.",
    )
    parser.add_argument(
        "--with-model",
        action="store_true",
        help="Also generate answers. Needs a live model; slow and non-deterministic.",
    )
    parser.add_argument("--tag", help="Only run cases carrying this tag.")
    parser.add_argument("--json", help="Write the full report to this path.")
    parser.add_argument(
        "--no-gates",
        action="store_true",
        help="Report without failing. For local exploration, never for CI.",
    )
    return asyncio.run(main_async(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
