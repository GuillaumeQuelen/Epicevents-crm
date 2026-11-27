"""Password hashing, JWT authentication and role-based authorization."""

import os
from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from dotenv import load_dotenv

from token_storage import load_token

load_dotenv()

# Role names, as stored in the roles table. Use these constants, never raw strings:
# a typo in a constant fails loudly, a typo in a string silently breaks a permission.
MANAGEMENT = "management"
SALES = "sales"
SUPPORT = "support"
ALL_ROLES = (MANAGEMENT, SALES, SUPPORT)

TOKEN_LIFETIME = timedelta(hours=8)

_hasher = PasswordHasher()


class PermissionDenied(Exception):
    """Raised when the current user is not logged in or not allowed to act."""


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    # argon2 raises an exception on a wrong password instead of returning False.
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def _secret() -> str:
    return os.environ["JWT_SECRET"]


def create_token(employee_id: int, role: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(employee_id),
        "role": role,
        "iat": now,
        "exp": now + TOKEN_LIFETIME,
    }
    return jwt.encode(payload, _secret(), algorithm="HS256")


def decode_token(token: str) -> dict:
    # algorithms is a fixed list: a token signed with "none" or another algorithm is rejected.
    return jwt.decode(token, _secret(), algorithms=["HS256"])


def current_user() -> dict:
    """Return the payload of the stored token, or raise PermissionDenied."""
    token = load_token()
    if token is None:
        raise PermissionDenied("Vous devez vous connecter (login).")
    try:
        return decode_token(token)
    except jwt.ExpiredSignatureError:
        raise PermissionDenied("Votre session a expiré, reconnectez-vous.")
    except jwt.InvalidTokenError:
        raise PermissionDenied("Jeton invalide, reconnectez-vous.")


def require_role(*allowed_roles: str):
    """Allow the decorated function only for the listed roles.

    Deny by default: a role that is not listed, including a role added later, has no access.
    """
    if not allowed_roles:
        raise ValueError("require_role needs at least one role.")

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            user = current_user()
            if user["role"] not in allowed_roles:
                raise PermissionDenied(f"Action réservée à : {', '.join(allowed_roles)}.")
            return func(*args, **kwargs)

        return wrapper

    return decorator