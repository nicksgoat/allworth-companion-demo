"""End-to-end live check: seed household, publish plan, count warehouse rows."""
import json
import os
import sys
import urllib.request

import pyodbc

BASE = "http://127.0.0.1:5000"

HOUSEHOLD = {
    "name": "Demo - Carter Household",
    "people": [
        {"role": "client", "first_name": "Alex", "last_name": "Carter",
         "date_of_birth": "1962-04-15", "retirement_age": 66, "assumed_age_of_death": 92},
        {"role": "spouse", "first_name": "Jordan", "last_name": "Carter",
         "date_of_birth": "1964-09-02", "retirement_age": 65, "assumed_age_of_death": 94},
    ],
    "accounts": [
        {"kind": "taxable", "name": "Brokerage", "value": 1250000, "tax_basis": 800000,
         "growth_rate": "0.05", "income_yield": "0.02"},
        {"kind": "qualified", "name": "Rollover IRA", "owner": "client", "value": 1800000,
         "growth_rate": "0.05", "apply_rmd": True},
        {"kind": "roth", "name": "Roth IRA", "value": 150000, "growth_rate": "0.05"},
        {"kind": "cash", "name": "Cash", "value": 200000, "growth_rate": "0.01"},
    ],
    "income": [{"name": "Client Social Security", "kind": "social_security",
                "amount": 42000, "owner": "client",
                "starts": {"kind": "client_age", "value": 67},
                "ends": {"kind": "client_death"}}],
    "expenses": [{"name": "Living expenses", "kind": "living", "amount": 150000,
                  "required": True, "starts": {"kind": "immediately"},
                  "ends": {"kind": "second_death"}}],
    "assumptions": {"start_year": 2026, "inflation_rate": "0.03",
                    "tax_mode": "form_1040", "plan_end_age": 95},
}


def call(method: str, path: str, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(BASE + path, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read())


def main() -> int:
    created = call("POST", "/api/v1/households", HOUSEHOLD)
    print("created:", created["household_id"])
    scenarios = call("GET", f"/api/v1/households/{created['household_id']}/scenarios")
    scenario = next(s for s in scenarios["scenarios"] if s["name"] == "Proposed Plan")
    published = call("POST", f"/api/v1/scenarios/{scenario['id']}/publish",
                     {"advisor_note": "First live-warehouse publication"})
    print("published:", published["status"], published["publication_id"])

    server = os.environ["SYNAPSE_SERVER"]
    database = os.environ["SYNAPSE_DATABASE"]
    user = os.environ["SYNAPSE_USERNAME"].strip("'\"")
    password = os.environ["SYNAPSE_PASSWORD"].strip("'\"")
    cs = (f"DRIVER={{ODBC Driver 18 for SQL Server}};SERVER=tcp:{server},1433;"
          f"DATABASE={database};UID={user};PWD={password};Encrypt=yes")
    connection = pyodbc.connect(cs, autocommit=True)
    cursor = connection.cursor()
    for table in ("households", "facts_versions", "scenarios", "published_plans"):
        count = cursor.execute(
            f"SELECT COUNT(*) FROM [planengine].[{table}]").fetchone()[0]
        print(f"warehouse {table}: {count}")
    connection.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
