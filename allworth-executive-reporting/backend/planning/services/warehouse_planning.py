"""Read-only DataWarehouse adapter for Salesforce Financial Services Cloud data.

Warehouse records are mapped into planning facts with field-level provenance.
No write-back occurs from this module.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
import re
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from planengine.models import Account, Assumptions, Facts, Flow, Holding, Indexing, Mortgage, Person
from planning.services.warehouse_monte_carlo import resolve_monte_carlo_inputs


SOURCE_CONTRACT = {
    "households": {"table": "sfp.Account", "identity": "Id",
                   "fields": ["Id", "Name", "OwnerId", "Primary_Client__c", "Secondary_Client__c", "LastModifiedDate"]},
    "contacts": {"table": "sfp.Contact", "identity": "Id",
                 "fields": ["Id", "AccountId", "FirstName", "LastName", "Birthdate", "Email", "FinServ__AnnualIncome__c", "LastModifiedDate"]},
    "relationships": {"table": "sfp.AccountContactRelation", "identity": "Id",
                      "fields": ["Id", "AccountId", "ContactId", "Roles", "IsActive", "LastModifiedDate"]},
    "financial_accounts": {"table": "sfp.FinServ__FinancialAccount__c", "identity": "Id",
                           "fields": ["Id", "FinServ__Household__c", "FinServ__PrimaryOwner__c", "FinServ__JointOwner__c", "Name", "FinServ__FinancialAccountType__c", "FinServ__Balance__c", "Total_Value__c", "FinServ__PrincipalBalance__c", "FinServ__InterestRate__c", "FinServ__LoanTermMonths__c", "LastModifiedDate"]},
    "advisors": {"table": "sfp.User", "identity": "Id",
                 "fields": ["Id", "Name", "Email", "IsActive", "LastModifiedDate"]},
    "tasks": {"table": "sfp.Task", "identity": "Id",
              "fields": ["Id", "FinServ__Household__c", "OwnerId", "Subject", "Status", "ActivityDate", "LastModifiedDate"]},
    "holdings": {"table": "tho.Account_Daily_Holdings", "identity": "Account_Number",
                 "fields": ["Account_Number", "Account_Name", "Symbol", "CUSIP", "Security_Description", "Security_Type", "Asset_Class", "Sector", "Cost_Basis", "Current_Price", "Quantity", "Weight", "Total_Account_Value", "As_Of_Date", "avhhid"]},
    "household_facts": {"table": "tho.Current_Household_Fact", "identity": "HHID",
                        "fields": ["HHID", "AVHHID", "AUM", "Expected_Retirement_Date__c"]},
    "contact_demographics": {"table": "tho.Contact_Demographic", "identity": "contact_id",
                             "fields": ["contact_id", "hh_id", "dob", "retire_date", "primary_or_secondary", "employment_status"]},
    "account_demographics": {"table": "tho.Current_Account_Demographic", "identity": "Account_Number",
                             "fields": ["Account_Number", "Account_Name", "Primary_Household_ID", "Financial_Account_SFID", "Account_Type", "Taxable", "Total_Account_Value", "Managed_Account_Value", "Current_Cash", "Risk_Tolerance__c", "Investment_Time_Horizon_BD__c", "Federal_Tax_Bracket_BD__c", "Client_Annual_Income_BD__c", "State_of_Primary_Residence", "Date"]},
    "plan_reviews": {"table": "sfp.Plan_Review__c", "identity": "Id",
                     "fields": ["Household__c", "Monthly_Expenses__c", "LastModifiedDate"]},
    "cma_volatility": {"table": "tav.Asset_Class_Historical_Volatility", "identity": "Asset Class",
                       "fields": ["Asset Class", "Volatility"]},
}


class AmbiguousHouseholdError(LookupError):
    """Raised when an exact warehouse household name is not unique."""


def resolve_household_id(session: Session, household_name: str) -> str:
    """Resolve one exact Salesforce household name without fuzzy matching."""
    rows = session.execute(text("""
        SELECT TOP 2 [Id]
        FROM [sfp].[Account]
        WHERE [Name] = :name
        ORDER BY [LastModifiedDate] DESC
    """), {"name": household_name}).mappings().all()
    if not rows:
        raise KeyError(household_name)
    if len(rows) > 1:
        raise AmbiguousHouseholdError(household_name)
    return str(rows[0]["Id"])


def contract() -> dict:
    return {"mode": "read_only", "system_of_record": {
        "demographics": "Salesforce Financial Services Cloud via sfp schema",
        "holdings_and_lots": "Tamarac via tho schema",
        "planning_assumptions": "PlanEngine-owned Azure Synapse facts versions"},
        "entities": SOURCE_CONTRACT,
        "provenance": "Every imported field records source table, source id, source field, and observed timestamp."}


def _value(row: dict, *names, default=None):
    for name in names:
        if name in row and row[name] is not None:
            return row[name]
    return default


def _as_date(value: Any) -> date | None:
    if isinstance(value, date): return value
    if value in (None, ""): return None
    raw = str(value).strip()
    if re.fullmatch(r"\d{8}\.0+", raw): raw = raw.split(".", 1)[0]
    if re.fullmatch(r"\d{8}", raw): raw = f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"
    try: return date.fromisoformat(raw[:10])
    except ValueError: return None


def _age_on(born: date, observed: date) -> int:
    return observed.year - born.year - ((observed.month, observed.day) < (born.month, born.day))


def _monthly_expense(value: Any) -> Decimal | None:
    """Accept an explicit numeric/currency value; reject narrative summaries."""
    if value in (None, ""): return None
    raw = str(value).strip()
    compact = raw.replace("$", "").replace(",", "").strip()
    if re.fullmatch(r"\d+(?:\.\d{1,2})?", compact):
        amount = Decimal(compact)
        return amount if amount > 0 else None
    matches = re.findall(r"\$\s*([0-9][0-9,]*(?:\.\d{1,2})?)", raw)
    if len(matches) == 1 and len(raw) <= 120:
        amount = Decimal(matches[0].replace(",", ""))
        return amount if amount > 0 else None
    return None


def _annual_income_estimate(value: Any) -> tuple[Decimal | None, bool]:
    """Return a numeric income and whether a warehouse band was estimated.

    Salesforce/Tamarac demographic feeds contain both numeric values and labels
    such as ``Over $100,000``.  Band conversions use a conservative bound and
    are always surfaced for advisor review by the caller.
    """
    if value in (None, ""):
        return None, False
    raw = str(value).strip()
    compact = raw.replace("$", "").replace(",", "").strip()
    try:
        amount = Decimal(compact)
        return (amount, False) if amount > 0 else (None, False)
    except Exception:
        pass
    numbers = [Decimal(number.replace(",", "")) for number in re.findall(r"[0-9][0-9,]*", raw)]
    lowered = raw.lower()
    if not numbers:
        return None, False
    if any(word in lowered for word in ("over", "above", "+")):
        return numbers[0], True
    if any(word in lowered for word in ("under", "below", "less than")):
        return numbers[0] / 2, True
    if len(numbers) >= 2:
        return (numbers[0] + numbers[1]) / 2, True
    return None, False


def _decimal_or_none(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        amount = Decimal(str(value).replace("$", "").replace(",", "").strip())
    except Exception:
        return None
    return amount if amount >= 0 else abs(amount)


def _account_kind(account_type: Any, taxable: Any = None) -> str:
    raw = f"{account_type or ''} {taxable or ''}".lower()
    if any(token in raw for token in ("roth",)):
        return "roth"
    if any(token in raw for token in ("ira", "401", "403", "retirement", "qualified")):
        return "qualified"
    if any(token in raw for token in ("529", "education")):
        return "529"
    if any(token in raw for token in ("cash", "checking", "savings", "money market")):
        return "cash"
    return "taxable"


def _is_liability_account(row: dict) -> bool:
    account_type = str(_value(row, "FinServ__FinancialAccountType__c", "FinServ__Type__c",
                              "Account_Type__c", default="")).lower()
    name = str(_value(row, "Name", default="")).lower()
    text = f"{account_type} {name}"
    liability_tokens = (
        "mortgage", "loan", "heloc", "home equity", "line of credit",
        "credit card", "liability", "debt",
    )
    principal = _decimal_or_none(_value(row, "FinServ__PrincipalBalance__c"))
    return any(token in text for token in liability_tokens) or bool(principal and principal > 0)


def _account_value(row: dict, warehouse_row: dict | None = None) -> tuple[Decimal, str, str | None]:
    if warehouse_row:
        for field in ("Total_Account_Value", "Managed_Account_Value", "Closing_Value"):
            amount = _decimal_or_none(warehouse_row.get(field))
            if amount and amount > 0:
                return amount, "tho.Current_Account_Demographic", field
    for field in ("Total_Value__c", "FinServ__Balance__c", "FinServ__CurrentPostedBalance__c",
                  "Managed_Value__c", "FinServ__AverageBalance__c"):
        amount = _decimal_or_none(_value(row, field))
        if amount and amount > 0:
            return amount, "sfp.FinServ__FinancialAccount__c", field
    return Decimal("0"), "sfp.FinServ__FinancialAccount__c", None


def _liability_balance(row: dict) -> tuple[Decimal, str | None]:
    for field in ("FinServ__PrincipalBalance__c", "FinServ__Balance__c", "FinServ__LoanAmount__c",
                  "FinServ__CurrentPostedBalance__c"):
        amount = _decimal_or_none(_value(row, field))
        if amount and amount > 0:
            return amount, field
    return Decimal("0"), None


def _current_account_rows(session: Session, avhhid: Any) -> list[dict]:
    if not avhhid:
        return []
    rows = session.execute(text("""
        WITH ranked AS (
            SELECT [Account_Number],[Account_Name],[Account_Type],[Taxable],
                   [Total_Account_Value],[Managed_Account_Value],[Current_Cash],
                   [Financial_Account_SFID],[FinServ__PrimaryOwner__c],
                   [FinServ__JointOwner__c],[Date],
                   ROW_NUMBER() OVER (
                       PARTITION BY [Account_Number]
                       ORDER BY [Date] DESC
                   ) AS rn
            FROM [tho].[Current_Account_Demographic]
            WHERE [Primary_Household_ID]=:avhhid
              AND NULLIF(LTRIM(RTRIM(CONVERT(nvarchar(255), [Account_Number]))), '') IS NOT NULL
              AND ISNULL([Total_Account_Value], 0) <> 0
              AND ([Closed_Date] IS NULL OR [Closed_Date] > GETDATE())
        )
        SELECT *
        FROM ranked
        WHERE rn=1
    """), {"avhhid": avhhid}).mappings().all()
    return [dict(row) for row in rows]


def _holding_market_value(row: dict) -> Decimal:
    price = _decimal_or_none(row.get("Current_Price")) or Decimal("0")
    quantity = _decimal_or_none(row.get("Quantity")) or Decimal("0")
    value = price * quantity
    if value:
        return value
    total = _decimal_or_none(row.get("Total_Account_Value")) or Decimal("0")
    weight = _decimal_or_none(row.get("Weight")) or Decimal("0")
    if abs(weight) > 1:
        weight = weight / Decimal("100")
    return total * weight


def _current_holdings_by_account(session: Session, avhhid: Any) -> dict[str, list[Holding]]:
    if not avhhid:
        return {}
    rows = session.execute(text("""
        SELECT [Account_Number],[Account_Name],[Symbol],[CUSIP],
               [Security_Description],[Security_Type],[Asset_Class],[Sector],
               [Cost_Basis],[Current_Price],[Quantity],[Weight],
               [Total_Account_Value],[As_Of_Date]
        FROM [tho].[Account_Daily_Holdings]
        WHERE [avhhid]=:avhhid
          AND [Current_Date_Filter]=1
          AND NULLIF(LTRIM(RTRIM(CONVERT(nvarchar(255), [Account_Number]))), '') IS NOT NULL
        ORDER BY [Account_Number], [Asset_Class], [Security_Description], [Symbol]
    """), {"avhhid": avhhid}).mappings().all()
    grouped: dict[str, list[Holding]] = {}
    for raw in rows:
        row = dict(raw)
        account_number = str(row.get("Account_Number") or "")
        market_value = _holding_market_value(row)
        if not account_number or market_value == 0:
            continue
        holding = Holding(
            account_number=account_number,
            symbol=str(row["Symbol"]) if row.get("Symbol") else None,
            cusip=str(row["CUSIP"]) if row.get("CUSIP") else None,
            description=str(_value(row, "Security_Description", "Symbol", default="Holding")),
            security_type=str(row["Security_Type"]) if row.get("Security_Type") else None,
            asset_class=str(_value(row, "Asset_Class", default="Unclassified")),
            sector=str(row["Sector"]) if row.get("Sector") else None,
            quantity=_decimal_or_none(row.get("Quantity")) or Decimal("0"),
            current_price=_decimal_or_none(row.get("Current_Price")) or Decimal("0"),
            market_value=market_value,
            cost_basis=_decimal_or_none(row.get("Cost_Basis")),
            weight=_decimal_or_none(row.get("Weight")),
            as_of_date=_as_date(row.get("As_Of_Date")),
        )
        grouped.setdefault(account_number, []).append(holding)
    return grouped


def _owner_from_ids(row: dict, role_by_contact_id: dict[str, str], default: str = "client") -> str:
    primary_owner_id = str(_value(row, "FinServ__PrimaryOwner__c", default="") or "")
    joint_owner_id = str(_value(row, "FinServ__JointOwner__c", default="") or "")
    owner = role_by_contact_id.get(primary_owner_id, default)
    if joint_owner_id and joint_owner_id in role_by_contact_id:
        owner = "joint"
    return owner


def attach_current_holdings(session: Session, facts: Facts) -> Facts:
    """Return a facts copy with current Synapse holdings attached to accounts."""
    source_id = facts.metadata.get("source_id")
    avhhid = facts.metadata.get("household_avhhid")
    if facts.metadata.get("source") != "datawarehouse" or not source_id:
        return facts
    if all(account.holdings for account in facts.accounts):
        return facts
    if not avhhid:
        household_fact = session.execute(text(
            "SELECT TOP 1 [AVHHID] FROM [tho].[Current_Household_Fact] WHERE [HHID]=:id"),
            {"id": source_id}).mappings().first()
        avhhid = household_fact.get("AVHHID") if household_fact else None
    if not avhhid:
        return facts
    holdings_by_account = _current_holdings_by_account(session, avhhid)
    current_accounts = _current_account_rows(session, avhhid)
    current_by_sfid = {
        str(row.get("Financial_Account_SFID")): row for row in current_accounts
        if row.get("Financial_Account_SFID")
    }
    enriched = facts.model_copy(deep=True)
    for account in enriched.accounts:
        if account.holdings:
            continue
        account_number = (
            getattr(account, "external_account_number", None)
            or (current_by_sfid.get(str(getattr(account, "source_id", "") or "")) or {}).get("Account_Number")
            or (getattr(account, "source_id", None) if str(getattr(account, "source", "")) == "tho.Current_Account_Demographic" else None)
        )
        if account_number:
            account.holdings = holdings_by_account.get(str(account_number), [])
    return enriched


def import_household(session: Session, household_id: str) -> Facts:
    household = session.execute(text(
        "SELECT TOP 1 * FROM [sfp].[Account] WHERE [Id] = :id"), {"id": household_id}).mappings().first()
    if household is None:
        raise KeyError(household_id)
    contact_rows = session.execute(text(
        "SELECT c.*, r.[Roles] AS [Relationship_Roles] FROM [sfp].[Contact] c LEFT JOIN [sfp].[AccountContactRelation] r "
        "ON r.[ContactId]=c.[Id] WHERE c.[AccountId]=:id OR r.[AccountId]=:id"),
        {"id": household_id}).mappings().all()
    contacts = list({str(row.get("Id")): row for row in contact_rows}.values())
    demographic_rows = session.execute(text("""
        SELECT [contact_id],[dob],[retire_date],[primary_or_secondary],[employment_status]
        FROM [tho].[Contact_Demographic]
        WHERE [hh_id]=:id AND ISNULL([deceased_flag],0)=0
          AND ([current_noncurrent] IS NULL OR LOWER(CONVERT(varchar(255),[current_noncurrent])) LIKE '%current%')
    """), {"id": household_id}).mappings().all()
    contact_demographics = {str(row.get("contact_id")): dict(row) for row in demographic_rows}
    people, income, provenance, warnings = [], [], {}, []
    unverified_mc_inputs: set[str] = set()
    for index, raw in enumerate(contacts):
        row = dict(raw)
        demographic = contact_demographics.get(str(row.get("Id")), {})
        dob = _as_date(_value(row, "Birthdate")) or _as_date(demographic.get("dob"))
        if dob is None:
            dob = date(date.today().year - 50, 1, 1)
            warnings.append(f"Contact {row.get('Id')} has no birthdate; age 50 placeholder requires review")
        relationship_roles = str(_value(row, "Relationship_Roles", default="")).lower()
        warehouse_role = str(demographic.get("primary_or_secondary") or "").lower()
        if "primary" in relationship_roles or "primary" in warehouse_role:
            role = "client"
        elif "spouse" in relationship_roles or "secondary" in warehouse_role:
            role = "spouse"
        else:
            role = "client" if index == 0 else "spouse" if index == 1 else "other"
        if role == "client" and _as_date(_value(row, "Birthdate")) is None and not _as_date(demographic.get("dob")):
            unverified_mc_inputs.add("current_age")
        retire_date = _as_date(demographic.get("retire_date"))
        retirement_age = _age_on(dob, retire_date) if retire_date else 65
        if role == "client" and not retire_date:
            unverified_mc_inputs.add("retirement_age")
        person = Person(role=role, first_name=str(_value(row, "FirstName", default="")),
                        last_name=str(_value(row, "LastName", default="")), date_of_birth=dob,
                        retirement_age=retirement_age,
                        email=_value(row, "Email"), source_id=row.get("Id"))
        people.append(person)
        annual_income = _value(row, "FinServ__AnnualIncome__c")
        amount, estimated = _annual_income_estimate(annual_income)
        if amount:
            income.append(Flow(name=f"{person.first_name or role} reported annual income",
                               amount=amount, kind="salary", owner=role,
                               indexing=Indexing(mode="inflation"), source="sfp.Contact",
                               source_id=row.get("Id")))
            if estimated:
                warnings.append(
                    f"Contact {row.get('Id')} annual income was estimated from a warehouse income band; advisor review is required"
                )
        provenance[f"/people/{index}"] = {"source": "sfp.Contact", "source_id": row.get("Id"),
                                          "observed_at": str(row.get("LastModifiedDate") or "")}
    if not people:
        people = [Person(role="client", first_name=str(_value(dict(household), "Name", default="Client")),
                         date_of_birth=date(date.today().year - 50, 1, 1))]
        warnings.append("No household contacts were returned; placeholder client requires review")
        unverified_mc_inputs.update({"current_age", "retirement_age"})
    household_fact = session.execute(text(
        "SELECT TOP 1 [AVHHID],[Expected_Retirement_Date__c],[AUM] "
        "FROM [tho].[Current_Household_Fact] WHERE [HHID]=:id"),
        {"id": household_id}).mappings().first()
    avhhid = household_fact.get("AVHHID") if household_fact else None
    current_accounts = _current_account_rows(session, avhhid)
    holdings_by_account = _current_holdings_by_account(session, avhhid)
    current_by_sfid = {
        str(row.get("Financial_Account_SFID")): row for row in current_accounts
        if row.get("Financial_Account_SFID")
    }
    raw_accounts = session.execute(text(
        "SELECT * FROM [sfp].[FinServ__FinancialAccount__c] WHERE [FinServ__Household__c]=:id"),
        {"id": household_id}).mappings().all()
    role_by_contact_id = {str(getattr(person, "source_id", "")): person.role for person in people
                          if getattr(person, "source_id", None)}
    accounts, liabilities, imported_current_numbers = [], [], set()
    for raw in raw_accounts:
        row = dict(raw)
        account_id = str(row.get("Id") or "")
        warehouse_account = current_by_sfid.get(account_id)
        if warehouse_account and warehouse_account.get("Account_Number"):
            imported_current_numbers.add(str(warehouse_account["Account_Number"]))
        if _is_liability_account(row):
            balance, balance_field = _liability_balance(row)
            months = _decimal_or_none(_value(row, "FinServ__LoanTermMonths__c"))
            term_years = max(1, int((months or Decimal("360")) / Decimal("12")))
            raw_rate = _decimal_or_none(_value(row, "FinServ__InterestRate__c")) or Decimal("0")
            interest_rate = raw_rate / Decimal("100") if raw_rate > 1 else raw_rate
            liability = Mortgage(institution=str(_value(row, "Name", "FinServ__ServiceProvider__c", default="Lender")),
                                 current_balance=balance, interest_rate=interest_rate,
                                 term_years=term_years)
            liabilities.append(liability)
            provenance[f"/liabilities/{len(liabilities) - 1}"] = {
                "source": "sfp.FinServ__FinancialAccount__c",
                "source_id": row.get("Id"),
                "source_field": balance_field,
                "observed_at": str(row.get("LastModifiedDate") or ""),
            }
            continue
        account_type = _value(warehouse_account or {}, "Account_Type",
                              default=_value(row, "FinServ__FinancialAccountType__c", "Account_Type__c", default="taxable"))
        taxable = _value(warehouse_account or {}, "Taxable", default=_value(row, "Taxable__c", "Taxable1__c"))
        kind = _account_kind(account_type, taxable)
        value, value_source, value_field = _account_value(row, warehouse_account)
        raw_basis = _value(row, "Tax_Basis__c", "FinServ__TaxBasis__c")
        basis = Decimal(str(raw_basis)) if raw_basis is not None else value
        owner = _owner_from_ids(warehouse_account or row, role_by_contact_id)
        if raw_basis is None and kind == "taxable":
            warnings.append(f"Tax basis unavailable for account {row.get('Id')}; initialized to market value pending review")
        accounts.append(Account(name=str(_value(warehouse_account or {}, "Account_Name",
                                                default=_value(row, "Name", default="Financial Account"))),
                                kind=kind, value=value, tax_basis=basis, owner=owner,
                                apply_rmd=kind == "qualified",
                                holdings=holdings_by_account.get(str((warehouse_account or {}).get("Account_Number") or ""), []),
                                source=value_source, source_id=row.get("Id"),
                                external_account_number=(warehouse_account or {}).get("Account_Number")))
        provenance[f"/accounts/{len(accounts) - 1}"] = {
            "source": value_source,
            "source_id": row.get("Id"),
            "source_field": value_field,
            "observed_at": str((warehouse_account or {}).get("Date") or row.get("LastModifiedDate") or ""),
            "metadata_source": "sfp.FinServ__FinancialAccount__c",
            "holdings_source": "tho.Account_Daily_Holdings" if warehouse_account else None,
        }
    for row in current_accounts:
        account_number = str(row.get("Account_Number") or "")
        if not account_number or account_number in imported_current_numbers:
            continue
        value, value_source, value_field = _account_value({}, row)
        kind = _account_kind(row.get("Account_Type"), row.get("Taxable"))
        owner = _owner_from_ids(row, role_by_contact_id)
        accounts.append(Account(name=str(_value(row, "Account_Name", default="Financial Account")),
                                kind=kind, value=value, tax_basis=value, owner=owner,
                                apply_rmd=kind == "qualified",
                                holdings=holdings_by_account.get(account_number, []),
                                source=value_source, source_id=account_number,
                                external_account_number=account_number))
        provenance[f"/accounts/{len(accounts) - 1}"] = {
            "source": value_source,
            "source_id": account_number,
            "source_field": value_field,
            "observed_at": str(row.get("Date") or ""),
            "holdings_source": "tho.Account_Daily_Holdings",
        }
    if people and "retirement_age" in unverified_mc_inputs and household_fact:
        household_retirement_date = _as_date(household_fact.get("Expected_Retirement_Date__c"))
        if household_retirement_date:
            primary = next((person for person in people if person.role == "client"), people[0])
            primary.retirement_age = _age_on(primary.date_of_birth, household_retirement_date)
            unverified_mc_inputs.discard("retirement_age")
    if "retirement_age" in unverified_mc_inputs:
        warnings.append("No governed retirement date was found; age 65 is a placeholder requiring advisor review")
    if avhhid and not income:
        account_profile = session.execute(text("""
            SELECT TOP 1 [Client_Annual_Income_BD__c],[Date]
            FROM [tho].[Current_Account_Demographic]
            WHERE [Primary_Household_ID]=:avhhid
              AND NULLIF(LTRIM(RTRIM(CONVERT(nvarchar(255), [Client_Annual_Income_BD__c]))), '') IS NOT NULL
            ORDER BY [Date] DESC
        """), {"avhhid": avhhid}).mappings().first()
        if account_profile:
            amount, estimated = _annual_income_estimate(account_profile["Client_Annual_Income_BD__c"])
            if amount:
                income.append(Flow(name="Warehouse-reported annual household income",
                                   amount=amount, kind="salary",
                                   indexing=Indexing(mode="inflation"),
                                   source="tho.Current_Account_Demographic"))
                provenance["/income/0"] = {
                    "source": "tho.Current_Account_Demographic",
                    "source_field": "Client_Annual_Income_BD__c",
                    "observed_at": str(account_profile.get("Date") or ""),
                    "estimated_from_band": estimated,
                }
                if estimated:
                    warnings.append(
                        "Annual household income was estimated conservatively from a warehouse income band; advisor review is required"
                    )
            else:
                warnings.append(
                    "Warehouse annual-income category was not numeric or recognized; advisor-entered income is required"
                )
    review = session.execute(text(
        "SELECT TOP 1 [Id],[Monthly_Expenses__c],[LastModifiedDate] "
        "FROM [sfp].[Plan_Review__c] WHERE [Household__c]=:id ORDER BY [LastModifiedDate] DESC"),
        {"id": household_id}).mappings().first()
    expenses = []
    if review:
        monthly = _monthly_expense(review.get("Monthly_Expenses__c"))
        if monthly:
            expenses.append(Flow(name="Reported household living expenses", amount=monthly * 12,
                                 kind="living", indexing=Indexing(mode="inflation"),
                                 source="sfp.Plan_Review__c", source_id=review.get("Id")))
            provenance["/expenses/0"] = {"source": "sfp.Plan_Review__c",
                                          "source_id": review.get("Id"),
                                          "observed_at": str(review.get("LastModifiedDate") or "")}
        else:
            warnings.append("Latest Plan Review does not contain an unambiguous numeric monthly expense; Monte Carlo requires advisor-entered spending")
    else:
        warnings.append("No Plan Review expense input was found; Monte Carlo requires advisor-entered spending")
    facts = Facts(name=str(_value(dict(household), "Name", default="Household")), people=people,
                  accounts=accounts, liabilities=liabilities, income=income,
                  expenses=expenses, assumptions=Assumptions(),
                  metadata={"source": "datawarehouse", "source_id": household_id,
                            "household_avhhid": str(avhhid) if avhhid else None,
                            "provenance": provenance, "data_quality_warnings": warnings,
                            "unverified_monte_carlo_inputs": sorted(unverified_mc_inputs),
                            "requires_advisor_review": bool(warnings)})
    facts.metadata["monte_carlo_inputs"] = resolve_monte_carlo_inputs(session, facts)
    return facts
