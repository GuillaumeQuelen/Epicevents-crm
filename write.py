"""Create, update and delete operations, with permission checks and input validation.

Order in every function: role (require_role), then ownership rule, then validation, then write.
"""

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from auth import (
    MANAGEMENT,
    SALES,
    SUPPORT,
    PermissionDenied,
    current_user,
    hash_password,
    require_role,
)
from models import Client, Contract, Employee, Event, Role
from monitoring import log_action

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_PATTERN = re.compile(r"^\+?[\d\s.-]{6,20}$")

# Fields each update function accepts. Anything else is refused,
# so a caller cannot change id, password_hash or a foreign key by accident.
EMPLOYEE_FIELDS = {"employee_number", "name", "email"}
CLIENT_FIELDS = {"full_name", "email", "phone", "company_name"}
CONTRACT_FIELDS = {"total_amount", "amount_due", "is_signed"}
EVENT_FIELDS = {"name", "start_date", "end_date", "location", "attendees", "notes"}


# --- Validation -------------------------------------------------------------


def _validate_email(email: str) -> None:
    if not EMAIL_PATTERN.match(email):
        raise ValueError(f"Email invalide : {email}")


def _validate_phone(phone: str) -> None:
    if not PHONE_PATTERN.match(phone):
        raise ValueError(f"Téléphone invalide : {phone}")


def _to_amount(value) -> Decimal:
    try:
        amount = Decimal(str(value))
    except InvalidOperation:
        raise ValueError(f"Montant invalide : {value}")
    if amount < 0:
        raise ValueError("Un montant ne peut pas être négatif.")
    return amount


def _validate_amounts(total: Decimal, due: Decimal) -> None:
    if due > total:
        raise ValueError("Le montant restant ne peut pas dépasser le montant total.")


def _validate_dates(start: datetime, end: datetime) -> None:
    if end <= start:
        raise ValueError("La date de fin doit être après la date de début.")


def _check_fields(fields: dict, allowed: set) -> None:
    unknown = set(fields) - allowed
    if unknown:
        raise ValueError(f"Champ(s) non modifiable(s) : {', '.join(sorted(unknown))}")


# --- Ownership rules (shared by several functions) ------------------------------


def _check_client_owner(user: dict, client: Client) -> None:
    """A sales employee can only act on their own clients."""
    if user["role"] == SALES and client.sales_contact_id != int(user["sub"]):
        raise PermissionDenied("Vous ne pouvez agir que sur vos propres clients.")


def _check_event_support(user: dict, event: Event) -> None:
    """A support employee can only act on the events assigned to them."""
    if user["role"] == SUPPORT and event.support_contact_id != int(user["sub"]):
        raise PermissionDenied("Vous ne pouvez modifier que vos propres événements.")


def _get_role(session: Session, role_name: str) -> Role:
    role = session.scalar(select(Role).where(Role.name == role_name))
    if role is None:
        raise ValueError(f"Rôle inconnu : {role_name}")
    return role


# --- Employees (management only) ---------------------------------------------------


@require_role(MANAGEMENT)
def create_employee(
    session: Session, employee_number: str, name: str, email: str, password: str, role_name: str
) -> Employee:
    _validate_email(email)
    employee = Employee(
        employee_number=employee_number,
        name=name,
        email=email,
        password_hash=hash_password(password),
        role=_get_role(session, role_name),
    )
    session.add(employee)
    session.commit()
    log_action("Collaborateur créé", employee_id=employee.id, role=role_name, by=current_user()["sub"])
    return employee


@require_role(MANAGEMENT)
def update_employee(session: Session, employee: Employee, role_name: str | None = None, **fields) -> Employee:
    _check_fields(fields, EMPLOYEE_FIELDS)
    if "email" in fields:
        _validate_email(fields["email"])
    if role_name is not None:
        employee.role = _get_role(session, role_name)
    for field, value in fields.items():
        setattr(employee, field, value)
    session.commit()
    changed = sorted(fields) + (["role"] if role_name is not None else [])
    log_action("Collaborateur modifié", employee_id=employee.id, fields=changed, by=current_user()["sub"])
    return employee


@require_role(MANAGEMENT)
def delete_employee(session: Session, employee: Employee) -> None:
    employee_id = employee.id
    session.delete(employee)
    session.commit()
    log_action("Collaborateur supprimé", employee_id=employee_id, by=current_user()["sub"])


# --- Clients (sales only) -------------------------------------------------------------


@require_role(SALES)
def create_client(session: Session, full_name: str, email: str, phone: str, company_name: str) -> Client:
    _validate_email(email)
    _validate_phone(phone)
    user = current_user()
    client = Client(
        full_name=full_name,
        email=email,
        phone=phone,
        company_name=company_name,
        sales_contact_id=int(user["sub"]),  # the client is automatically attached to its creator
    )
    session.add(client)
    session.commit()
    return client


@require_role(SALES)
def update_client(session: Session, client: Client, **fields) -> Client:
    user = current_user()
    _check_client_owner(user, client)
    _check_fields(fields, CLIENT_FIELDS)
    if "email" in fields:
        _validate_email(fields["email"])
    if "phone" in fields:
        _validate_phone(fields["phone"])
    for field, value in fields.items():
        setattr(client, field, value)
    client.last_contact = date.today()
    session.commit()
    return client


# --- Contracts -----------------------------------------------------------------------------


@require_role(MANAGEMENT)
def create_contract(
    session: Session, client: Client, total_amount, amount_due=None, is_signed: bool = False
) -> Contract:
    total = _to_amount(total_amount)
    due = total if amount_due is None else _to_amount(amount_due)
    _validate_amounts(total, due)
    contract = Contract(client=client, total_amount=total, amount_due=due, is_signed=is_signed)
    session.add(contract)
    session.commit()
    if contract.is_signed:
        log_action("Contrat signé", contract_id=contract.id, by=current_user()["sub"])
    return contract


@require_role(MANAGEMENT, SALES)
def update_contract(session: Session, contract: Contract, **fields) -> Contract:
    user = current_user()
    _check_client_owner(user, contract.client)  # management passes, sales only for their clients
    _check_fields(fields, CONTRACT_FIELDS)
    total = _to_amount(fields.get("total_amount", contract.total_amount))
    due = _to_amount(fields.get("amount_due", contract.amount_due))
    _validate_amounts(total, due)
    was_signed = contract.is_signed
    contract.total_amount = total
    contract.amount_due = due
    if "is_signed" in fields:
        contract.is_signed = bool(fields["is_signed"])
    session.commit()
    if contract.is_signed and not was_signed:
        log_action("Contrat signé", contract_id=contract.id, by=user["sub"])
    return contract


# --- Events ----------------------------------------------------------------------------------


@require_role(SALES)
def create_event(
    session: Session,
    contract: Contract,
    name: str,
    start_date: datetime,
    end_date: datetime,
    location: str,
    attendees: int,
    notes: str | None = None,
) -> Event:
    user = current_user()
    _check_client_owner(user, contract.client)
    if not contract.is_signed:
        raise ValueError("Le contrat doit être signé avant de créer un événement.")
    if contract.event is not None:
        raise ValueError("Ce contrat a déjà un événement.")
    _validate_dates(start_date, end_date)
    if start_date < datetime.now():
        raise ValueError("La date de début ne peut pas être dans le passé.")
    if attendees < 0:
        raise ValueError("Le nombre de participants ne peut pas être négatif.")
    event = Event(
        contract=contract,
        name=name,
        start_date=start_date,
        end_date=end_date,
        location=location,
        attendees=attendees,
        notes=notes,
    )
    session.add(event)
    session.commit()
    return event


@require_role(MANAGEMENT, SUPPORT)
def update_event(session: Session, event: Event, **fields) -> Event:
    user = current_user()
    _check_event_support(user, event)  # management passes, support only for their events
    _check_fields(fields, EVENT_FIELDS)
    start = fields.get("start_date", event.start_date)
    end = fields.get("end_date", event.end_date)
    _validate_dates(start, end)
    if fields.get("attendees", 0) < 0:
        raise ValueError("Le nombre de participants ne peut pas être négatif.")
    for field, value in fields.items():
        setattr(event, field, value)
    session.commit()
    return event


@require_role(MANAGEMENT)
def assign_support(session: Session, event: Event, support_employee: Employee) -> Event:
    if support_employee.role.name != SUPPORT:
        raise ValueError(f"{support_employee.name} n'appartient pas au département support.")
    event.support_contact = support_employee
    session.commit()
    return event