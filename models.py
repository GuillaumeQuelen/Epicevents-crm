"""SQLAlchemy models for the Epic Events CRM."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Role(Base):
    """A department: management, sales or support."""

    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(30), unique=True)

    employees: Mapped[list["Employee"]] = relationship(back_populates="role")


class Employee(Base):
    """An Epic Events employee who can log in to the CRM."""

    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_number: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))

    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"))
    role: Mapped["Role"] = relationship(back_populates="employees")

    clients: Mapped[list["Client"]] = relationship(back_populates="sales_contact")
    events: Mapped[list["Event"]] = relationship(back_populates="support_contact")


class Client(Base):
    """A customer, always attached to the sales employee who created it."""

    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(255), unique=True)
    phone: Mapped[str] = mapped_column(String(20))
    company_name: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[date] = mapped_column(Date, default=date.today)
    last_contact: Mapped[date] = mapped_column(Date, default=date.today)

    sales_contact_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    sales_contact: Mapped["Employee"] = relationship(back_populates="clients")

    contracts: Mapped[list["Contract"]] = relationship(back_populates="client")


class Contract(Base):
    """A contract signed (or not yet) by a client.

    The sales contact of a contract is the sales contact of its client:
    it is read through ``contract.client.sales_contact`` instead of being stored twice.
    """

    __tablename__ = "contracts"

    id: Mapped[int] = mapped_column(primary_key=True)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    amount_due: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    created_at: Mapped[date] = mapped_column(Date, default=date.today)
    is_signed: Mapped[bool] = mapped_column(default=False)

    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"))
    client: Mapped["Client"] = relationship(back_populates="contracts")

    event: Mapped["Event | None"] = relationship(back_populates="contract")


class Event(Base):
    """An event organised for a signed contract (one event per contract)."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    start_date: Mapped[datetime] = mapped_column(DateTime)
    end_date: Mapped[datetime] = mapped_column(DateTime)
    location: Mapped[str] = mapped_column(String(255))
    attendees: Mapped[int]
    notes: Mapped[str | None] = mapped_column(Text)

    contract_id: Mapped[int] = mapped_column(ForeignKey("contracts.id"), unique=True)
    contract: Mapped["Contract"] = relationship(back_populates="event")

    # Nullable: an event exists before management assigns a support employee.
    support_contact_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"))
    support_contact: Mapped["Employee | None"] = relationship(back_populates="events")