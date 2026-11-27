"""Read operations. Every function is protected by require_role, except the login lookup."""

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from auth import ALL_ROLES, MANAGEMENT, SALES, SUPPORT, current_user, require_role
from models import Client, Contract, Employee, Event


def find_employee_by_email(session: Session, email: str):
    """Login lookup, written in raw SQL on purpose (the rest of the code uses the ORM).

    Not protected by require_role: it runs before the user is authenticated.
    The email is a bound parameter (:email), never inserted in the string,
    so a value such as  x' OR '1'='1  cannot change the query (no SQL injection).
    INNER JOIN: only employees that have a role are returned.
    """
    query = text(
        "SELECT e.id, e.password_hash, r.name AS role "
        "FROM employees e "
        "INNER JOIN roles r ON r.id = e.role_id "
        "WHERE e.email = :email"
    )
    return session.execute(query, {"email": email}).first()


@require_role(MANAGEMENT)
def get_employees(session: Session) -> list[Employee]:
    return list(session.scalars(select(Employee).order_by(Employee.id)))


@require_role(*ALL_ROLES)
def get_clients(session: Session) -> list[Client]:
    return list(session.scalars(select(Client).order_by(Client.id)))


@require_role(*ALL_ROLES)
def get_contracts(session: Session) -> list[Contract]:
    return list(session.scalars(select(Contract).order_by(Contract.id)))


@require_role(*ALL_ROLES)
def get_events(session: Session) -> list[Event]:
    return list(session.scalars(select(Event).order_by(Event.start_date)))


@require_role(MANAGEMENT)
def get_events_without_support(session: Session) -> list[Event]:
    """LEFT OUTER JOIN: keeps every event, with no employee when none is assigned.

    SQL equivalent:
        SELECT events.* FROM events
        LEFT OUTER JOIN employees ON employees.id = events.support_contact_id
        WHERE employees.id IS NULL
    """
    query = select(Event).outerjoin(Event.support_contact).where(Employee.id.is_(None))
    return list(session.scalars(query))


@require_role(SALES)
def get_unsigned_contracts(session: Session) -> list[Contract]:
    return list(session.scalars(select(Contract).where(Contract.is_signed.is_(False))))


@require_role(SALES)
def get_unpaid_contracts(session: Session) -> list[Contract]:
    return list(session.scalars(select(Contract).where(Contract.amount_due > 0)))


@require_role(SUPPORT)
def get_my_events(session: Session) -> list[Event]:
    user_id = int(current_user()["sub"])
    return list(session.scalars(select(Event).where(Event.support_contact_id == user_id)))