"""Password hashing, JWT tokens, token storage and the require_role decorator."""

import base64
import json
import os
import stat
from datetime import datetime, timedelta, timezone

import jwt
import pytest

import auth
import token_storage
from auth import (
    MANAGEMENT,
    SALES,
    PermissionDenied,
    create_token,
    current_user,
    decode_token,
    hash_password,
    require_role,
    verify_password,
)


def test_password_is_never_stored_in_clear():
    hashed = hash_password("secret")
    assert hashed != "secret"
    assert hashed.startswith("$argon2")


def test_same_password_gives_different_hashes():
    # A random salt is added each time.
    assert hash_password("secret") != hash_password("secret")


def test_verify_password():
    hashed = hash_password("secret")
    assert verify_password("secret", hashed) is True
    assert verify_password("wrong", hashed) is False


def test_verify_password_with_a_broken_hash():
    assert verify_password("secret", "not-a-hash") is False


def test_token_round_trip():
    payload = decode_token(create_token(7, SALES))
    assert payload["sub"] == "7"
    assert payload["role"] == SALES


def test_no_token_means_not_logged_in():
    with pytest.raises(PermissionDenied, match="connecter"):
        current_user()


def test_expired_token_is_refused():
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    token_storage.save_token(jwt.encode({"sub": "1", "role": SALES, "exp": past}, auth._secret(), algorithm="HS256"))
    with pytest.raises(PermissionDenied, match="expiré"):
        current_user()


def test_token_signed_with_another_secret_is_refused():
    forged = jwt.encode({"sub": "1", "role": MANAGEMENT}, "attacker-secret-0123456789-abcdefghij", algorithm="HS256")
    token_storage.save_token(forged)
    with pytest.raises(PermissionDenied, match="invalide"):
        current_user()


def test_unsigned_token_is_refused():
    # The classic "alg: none" attack: a token with no signature at all.
    token_storage.save_token(jwt.encode({"sub": "1", "role": MANAGEMENT}, "", algorithm="none"))
    with pytest.raises(PermissionDenied, match="invalide"):
        current_user()


def test_changing_the_role_inside_a_token_breaks_its_signature():
    header, _payload, signature = create_token(2, SALES).split(".")
    forged = base64.urlsafe_b64encode(json.dumps({"sub": "2", "role": MANAGEMENT}).encode()).decode().rstrip("=")
    token_storage.save_token(f"{header}.{forged}.{signature}")
    with pytest.raises(PermissionDenied, match="invalide"):
        current_user()


@require_role(MANAGEMENT)
def management_only():
    return "ok"


def test_require_role_lets_the_listed_role_through():
    token_storage.save_token(create_token(1, MANAGEMENT))
    assert management_only() == "ok"


def test_require_role_refuses_another_role():
    token_storage.save_token(create_token(2, SALES))
    with pytest.raises(PermissionDenied, match="réservée"):
        management_only()


def test_a_new_role_has_no_access_by_default():
    token_storage.save_token(create_token(9, "intern"))
    with pytest.raises(PermissionDenied):
        management_only()


def test_require_role_needs_at_least_one_role():
    with pytest.raises(ValueError):
        require_role()


def test_token_file_is_readable_by_its_owner_only():
    token_storage.save_token("abc")
    assert stat.S_IMODE(os.stat(token_storage.TOKEN_FILE).st_mode) == 0o600
    assert token_storage.load_token() == "abc"


def test_logout_deletes_the_token():
    token_storage.save_token("abc")
    token_storage.delete_token()
    assert token_storage.load_token() is None