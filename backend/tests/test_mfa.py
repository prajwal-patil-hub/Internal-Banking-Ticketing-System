"""TOTP multi-factor authentication tests."""

from __future__ import annotations

import time

import pyotp
import pytest

from app.core.security import (
    create_access_token,
    create_mfa_challenge_token,
    decode_token,
    generate_mfa_secret,
    mfa_provisioning_uri,
    verify_totp,
)

# ---------------------------------------------------------------------------
# Secrets and codes
# ---------------------------------------------------------------------------

def test_secret_is_valid_base32_and_unique() -> None:
    a, b = generate_mfa_secret(), generate_mfa_secret()

    assert a != b
    pyotp.TOTP(a).now()  # would raise on a malformed secret


def test_current_code_verifies() -> None:
    secret = generate_mfa_secret()

    assert verify_totp(secret, pyotp.TOTP(secret).now())


def test_wrong_code_is_rejected() -> None:
    secret = generate_mfa_secret()
    wrong = "000000" if pyotp.TOTP(secret).now() != "000000" else "111111"

    assert not verify_totp(secret, wrong)


def test_code_from_another_secret_is_rejected() -> None:
    mine, theirs = generate_mfa_secret(), generate_mfa_secret()

    assert not verify_totp(mine, pyotp.TOTP(theirs).now())


def test_blank_inputs_are_rejected_not_accepted() -> None:
    """An empty secret must never behave like a wildcard."""
    secret = generate_mfa_secret()

    assert not verify_totp(secret, "")
    assert not verify_totp("", pyotp.TOTP(secret).now())
    assert not verify_totp("", "")


def test_codes_are_accepted_with_spaces() -> None:
    """Authenticator apps display '123 456'; pasting that must work."""
    secret = generate_mfa_secret()
    code = pyotp.TOTP(secret).now()

    assert verify_totp(secret, f"{code[:3]} {code[3:]}")


def test_adjacent_time_step_is_accepted_for_clock_drift() -> None:
    secret = generate_mfa_secret()
    previous = pyotp.TOTP(secret).at(time.time() - 30)

    assert verify_totp(secret, previous)


def test_distant_time_step_is_rejected() -> None:
    secret = generate_mfa_secret()
    stale = pyotp.TOTP(secret).at(time.time() - 300)

    assert not verify_totp(secret, stale)


# ---------------------------------------------------------------------------
# Provisioning URI
# ---------------------------------------------------------------------------

def test_provisioning_uri_carries_issuer_and_account() -> None:
    secret = generate_mfa_secret()

    uri = mfa_provisioning_uri(secret, "priya.sharma@successbank.local")

    assert uri.startswith("otpauth://totp/")
    assert secret in uri
    assert "SUCCESS%20Bank" in uri
    assert "priya.sharma%40successbank.local" in uri


# ---------------------------------------------------------------------------
# Challenge token
# ---------------------------------------------------------------------------

def test_challenge_token_is_typed_mfa_not_access() -> None:
    """The critical property: a half-finished login must not open the API.

    get_current_user only accepts type 'access', so typing the challenge
    differently is what stops it being replayed as a bearer token.
    """
    token, _exp = create_mfa_challenge_token(subject="user-123")

    claims = decode_token(token)
    assert claims["type"] == "mfa"
    assert claims["type"] != "access"
    assert claims["sub"] == "user-123"


def test_challenge_token_expires_sooner_than_an_access_token() -> None:
    challenge, challenge_exp = create_mfa_challenge_token(subject="u")
    _access, access_exp = create_access_token(subject="u", role="admin")

    assert challenge_exp <= access_exp
    assert decode_token(challenge)["exp"] > 0


def test_challenge_tokens_are_not_interchangeable() -> None:
    a, _ = create_mfa_challenge_token(subject="user-a")
    b, _ = create_mfa_challenge_token(subject="user-b")

    assert a != b
    assert decode_token(a)["sub"] != decode_token(b)["sub"]
    assert decode_token(a)["jti"] != decode_token(b)["jti"]


@pytest.mark.parametrize("subject", ["", "user-1", "a" * 64])
def test_challenge_token_round_trips_any_subject(subject: str) -> None:
    token, _ = create_mfa_challenge_token(subject=subject)

    assert decode_token(token)["sub"] == subject
