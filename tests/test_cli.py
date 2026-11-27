"""The command line interface, end to end, with click's test runner."""

import pytest
from click.testing import CliRunner
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

import epicevents
import read
import write
from conftest import PASSWORD


@pytest.fixture
def run(engine, session, monkeypatch):
    """Run a CLI command against the test database."""
    monkeypatch.setattr(epicevents, "SessionLocal", sessionmaker(bind=engine))
    monkeypatch.setattr(epicevents.console, "width", 200)  # wide enough to read whole tables
    runner = CliRunner()

    def _run(*args, input=None):
        return runner.invoke(epicevents.cli, list(args), input=input)

    return _run


def login(run, email):
    result = run("login", "--email", email, "--password", PASSWORD)
    assert result.exit_code == 0, result.output


def test_login_with_a_wrong_password(run):
    result = run("login", "--email", "bill@test.local", "--password", "wrong")
    assert result.exit_code != 0
    assert "incorrect" in result.output


def test_unknown_email_gets_the_same_message(run):
    result = run("login", "--email", "nobody@test.local", "--password", "wrong")
    assert "Email ou mot de passe incorrect" in result.output


def test_login_then_whoami(run):
    login(run, "bill@test.local")
    assert "Bill Boquet" in run("whoami").output


def test_commands_require_login(run):
    result = run("client", "list")
    assert result.exit_code != 0
    assert "Vous devez vous connecter" in result.output


def test_permission_denied_shows_a_clean_message(run):
    login(run, "admin@test.local")
    result = run("client", "create", "--name", "K", "--email", "k@x.io", "--phone", "+33 6 11 22 33 44",
                 "--company", "C")
    assert "Accès refusé" in result.output
    assert "Traceback" not in result.output


def test_invalid_data_shows_a_clean_message(run):
    login(run, "bill@test.local")
    result = run("client", "create", "--name", "K", "--email", "nope", "--phone", "+33 6 11 22 33 44",
                 "--company", "C")
    assert "Email invalide" in result.output


def test_unknown_id_is_reported(run):
    login(run, "admin@test.local")
    assert "introuvable" in run("contract", "create", "--client-id", "99", "--total", "10").output


def test_unexpected_error_is_sent_to_sentry(run, monkeypatch, bill_client):
    reported = []
    monkeypatch.setattr(epicevents, "log_exception", reported.append)

    def broken(*args, **kwargs):
        raise RuntimeError("simulated bug")

    monkeypatch.setattr(write, "update_client", broken)
    login(run, "bill@test.local")
    result = run("client", "update", str(bill_client.id), "--name", "X")
    assert "Erreur inattendue" in result.output
    assert isinstance(reported[0], RuntimeError)


def test_full_business_cycle(run, future):
    start, end = (date.strftime("%Y-%m-%d %H:%M") for date in future)

    login(run, "bill@test.local")
    assert "Client 1 créé" in run("client", "create", "--name", "Kevin Casey", "--email", "kevin@startup.io",
                                  "--phone", "+678 123 456 78", "--company", "Cool Startup").output

    login(run, "admin@test.local")
    assert "Contrat 1 créé" in run("contract", "create", "--client-id", "1", "--total", "5000").output
    assert "modifié" in run("contract", "update", "1", "--signed").output

    login(run, "bill@test.local")
    result = run("event", "create", "--contract-id", "1", "--name", "Wedding", "--start", start, "--end", end,
                 "--location", "Candé", "--attendees", "75")
    assert "Événement 1 créé" in result.output

    login(run, "admin@test.local")
    assert "Wedding" in run("event", "list", "--no-support").output
    assert "Support assigné" in run("event", "assign-support", "1", "--support-id", "3").output
    assert "aucun résultat" in run("event", "list", "--no-support").output

    login(run, "kate@test.local")
    assert "modifié" in run("event", "update", "1", "--attendees", "80").output
    assert "Kate Hastroff" in run("event", "list", "--mine").output


def test_logout(run):
    login(run, "bill@test.local")
    run("logout")
    assert "Vous devez vous connecter" in run("client", "list").output


def test_duplicate_email_is_refused_cleanly(run, bill_client):
    login(run, "bill@test.local")
    result = run("client", "create", "--name", "K", "--email", "kevin@startup.io", "--phone", "+33 6 11 22 33 44",
                 "--company", "C")
    assert "Opération refusée par la base de données" in result.output


def test_database_down_is_reported_cleanly(run, monkeypatch):
    def down(*args, **kwargs):
        raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    monkeypatch.setattr(read, "get_clients", down)
    monkeypatch.setattr(epicevents, "log_exception", lambda error: None)
    login(run, "bill@test.local")
    assert "Base de données injoignable" in run("client", "list").output


def test_employee_commands(run):
    login(run, "admin@test.local")
    result = run("employee", "create", "--number", "E010", "--name", "Nina", "--email", "nina@test.local",
                 "--role", "sales", "--password", "Secret123", input="Secret123\n")
    assert "Collaborateur 6 créé" in result.output
    assert "modifié" in run("employee", "update", "6", "--role", "support").output
    assert "Nina" in run("employee", "list").output
    assert "supprimé" in run("employee", "delete", "6", "--yes").output


def test_client_and_contract_commands(run, contract):
    login(run, "bill@test.local")
    assert "Kevin Casey" in run("client", "list").output
    assert "modifié" in run("client", "update", "1", "--company", "New Name").output
    assert "Kevin Casey" in run("contract", "list", "--unsigned").output
    assert "Kevin Casey" in run("contract", "list", "--unpaid").output
    assert "5000.00" in run("contract", "list").output


def test_event_list_shows_every_event(run, event_):
    login(run, "kate@test.local")
    assert "John Ouick Wedding" in run("event", "list").output