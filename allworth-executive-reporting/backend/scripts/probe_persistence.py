"""Probe: write one row through SynapsePlanningPersistence and read it back."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("AUTH_METHOD", "SqlPassword")

from planning.db import get_engine
from planning.services.synapse_planning_persistence import SynapsePlanningPersistence

persistence = SynapsePlanningPersistence(
    get_engine(),
    (os.getenv("SYNAPSE_PLANNING_SCHEMA") or "planengine").strip(),
    (os.getenv("AUTH_FIRM_ID") or "allworth").strip(),
)
print("engine url:", persistence.engine.url.render_as_string(hide_password=True)[:120])
persistence.save_household("probe-0000-0000-0000-000000000001", "Probe Household",
                           {"name": "Probe Household", "metadata": {}})
households, versions, scenarios = persistence.load()
print("load() households:", [(row.id, row.name) for row in households])
with persistence.engine.connect() as connection:
    from sqlalchemy import text
    count = connection.execute(text(
        "SELECT COUNT(*) FROM [planengine].[households]")).scalar()
    print("direct count:", count)
    db = connection.execute(text("SELECT DB_NAME()")).scalar()
    server = connection.execute(text("SELECT @@SERVERNAME")).scalar()
    print("connected to:", server, "/", db)
