"""Epic Events CRM — command line interface.

Usage examples:
    python epicevents.py login
    python epicevents.py client list
    python epicevents.py contract list --unsigned
    python epicevents.py event assign-support 3 --support-id 5
"""

import click
from rich.console import Console
from rich.table import Table
from sqlalchemy.exc import IntegrityError, OperationalError

import read
import write
from auth import ALL_ROLES, PermissionDenied, create_token, current_user, verify_password
from database import SessionLocal
from models import Client, Contract, Employee, Event
from monitoring import init_sentry, log_exception
from token_storage import delete_token, save_token

console = Console()
DATE_FORMATS = ["%Y-%m-%d %H:%M", "%Y-%m-%d"]


class CRMGroup(click.Group):
    """Root group: turns expected errors into a clean message instead of a traceback.

    Every command runs inside this invoke(), so errors are handled in one place.
    """

    def invoke(self, ctx):
        try:
            return super().invoke(ctx)
        except PermissionDenied as error:
            raise click.ClickException(f"Accès refusé : {error}")
        except ValueError as error:
            raise click.ClickException(str(error))
        except IntegrityError:
            ctx.obj.rollback()
            raise click.ClickException(
                "Opération refusée par la base de données (valeur déjà utilisée ou donnée encore liée)."
            )
        except OperationalError as error:
            log_exception(error)
            raise click.ClickException("Base de données injoignable : vérifiez que PostgreSQL est démarré.")
        except (click.ClickException, click.exceptions.Exit, click.exceptions.Abort):
            raise  # click's own messages and exits, already clean
        except Exception as error:
            # Any other error is unexpected: it goes to Sentry, the user gets a short message.
            log_exception(error)
            raise click.ClickException("Erreur inattendue. Elle a été signalée à l'équipe technique.")


@click.group(cls=CRMGroup)
@click.pass_context
def cli(ctx):
    """Epic Events CRM."""
    init_sentry()
    # The click context carries one database session, shared by the command that runs.
    session = SessionLocal()
    ctx.obj = session
    ctx.call_on_close(session.close)


def _get(session, model, object_id: int):
    """Load an object by id. Requires a logged-in user, whatever the role."""
    current_user()
    obj = session.get(model, object_id)
    if obj is None:
        raise click.ClickException(f"{model.__name__} {object_id} introuvable.")
    return obj


def _only_given(**options) -> dict:
    """Keep only the options the user actually typed."""
    return {name: value for name, value in options.items() if value is not None}


def _show(title: str, columns: list[str], rows: list[list]) -> None:
    if not rows:
        console.print(f"[yellow]{title} : aucun résultat.[/yellow]")
        return
    table = Table(title=title)
    for column in columns:
        table.add_column(column, overflow="fold")  # wrap long values instead of cutting them
    for row in rows:
        table.add_row(*["" if value is None else str(value) for value in row])
    console.print(table)


def _done(message: str) -> None:
    console.print(f"[green]{message}[/green]")


# --- Authentication ------------------------------------------------------------------------


@cli.command()
@click.option("--email", prompt="Email")
@click.option("--password", prompt="Mot de passe", hide_input=True)
@click.pass_obj
def login(session, email, password):
    """Log in and keep the session for 8 hours."""
    employee = read.find_employee_by_email(session, email.strip())
    if employee is None or not verify_password(password, employee.password_hash):
        raise click.ClickException("Email ou mot de passe incorrect.")
    save_token(create_token(employee.id, employee.role))
    _done(f"Connecté ({employee.role}).")


@cli.command()
def logout():
    """Delete the local session token."""
    delete_token()
    _done("Déconnecté.")


@cli.command()
@click.pass_obj
def whoami(session):
    """Show the logged-in employee."""
    user = current_user()
    employee = _get(session, Employee, int(user["sub"]))
    console.print(f"{employee.name} ({employee.email}) — rôle : {user['role']}")


# --- Employees -----------------------------------------------------------------------------


@cli.group()
def employee():
    """Manage employees (management)."""


@employee.command("list")
@click.pass_obj
def employee_list(session):
    rows = [[e.id, e.employee_number, e.name, e.email, e.role.name] for e in read.get_employees(session)]
    _show("Collaborateurs", ["ID", "Numéro", "Nom", "Email", "Rôle"], rows)


@employee.command("create")
@click.option("--number", prompt="Numéro d'employé")
@click.option("--name", prompt="Nom")
@click.option("--email", prompt="Email")
@click.option("--role", type=click.Choice(ALL_ROLES), prompt="Rôle")
@click.option("--password", prompt="Mot de passe", hide_input=True, confirmation_prompt=True)
@click.pass_obj
def employee_create(session, number, name, email, role, password):
    new = write.create_employee(session, number, name, email, password, role)
    _done(f"Collaborateur {new.id} créé.")


@employee.command("update")
@click.argument("employee_id", type=int)
@click.option("--number", "employee_number")
@click.option("--name")
@click.option("--email")
@click.option("--role", type=click.Choice(ALL_ROLES))
@click.pass_obj
def employee_update(session, employee_id, employee_number, name, email, role):
    target = _get(session, Employee, employee_id)
    fields = _only_given(employee_number=employee_number, name=name, email=email)
    write.update_employee(session, target, role_name=role, **fields)
    _done(f"Collaborateur {employee_id} modifié.")


@employee.command("delete")
@click.argument("employee_id", type=int)
@click.confirmation_option(prompt="Supprimer ce collaborateur ?")
@click.pass_obj
def employee_delete(session, employee_id):
    write.delete_employee(session, _get(session, Employee, employee_id))
    _done(f"Collaborateur {employee_id} supprimé.")


# --- Clients ---------------------------------------------------------------------------------


@cli.group()
def client():
    """Manage clients."""


@client.command("list")
@click.pass_obj
def client_list(session):
    rows = [
        [c.id, c.full_name, c.email, c.phone, c.company_name, c.last_contact, c.sales_contact.name]
        for c in read.get_clients(session)
    ]
    _show("Clients", ["ID", "Nom", "Email", "Téléphone", "Entreprise", "Dernier contact", "Commercial"], rows)


@client.command("create")
@click.option("--name", "full_name", prompt="Nom complet")
@click.option("--email", prompt="Email")
@click.option("--phone", prompt="Téléphone")
@click.option("--company", "company_name", prompt="Entreprise")
@click.pass_obj
def client_create(session, full_name, email, phone, company_name):
    new = write.create_client(session, full_name, email, phone, company_name)
    _done(f"Client {new.id} créé.")


@client.command("update")
@click.argument("client_id", type=int)
@click.option("--name", "full_name")
@click.option("--email")
@click.option("--phone")
@click.option("--company", "company_name")
@click.pass_obj
def client_update(session, client_id, full_name, email, phone, company_name):
    target = _get(session, Client, client_id)
    write.update_client(
        session, target, **_only_given(full_name=full_name, email=email, phone=phone, company_name=company_name)
    )
    _done(f"Client {client_id} modifié.")


# --- Contracts -------------------------------------------------------------------------------


@cli.group()
def contract():
    """Manage contracts."""


@contract.command("list")
@click.option("--unsigned", is_flag=True, help="Seulement les contrats non signés (commercial).")
@click.option("--unpaid", is_flag=True, help="Seulement les contrats pas entièrement payés (commercial).")
@click.pass_obj
def contract_list(session, unsigned, unpaid):
    if unsigned:
        contracts = read.get_unsigned_contracts(session)
    elif unpaid:
        contracts = read.get_unpaid_contracts(session)
    else:
        contracts = read.get_contracts(session)
    rows = [
        [k.id, k.client.full_name, k.client.sales_contact.name, k.total_amount, k.amount_due,
         k.created_at, "oui" if k.is_signed else "non"]
        for k in contracts
    ]
    _show("Contrats", ["ID", "Client", "Commercial", "Total", "Restant", "Créé le", "Signé"], rows)


@contract.command("create")
@click.option("--client-id", type=int, prompt="ID du client")
@click.option("--total", prompt="Montant total")
@click.option("--due", default=None, help="Montant restant (par défaut : le total).")
@click.option("--signed", is_flag=True)
@click.pass_obj
def contract_create(session, client_id, total, due, signed):
    new = write.create_contract(session, _get(session, Client, client_id), total, due, signed)
    _done(f"Contrat {new.id} créé.")


@contract.command("update")
@click.argument("contract_id", type=int)
@click.option("--total", "total_amount")
@click.option("--due", "amount_due")
@click.option("--signed/--unsigned", "is_signed", default=None)
@click.pass_obj
def contract_update(session, contract_id, total_amount, amount_due, is_signed):
    target = _get(session, Contract, contract_id)
    write.update_contract(
        session, target, **_only_given(total_amount=total_amount, amount_due=amount_due, is_signed=is_signed)
    )
    _done(f"Contrat {contract_id} modifié.")


# --- Events ----------------------------------------------------------------------------------


@cli.group()
def event():
    """Manage events."""


@event.command("list")
@click.option("--no-support", is_flag=True, help="Seulement les événements sans support (gestion).")
@click.option("--mine", is_flag=True, help="Seulement mes événements (support).")
@click.pass_obj
def event_list(session, no_support, mine):
    if no_support:
        events = read.get_events_without_support(session)
    elif mine:
        events = read.get_my_events(session)
    else:
        events = read.get_events(session)
    rows = [
        [e.id, e.name, e.contract_id, e.contract.client.full_name,
         e.start_date.strftime("%Y-%m-%d %H:%M"), e.end_date.strftime("%Y-%m-%d %H:%M"),
         e.location, e.attendees, e.support_contact.name if e.support_contact else "à assigner"]
        for e in events
    ]
    _show("Événements", ["ID", "Nom", "Contrat", "Client", "Début", "Fin", "Lieu", "Participants", "Support"], rows)


@event.command("create")
@click.option("--contract-id", type=int, prompt="ID du contrat")
@click.option("--name", prompt="Nom de l'événement")
@click.option("--start", type=click.DateTime(DATE_FORMATS), prompt="Début (AAAA-MM-JJ HH:MM)")
@click.option("--end", type=click.DateTime(DATE_FORMATS), prompt="Fin (AAAA-MM-JJ HH:MM)")
@click.option("--location", prompt="Lieu")
@click.option("--attendees", type=click.IntRange(min=0), prompt="Nombre de participants")
@click.option("--notes", default=None)
@click.pass_obj
def event_create(session, contract_id, name, start, end, location, attendees, notes):
    target = _get(session, Contract, contract_id)
    new = write.create_event(session, target, name, start, end, location, attendees, notes)
    _done(f"Événement {new.id} créé.")


@event.command("update")
@click.argument("event_id", type=int)
@click.option("--name")
@click.option("--start", "start_date", type=click.DateTime(DATE_FORMATS))
@click.option("--end", "end_date", type=click.DateTime(DATE_FORMATS))
@click.option("--location")
@click.option("--attendees", type=click.IntRange(min=0))
@click.option("--notes")
@click.pass_obj
def event_update(session, event_id, **options):
    write.update_event(session, _get(session, Event, event_id), **_only_given(**options))
    _done(f"Événement {event_id} modifié.")


@event.command("assign-support")
@click.argument("event_id", type=int)
@click.option("--support-id", type=int, prompt="ID du collaborateur support")
@click.pass_obj
def event_assign_support(session, event_id, support_id):
    target = _get(session, Event, event_id)
    write.assign_support(session, target, _get(session, Employee, support_id))
    _done(f"Support assigné à l'événement {event_id}.")


if __name__ == "__main__":
    cli()