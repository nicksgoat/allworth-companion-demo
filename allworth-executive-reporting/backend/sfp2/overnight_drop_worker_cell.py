# =============================================================================
# Synapse PySpark cell — process queued SFP2 column adds + drops
# =============================================================================
# Place this in the `overnight_refresh` notebook AFTER the SFP2 history-tables
# cell and BEFORE the Control Section / `publish_entire_folder_to_schema`.
#
# How it works:
#   1. Reads the audit Delta table at silver/logging/sfp2_schema_changes.
#   2. Finds rows where the latest action for (table, column) is `add_queued`
#      or `drop_queued` (i.e. no later terminal row has overridden it).
#   3. For each pending add:
#        - Runs ALTER TABLE delta.`abfss://...` ADD COLUMNS (col TYPE).
#          The Spark DDL TYPE is read from the audit row's `delta_type`.
#        - Appends a follow-up audit row (action='add', success=True/False).
#   4. For each pending drop:
#        - Auto-enables delta.columnMapping.mode='name' if missing.
#        - Runs ALTER TABLE delta.`abfss://...` DROP COLUMN `<col>`.
#        - Appends a follow-up audit row (action='drop', success=True/False).
#
# Adds are processed BEFORE drops so a same-night add+drop on the same column
# would no-op cleanly (drop would skip with "no longer exists" — fine).
# Failures on one column do NOT abort the cell — each column is independent.
# =============================================================================

from datetime import datetime, timezone
from pyspark.sql import Row
from pyspark.sql.functions import col, max as spark_max
from pyspark.sql.types import (
    StructType, StructField, StringType, TimestampType, BooleanType
)

# --- config (mirrors backend/sfp2/audit.py) -----------------------------------
ADLS_ACCOUNT = "dlallworthai"
BRONZE_CONTAINER = "bronze"
SFP2_PREFIX = "sfp2"
AUDIT_PATH = (
    f"abfss://silver@{ADLS_ACCOUNT}.dfs.core.windows.net/"
    f"logging/sfp2_schema_changes"
)

ACTION_ADD = "add"
ACTION_ADD_QUEUED = "add_queued"
ACTION_ADD_CANCELED = "add_canceled"
ACTION_DROP = "drop"
ACTION_DROP_QUEUED = "drop_queued"
ACTION_DROP_CANCELED = "drop_canceled"

WORKER_USER = "overnight_worker"


def _bronze_path(object_name: str) -> str:
    return (
        f"abfss://{BRONZE_CONTAINER}@{ADLS_ACCOUNT}.dfs.core.windows.net/"
        f"{SFP2_PREFIX}/{object_name}"
    )


def _audit_schema():
    # MUST stay in sync with backend/sfp2/audit.py::_build_schema.
    return StructType([
        StructField("ts", TimestampType(), False),
        StructField("action", StringType(), False),
        StructField("table", StringType(), False),
        StructField("column", StringType(), False),
        StructField("sf_type", StringType(), True),
        StructField("delta_type", StringType(), True),
        StructField("user_email", StringType(), True),
        StructField("success", BooleanType(), False),
        StructField("error", StringType(), True),
        StructField("request_id", StringType(), True),
        StructField("app_version", StringType(), True),
    ])


def _append_audit(action: str, table: str, column: str, success: bool,
                  error, request_id: str, delta_type=None):
    df = spark.createDataFrame(
        [Row(
            ts=datetime.now(timezone.utc),
            action=action,
            table=table,
            column=column,
            sf_type=None,
            delta_type=delta_type,
            user_email=WORKER_USER,
            success=bool(success),
            error=error,
            request_id=request_id,
            app_version="overnight",
        )],
        schema=_audit_schema(),
    )
    (df.write.format("delta").mode("append")
        .option("mergeSchema", "true")
        .save(AUDIT_PATH))


def _find_pending(action_queued: str):
    """Return list of (table, column, delta_type) where the latest action is
    `action_queued` (i.e. an open queued request)."""
    audit_df = spark.read.format("delta").load(AUDIT_PATH)
    latest = (audit_df
        .groupBy("table", "column")
        .agg(spark_max("ts").alias("max_ts")))
    joined = (audit_df.alias("a")
        .join(latest.alias("l"),
              (col("a.table") == col("l.table")) &
              (col("a.column") == col("l.column")) &
              (col("a.ts") == col("l.max_ts")))
        .select("a.table", "a.column", "a.action", "a.success", "a.delta_type"))
    pending = joined.filter(col("action") == action_queued).filter(col("success") == True)
    return [(r["table"], r["column"], r["delta_type"]) for r in pending.collect()]


def _ensure_column_mapping(table_path: str) -> None:
    """Set delta.columnMapping.mode='name' if not already enabled."""
    spark.sql(
        f"ALTER TABLE delta.`{table_path}` SET TBLPROPERTIES ("
        f"'delta.columnMapping.mode' = 'name', "
        f"'delta.minReaderVersion' = '2', "
        f"'delta.minWriterVersion' = '5')"
    )


def _column_exists(table_path: str, column: str) -> bool:
    cols = spark.read.format("delta").load(table_path).columns
    return column in cols


def _process_pending_adds(request_id: str):
    summary = []
    try:
        pending = _find_pending(ACTION_ADD_QUEUED)
    except Exception as e:
        print(f"[sfp2-worker][adds] ERROR reading audit table: {type(e).__name__}: {e}")
        return summary

    if not pending:
        print("[sfp2-worker][adds] No pending adds.")
        return summary

    print(f"[sfp2-worker][adds] Found {len(pending)} pending add(s).")
    for table, column, ddl_type in pending:
        path = _bronze_path(table)
        try:
            if _column_exists(path, column):
                msg = f"Column {column!r} already exists on {table}"
                print(f"[sfp2-worker][adds][SKIP] {msg}")
                _append_audit(ACTION_ADD, table, column, success=False,
                              error=msg, request_id=request_id, delta_type=ddl_type)
                summary.append((table, column, "add_skipped", msg))
                continue
            if not ddl_type:
                msg = "audit row has no delta_type (Spark DDL); cannot ADD COLUMN"
                print(f"[sfp2-worker][adds][FAIL] {table}.{column}: {msg}")
                _append_audit(ACTION_ADD, table, column, success=False,
                              error=msg, request_id=request_id)
                summary.append((table, column, "add_failed", msg))
                continue

            spark.sql(
                f"ALTER TABLE delta.`{path}` ADD COLUMNS (`{column}` {ddl_type})"
            )
            _append_audit(ACTION_ADD, table, column, success=True,
                          error=None, request_id=request_id, delta_type=ddl_type)
            print(f"[sfp2-worker][adds][OK]   added {table}.{column} {ddl_type}")
            summary.append((table, column, "added", None))
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
            print(f"[sfp2-worker][adds][FAIL] {table}.{column}: {err}")
            try:
                _append_audit(ACTION_ADD, table, column, success=False,
                              error=err, request_id=request_id, delta_type=ddl_type)
            except Exception as audit_err:  # pragma: no cover
                print(f"[sfp2-worker][adds][FAIL] audit append failed: {audit_err}")
            summary.append((table, column, "add_failed", err))
    return summary


def _process_pending_drops(request_id: str):
    summary = []
    try:
        pending = _find_pending(ACTION_DROP_QUEUED)
    except Exception as e:
        print(f"[sfp2-worker][drops] ERROR reading audit table: {type(e).__name__}: {e}")
        return summary

    if not pending:
        print("[sfp2-worker][drops] No pending drops.")
        return summary

    print(f"[sfp2-worker][drops] Found {len(pending)} pending drop(s).")
    for table, column, _ddl in pending:
        path = _bronze_path(table)
        try:
            if not _column_exists(path, column):
                msg = f"Column {column!r} no longer exists on {table}"
                print(f"[sfp2-worker][drops][SKIP] {msg}")
                _append_audit(ACTION_DROP, table, column, success=False,
                              error=msg, request_id=request_id)
                summary.append((table, column, "drop_skipped", msg))
                continue

            _ensure_column_mapping(path)
            spark.sql(f"ALTER TABLE delta.`{path}` DROP COLUMN `{column}`")
            _append_audit(ACTION_DROP, table, column, success=True,
                          error=None, request_id=request_id)
            print(f"[sfp2-worker][drops][OK]   dropped {table}.{column}")
            summary.append((table, column, "dropped", None))
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
            print(f"[sfp2-worker][drops][FAIL] {table}.{column}: {err}")
            try:
                _append_audit(ACTION_DROP, table, column, success=False,
                              error=err, request_id=request_id)
            except Exception as audit_err:  # pragma: no cover
                print(f"[sfp2-worker][drops][FAIL] audit append failed: {audit_err}")
            summary.append((table, column, "drop_failed", err))
    return summary


def process_pending_schema_changes():
    request_id = f"overnight-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    # Adds first so a same-night add+drop on the same column is a no-op overall.
    add_summary = _process_pending_adds(request_id)
    drop_summary = _process_pending_drops(request_id)

    print("\n[sfp2-worker] Summary:")
    for row in add_summary + drop_summary:
        print(f"  {row}")


process_pending_schema_changes()
