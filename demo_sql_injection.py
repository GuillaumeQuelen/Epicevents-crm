"""Demonstration for the defence: why a SQL query must never be built with an f-string.

The vulnerable query below exists only in this script, never in the application code.
"""

from sqlalchemy import text

from database import SessionLocal

MALICIOUS_INPUT = "x' OR '1'='1"

with SessionLocal() as session:
    vulnerable = session.execute(
        text(f"SELECT email FROM employees WHERE email = '{MALICIOUS_INPUT}'")
    ).all()
    print("Requête construite avec une f-string :", [row.email for row in vulnerable])

    safe = session.execute(
        text("SELECT email FROM employees WHERE email = :email"),
        {"email": MALICIOUS_INPUT},
    ).all()
    print("Requête paramétrée :", [row.email for row in safe])