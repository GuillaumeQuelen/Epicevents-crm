"""Read operations: who can read what, filters and the raw SQL login lookup."""

import pytest

import read
import token_storage
from auth import PermissionDenied, create_token


@pytest.mark.parametrize("email", ["admin@test.local", "bill@test.local", "kate@test.local"])
def test_every_role_reads_clients_contracts_and_events(session, login_as, event_, email):
    login_as(email)
    assert len(read.get_clients(session)) == 1
    assert len(read.get_contracts(session)) == 1
    assert len(read.get_events(session)) == 1


def test_reading_requires_login(session):
    with pytest.raises(PermissionDenied):
        read.get_clients(session)


def test_unknown_role_cannot_read(session):
    token_storage.save_token(create_token(1, "intern"))
    with pytest.raises(PermissionDenied):
        read.get_clients(session)


def test_only_management_lists_employees(session, login_as):
    login_as("admin@test.local")
    assert len(read.get_employees(session)) == 5
    login_as("bill@test.local")
    with pytest.raises(PermissionDenied):
        read.get_employees(session)


def test_events_without_support_left_join(session, login_as, event_, employee):
    login_as("admin@test.local")
    assert read.get_events_without_support(session) == [event_]
    event_.support_contact = employee("kate@test.local")
    session.commit()
    assert read.get_events_without_support(session) == []


def test_support_sees_only_their_events(session, login_as, event_, employee):
    event_.support_contact = employee("kate@test.local")
    session.commit()
    login_as("kate@test.local")
    assert read.get_my_events(session) == [event_]
    login_as("lea@test.local")
    assert read.get_my_events(session) == []


def test_sales_filters(session, login_as, contract):
    login_as("bill@test.local")
    assert read.get_unsigned_contracts(session) == [contract]
    assert read.get_unpaid_contracts(session) == [contract]
    contract.is_signed = True
    contract.amount_due = 0
    session.commit()
    assert read.get_unsigned_contracts(session) == []
    assert read.get_unpaid_contracts(session) == []


def test_login_lookup_finds_the_employee_and_role(session):
    row = read.find_employee_by_email(session, "bill@test.local")
    assert row.role == "sales"


def test_login_lookup_resists_sql_injection(session):
    assert read.find_employee_by_email(session, "x' OR '1'='1") is None