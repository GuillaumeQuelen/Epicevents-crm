"""Local storage of the JWT between two commands.

The token lives in the home folder of the current OS user, readable by that user only.
One OS account = one CRM session at a time: logging in again replaces the token.
"""

import os
from pathlib import Path

TOKEN_DIR = Path.home() / ".epicevents"
TOKEN_FILE = TOKEN_DIR / "token"


def save_token(token: str) -> None:
    TOKEN_DIR.mkdir(mode=0o700, exist_ok=True)
    # The file is created with owner-only permissions from the start (chmod 600).
    fd = os.open(TOKEN_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as file:
        file.write(token)
    os.chmod(TOKEN_FILE, 0o600)


def load_token() -> str | None:
    if not TOKEN_FILE.exists():
        return None
    return TOKEN_FILE.read_text().strip() or None


def delete_token() -> None:
    TOKEN_FILE.unlink(missing_ok=True)