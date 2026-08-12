"""Single-use MFA recovery codes.

A recovery code is a password at the point of use, so the properties that
matter are: unguessable, stored only as a hash, forgiving to type, and dead
after one use.
"""

from __future__ import annotations

from app.core.security import (
    MFA_BACKUP_CODE_COUNT,
    generate_backup_codes,
    hash_backup_code,
)

# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

def test_a_full_set_is_issued() -> None:
    assert len(generate_backup_codes()) == MFA_BACKUP_CODE_COUNT


def test_codes_within_a_set_are_distinct() -> None:
    codes = generate_backup_codes()

    assert len(set(codes)) == len(codes)


def test_two_sets_do_not_overlap() -> None:
    """Regenerating must not hand back a code the user already burned."""
    assert not set(generate_backup_codes()) & set(generate_backup_codes())


def test_codes_avoid_the_characters_people_misread() -> None:
    """0/O and 1/I are indistinguishable on a printout — none may appear."""
    for code in generate_backup_codes():
        body = code.replace("-", "")
        assert not (set(body) & set("01OI")), code


def test_codes_are_grouped_for_transcription() -> None:
    for code in generate_backup_codes():
        left, _, right = code.partition("-")
        assert len(left) == 5 and len(right) == 5


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------

def test_hash_is_stable_for_the_same_code() -> None:
    code = generate_backup_codes(1)[0]

    assert hash_backup_code(code) == hash_backup_code(code)


def test_hash_does_not_contain_the_code() -> None:
    """What lands in the database must be useless to whoever reads it."""
    code = generate_backup_codes(1)[0]
    digest = hash_backup_code(code)

    assert code not in digest
    assert code.replace("-", "") not in digest
    assert len(digest) == 64  # SHA-256 hex


def test_different_codes_hash_differently() -> None:
    a, b = generate_backup_codes(2)

    assert hash_backup_code(a) != hash_backup_code(b)


# ---------------------------------------------------------------------------
# Normalisation — someone is typing this off a piece of paper
# ---------------------------------------------------------------------------

def test_case_is_ignored() -> None:
    code = generate_backup_codes(1)[0]

    assert hash_backup_code(code.lower()) == hash_backup_code(code.upper())


def test_separators_and_spacing_are_ignored() -> None:
    code = generate_backup_codes(1)[0]
    stripped = code.replace("-", "")

    assert hash_backup_code(stripped) == hash_backup_code(code)
    assert hash_backup_code(f"  {code}  ") == hash_backup_code(code)
    assert hash_backup_code(code.replace("-", " ")) == hash_backup_code(code)


def test_a_wrong_code_of_the_right_shape_does_not_collide() -> None:
    real = generate_backup_codes(1)[0]
    tampered = ("A" if real[0] != "A" else "B") + real[1:]

    assert hash_backup_code(tampered) != hash_backup_code(real)
