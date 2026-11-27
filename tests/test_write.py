"""Create and update operations: permissions, ownership rules, validation and Sentry messages."""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

import write
from auth import PermissionDenied, verify_password


# --- Employees ---------------------------------------------------------------------------------


def test_management_creates_an_employee_and_it_is_logged(session, login_as, actions):
    login_as("admin@test.local")
    new = write.create_employee(session, "E010", "Nina", "nina@test.local", "Secret123", "sales")
    assert new.role.name == "sales"
    assert verify_password("Secret123", new.password_hash)
    assert actions == [("Collaborateur créé", {"employee_id": new.id, "role": "sales", "by": "1"})]


def test_sales_cannot_create_an_employee(session, login_as):
    login_as("bill@test.local")
    with pytest.raises(PermissionDenied):
        write.create_employee(session, "E010", "Nina", "nina@test.local", "Secret123", "sales")


def test_unknown_role_is_refused(session, login_as):
    login_as("admin@test.local")
    with pytest.raises(ValueError, match="Rôle inconnu"):
        write.create_employee(session, "E010", "Nina", "nina@test.local", "Secret123", "boss")


def test_update_employee_including_department_is_logged(session, login_as, employee, actions):
    login_as("admin@test.local")
    sam = employee("sam@test.local")
    write.update_employee(session, sam, role_name="support", name="Sam S.")
    assert sam.role.name == "support"
    assert actions[0][0] == "Collaborateur modifié"
    assert actions[0][1]["fields"] == ["name", "role"]


def test_update_employee_refuses_protected_fields(session, login_as, employee):
    login_as("admin@test.local")
    with pytest.raises(ValueError, match="non modifiable"):
        write.update_employee(session, employee("sam@test.local"), password_hash="x")


def test_an_employee_with_clients_cannot_be_deleted(session, login_as, bill_client, employee):
    login_as("admin@test.local")
    with pytest.raises(IntegrityError):
        write.delete_employee(session, employee("bill@test.local"))


def test_an_employee_without_clients_can_be_deleted(session, login_as, employee, actions):
    login_as("admin@test.local")
    write.delete_employee(session, employee("sam@test.local"))
    assert employee("sam@test.local") is None
    assert actions[0][0] == "Collaborateur supprimé"


# --- Clients ------------------------------------------------------------------------------------


def test_sales_creates_a_client_attached_to_them(session, login_as):
    bill = login_as("bill@test.local")
    client = write.create_client(session, "Kevin Casey", "kevin@startup.io", "+678 123 456 78", "Cool Startup")
    assert client.sales_contact == bill


def test_management_cannot_create_a_client(session, login_as):
    login_as("admin@test.local")
    with pytest.raises(PermissionDenied):
        write.create_client(session, "Kevin Casey", "kevin@startup.io", "+678 123 456 78", "Cool Startup")


@pytest.mark.parametrize(
    "email, phone, message",
    [("not-an-email", "+33 6 11 22 33 44", "Email"), ("ok@test.io", "call me", "Téléphone")],
)
def test_client_data_is_validated(session, login_as, email, phone, message):
    login_as("bill@test.local")
    with pytest.raises(ValueError, match=message):
        write.create_client(session, "X", email, phone, "X")


def test_sales_updates_their_own_client(session, login_as, bill_client):
    login_as("bill@test.local")
    write.update_client(session, bill_client, phone="+33 1 23 45 67 89")
    assert bill_client.phone == "+33 1 23 45 67 89"


def test_sales_cannot_update_another_sellers_client(session, login_as, bill_client):
    login_as("sam@test.local")
    with pytest.raises(PermissionDenied, match="propres clients"):
        write.update_client(session, bill_client, phone="+33 1 23 45 67 89")


def test_client_owner_cannot_be_changed_through_update(session, login_as, bill_client):
    login_as("bill@test.local")
    with pytest.raises(ValueError, match="non modifiable"):
        write.update_client(session, bill_client, sales_contact_id=4)


# --- Contracts ----------------------------------------------------------------------------------


def test_management_creates_a_contract(session, login_as, bill_client):
    login_as("admin@test.local")
    contract = write.create_contract(session, bill_client, "5000")
    assert contract.total_amount == Decimal("5000")
    assert contract.amount_due == Decimal("5000")
    assert contract.is_signed is False


@pytest.mark.parametrize("total, due", [("-1", None), ("100", "200"), ("abc", None)])
def test_contract_amounts_are_validated(session, login_as, bill_client, total, due):
    login_as("admin@test.local")
    with pytest.raises(ValueError):
        write.create_contract(session, bill_client, total, due)


def test_signature_is_logged_once(session, login_as, contract, actions):
    login_as("bill@test.local")
    write.update_contract(session, contract, is_signed=True)
    write.update_contract(session, contract, amount_due="1000")
    assert actions == [("Contrat signé", {"contract_id": contract.id, "by": "2"})]


def test_contract_created_already_signed_is_logged(session, login_as, bill_client, actions):
    login_as("admin@test.local")
    write.create_contract(session, bill_client, "100", is_signed=True)
    assert actions[0][0] == "Contrat signé"


def test_sales_cannot_update_another_sellers_contract(session, login_as, contract):
    login_as("sam@test.local")
    with pytest.raises(PermissionDenied):
        write.update_contract(session, contract, is_signed=True)


def test_support_cannot_update_a_contract(session, login_as, contract):
    login_as("kate@test.local")
    with pytest.raises(PermissionDenied):
        write.update_contract(session, contract, is_signed=True)


# --- Events -------------------------------------------------------------------------------------


def test_sales_creates_an_event_for_a_signed_contract(session, login_as, signed_contract, future):
    login_as("bill@test.local")
    start, end = future
    created = write.create_event(session, signed_contract, "Wedding", start, end, "Candé", 75)
    assert created.contract == signed_contract
    assert created.support_contact is None


def test_no_event_for_an_unsigned_contract(session, login_as, contract, future):
    login_as("bill@test.local")
    with pytest.raises(ValueError, match="signé"):
        write.create_event(session, contract, "Wedding", *future, "Candé", 75)


def test_no_event_for_another_sellers_client(session, login_as, signed_contract, future):
    login_as("sam@test.local")
    with pytest.raises(PermissionDenied):
        write.create_event(session, signed_contract, "Wedding", *future, "Candé", 75)


def test_only_one_event_per_contract(session, login_as, event_, future):
    login_as("bill@test.local")
    with pytest.raises(ValueError, match="déjà"):
        write.create_event(session, event_.contract, "Second", *future, "Lens", 10)


def test_event_cannot_start_in_the_past(session, login_as, signed_contract):
    login_as("bill@test.local")
    with pytest.raises(ValueError, match="passé"):
        write.create_event(session, signed_contract, "Old", datetime(2021, 1, 1), datetime(2021, 1, 2), "Lens", 10)


def test_event_end_must_follow_start(session, login_as, signed_contract, future):
    login_as("bill@test.local")
    start, _end = future
    with pytest.raises(ValueError, match="fin"):
        write.create_event(session, signed_contract, "Wedding", start, start - timedelta(hours=1), "Candé", 75)


def test_management_assigns_a_support_employee(session, login_as, event_, employee):
    login_as("admin@test.local")
    write.assign_support(session, event_, employee("kate@test.local"))
    assert event_.support_contact.name == "Kate Hastroff"


def test_only_a_support_employee_can_be_assigned(session, login_as, event_, employee):
    login_as("admin@test.local")
    with pytest.raises(ValueError, match="support"):
        write.assign_support(session, event_, employee("bill@test.local"))


def test_support_updates_their_own_event(session, login_as, event_, employee):
    event_.support_contact = employee("kate@test.local")
    session.commit()
    login_as("kate@test.local")
    write.update_event(session, event_, attendees=80, notes="DJ")
    assert event_.attendees == 80


def test_support_cannot_update_another_supports_event(session, login_as, event_, employee):
    event_.support_contact = employee("kate@test.local")
    session.commit()
    login_as("lea@test.local")
    with pytest.raises(PermissionDenied):
        write.update_event(session, event_, attendees=80)


def test_event_update_refuses_the_support_field(session, login_as, event_):
    login_as("admin@test.local")
    with pytest.raises(ValueError, match="non modifiable"):
        write.update_event(session, event_, support_contact_id=3)