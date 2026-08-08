"""Quick row-count check of the planengine schema (dev utility)."""
import os

import pyodbc

server = os.environ["SYNAPSE_SERVER"]
database = os.environ["SYNAPSE_DATABASE"]
user = os.environ["SYNAPSE_USERNAME"].strip("'\"")
password = os.environ["SYNAPSE_PASSWORD"].strip("'\"")
cs = (f"DRIVER={{ODBC Driver 18 for SQL Server}};SERVER=tcp:{server},1433;"
      f"DATABASE={database};UID={user};PWD={password};Encrypt=yes")
connection = pyodbc.connect(cs, autocommit=True)
cursor = connection.cursor()
# Migration 001 applies row-level security keyed to the firm_id session
# context; without it every SELECT is filtered to zero rows.
firm_id = (os.getenv("AUTH_FIRM_ID") or "allworth").strip()
cursor.execute("EXEC sys.sp_set_session_context @key=N'firm_id', @value=?", firm_id)
for table in ("households", "facts_versions", "scenarios", "portal_records",
              "audit_log", "published_plans"):
    count = cursor.execute(f"SELECT COUNT(*) FROM [planengine].[{table}]").fetchone()[0]
    print(f"{table}: {count}")
connection.close()
