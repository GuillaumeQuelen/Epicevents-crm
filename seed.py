"""Insert the three roles and one test employee per role.

Bootstrap script, run by whoever installs the application: nobody is logged in yet,
so it writes directly instead of going through write.py. Safe to run twice.
The test password is typed at run time, never written in the code.
"""

from getpass import getpass

from sqlalchemy import select

from auth import ALL_ROLES, MANAGEMENT, SALES, SUPPORT, hash_password
from database import SessionLocal
from models import Employee, Role

TEST_EMPLOYEES = [
    ("E001", "Admin Epic Events", "admin@epicevents.local", MANAGEMENT),
    ("E002", "Bill Boquet", "bill@epicevents.local", SALES),
    ("E003", "Kate Hastroff", "kate@epicevents.local", SUPPORT),
]


def main() -> None:
    password = getpass("Mot de passe des comptes de test : ")

    with SessionLocal() as session:
        roles = {}
        for role_name in ALL_ROLES:
            role = session.scalar(select(Role).where(Role.name == role_name))
            if role is None:
                role = Role(name=role_name)
                session.add(role)
            roles[role_name] = role

        for number, name, email, role_name in TEST_EMPLOYEES:
            if session.scalar(select(Employee).where(Employee.email == email)) is None:
                session.add(
                    Employee(
                        employee_number=number,
                        name=name,
                        email=email,
                        password_hash=hash_password(password),
                        role=roles[role_name],
                    )
                )
        session.commit()
    print("Rôles et comptes de test prêts.")


if __name__ == "__main__":
    main()