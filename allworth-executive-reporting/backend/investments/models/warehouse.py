"""SQLAlchemy ORM models for warehouse-backed account analysis.

These models represent the two primary source tables used by the new
account-number analyzer:

- ``tho.Account_Daily_Holdings`` (position/account facts)
- ``tav.Security_Info`` (security enrichment)
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, Integer, Numeric, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for ORM models."""


class SecurityInfo(Base):
    __tablename__ = "Security_Info"
    __table_args__ = {"schema": "tav"}

    cusip: Mapped[str | None] = mapped_column(
        "CUSIP", String(20), primary_key=True, index=True, nullable=True
    )
    symbol: Mapped[str | None] = mapped_column("Symbol", String(50), nullable=True)
    security_description: Mapped[str | None] = mapped_column(
        "Security_Description", String(255), nullable=True
    )
    security_type: Mapped[str | None] = mapped_column("Security_Type", String(100), nullable=True)
    sector: Mapped[str | None] = mapped_column("Sector", String(120), nullable=True)
    broad_sector: Mapped[str | None] = mapped_column("Broad_Sector", String(120), nullable=True)
    segment: Mapped[str | None] = mapped_column("Segment", String(120), nullable=True)
    issue_state: Mapped[str | None] = mapped_column("Issue_State", String(40), nullable=True)

    interest_rate: Mapped[Decimal | None] = mapped_column("Interest_Rate", Numeric(18, 6), nullable=True)
    current_price: Mapped[Decimal | None] = mapped_column("Current_Price", Numeric(18, 6), nullable=True)
    current_yield_to_worst: Mapped[Decimal | None] = mapped_column(
        "Current_Yield_To_Worst_Market", Numeric(18, 6), nullable=True
    )
    effective_duration: Mapped[Decimal | None] = mapped_column(
        "Effective_Duration", Numeric(18, 6), nullable=True
    )
    security_annual_income: Mapped[Decimal | None] = mapped_column(
        "Annual_Dividend", Numeric(18, 6), nullable=True
    )

    issue_date: Mapped[date | None] = mapped_column("Issue_Date", Date, nullable=True)
    maturity_date: Mapped[date | None] = mapped_column("Maturity_Date", Date, nullable=True)
    call_date: Mapped[date | None] = mapped_column("Call_Date", Date, nullable=True)
    call_price: Mapped[Decimal | None] = mapped_column("Call_Price", Numeric(18, 6), nullable=True)
    income_frequency: Mapped[str | None] = mapped_column("Income_Frequency", String(50), nullable=True)

    fitch_rating: Mapped[str | None] = mapped_column("Fitch_Bond_Rating", String(20), nullable=True)
    previous_fitch_rating: Mapped[str | None] = mapped_column(
        "Fitch_Bond_Rating_Previous_Value", String(20), nullable=True
    )
    previous_fitch_effective_date: Mapped[date | None] = mapped_column(
        "Fitch_Bond_Rating_Previous_Value_Effective_Date", Date, nullable=True
    )
    fitch_effective_date: Mapped[date | None] = mapped_column(
        "Fitch_Bond_Rating_Effective_Date", Date, nullable=True
    )

    federal_taxable: Mapped[bool | None] = mapped_column("Federal_Taxable", Boolean, nullable=True)
    state_taxable: Mapped[bool | None] = mapped_column("State_Taxable", Boolean, nullable=True)


class AccountDailyHoldings(Base):
    __tablename__ = "Account_Daily_Holdings"
    __table_args__ = {"schema": "tho"}

    holding_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_number: Mapped[str] = mapped_column("Account_Number", String(64), index=True)
    account_name: Mapped[str | None] = mapped_column("Account_Name", String(255), nullable=True)
    cusip: Mapped[str | None] = mapped_column("CUSIP", String(20), index=True, nullable=True)
    symbol: Mapped[str | None] = mapped_column("Symbol", String(50), nullable=True)
    security_description: Mapped[str | None] = mapped_column(
        "Security_Description", String(255), nullable=True
    )
    security_type: Mapped[str | None] = mapped_column("Security_Type", String(100), nullable=True)

    quantity: Mapped[Decimal | None] = mapped_column("Quantity", Numeric(22, 6), nullable=True)
    market_value: Mapped[Decimal | None] = mapped_column("Market_Value", Numeric(22, 6), nullable=True)
    current_price: Mapped[Decimal | None] = mapped_column("Current_Price", Numeric(18, 6), nullable=True)
    as_of_date: Mapped[date | None] = mapped_column("As_Of_Date", Date, nullable=True)
