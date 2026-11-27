"""Shared fixtures.

Safety: the environment variables are set BEFORE the application modules are imported,
so the tests always use an in-memory SQLite database, a test JWT secret and no Sentry.
load_dotenv() never overrides a variable that already exists, so .env is ignored here.
"""

import os

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["JWT_SECRET"] = "test-secret-for-pytest-only-0123456789abcdef"
os.environ["SENTRY_DSN"] = ""

from datetime import datetime, timedelta  # noqa: E402
from decimal import Decimal  # noqa: E402

import pytest  # noqa: E402
from sqlalchemy import create_engine, event, select  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

import token_storage  # noqa: E402
import write  # noqa: E402
from auth import MANAGEMENT, SALES, SUPPORT, create_token, hash_password  # noqa: E402
from models import Base, Client, Contract, Employee, Event, Role  # noqa: E402

PASSWORD = "Test1234"
PASSWORD_HASH = hash_password(PASSWORD)  # hashed once: argon2 is slow on purpose

EMPLOYEES = [
    ("E001", "Admin", "admin@test.local", MANAGEMENT),
    ("E002", "Bill Boquet", "bill@test.local", SALES),
    ("E003", "Kate Hastroff", "kate@test.local", SUPPORT),
    ("E004", "Sam Seller", "sam@test.local", SALES),
    ("E005", "Lea Support", "lea@test.local", SUPPORT),
]


@pytest.fixture
def engine():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(eng, "connect")
    def enable_foreign_keys(dbapi_connection, _record):
        # SQLite ignores foreign keys unless asked; PostgreSQL always checks them.
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def session(engine):
    with sessionmaker(bind=engine)() as db:
        roles = {name: Role(name=name) for name in (MANAGEMENT, SALES, SUPPORT)}
        db.add_all(roles.values())
        for number, name, email, role in EMPLOYEES:
            db.add(Employee(employee_number=number, name=name, email=email,
                            password_hash=PASSWORD_HASH, role=roles[role]))
        db.commit()
        yield db


@pytest.fixture(autouse=True)
def token_file(tmp_path, monkeypatch):
    """Every test gets its own token folder: the real ~/.epicevents is never touched."""
    monkeypatch.setattr(token_storage, "TOKEN_DIR", tmp_path / ".epicevents")
    monkeypatch.setattr(token_storage, "TOKEN_FILE", tmp_path / ".epicevents" / "token")


@pytest.fixture
def login_as(session):
    """Log in as an employee by writing a valid token, like the login command does."""

    def _login(email: str) -> Employee:
        employee = session.scalar(select(Employee).where(Employee.email == email))
        token_storage.save_token(create_token(employee.id, employee.role.name))
        return employee

    return _login


@pytest.fixture
def employee(session):
    def _get(email: str) -> Employee:
        return session.scalar(select(Employee).where(Employee.email == email))

    return _get


@pytest.fixture
def actions(monkeypatch):
    """Record the messages write.py sends to Sentry instead of sending them."""
    recorded = []
    monkeypatch.setattr(write, "log_action", lambda message, **details: recorded.append((message, details)))
    return recorded


@pytest.fixture
def bill_client(session, employee):
    client = Client(full_name="Kevin Casey", email="kevin@startup.io", phone="+678 123 456 78",
                    company_name="Cool Startup LLC", sales_contact=employee("bill@test.local"))
    session.add(client)
    session.commit()
    return client


@pytest.fixture
def contract(session, bill_client):
    contract = Contract(client=bill_client, total_amount=Decimal("5000"), amount_due=Decimal("5000"))
    session.add(contract)
    session.commit()
    return contract


@pytest.fixture
def signed_contract(session, contract):
    contract.is_signed = True
    session.commit()
    return contract


@pytest.fixture
def future():
    """A start and end date in the future."""
    start = (datetime.now() + timedelta(days=30)).replace(microsecond=0)
    return start, start + timedelta(hours=10)


@pytest.fixture
def event_(session, signed_contract, future):
    start, end = future
    new_event = Event(contract=signed_contract, name="John Ouick Wedding", start_date=start, end_date=end,
                      location="Candé-sur-Beuvron", attendees=75)
    session.add(new_event)
    session.commit()
    return new_event