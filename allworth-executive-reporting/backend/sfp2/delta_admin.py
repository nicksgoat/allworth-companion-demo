"""Admin helpers for SFP2 bronze Delta tables.

v1: list tables, return schema, run 3-bucket diff (handled in routes.py).
v2 (this file): real ALTER ADD COLUMNS / DROP COLUMNS via delta-rs, plus a
preview helper that returns the proposed Delta type and warnings without
mutating the table.
"""
from __future__ import annotations

import os
import re
from typing import Any, Optional

# Reuse the existing delta-rs setup so auth (SP / account key / MSI / az cli)
# stays in one place.
try:
    from delta_reader import (  # type: ignore
        DELTA_AVAILABLE,
        DELTA_IMPORT_ERROR,
        _build_storage_options,
    )
    from deltalake import DeltaTable  # type: ignore
except Exception as _e:  # pragma: no cover - env-dependent
    DELTA_AVAILABLE = False
    DELTA_IMPORT_ERROR = f"{type(_e).__name__}: {_e}"
    DeltaTable = None  # type: ignore

    def _build_storage_options() -> dict[str, str]:  # type: ignore
        return {}

try:
    import pyarrow as pa  # type: ignore
    PYARROW_AVAILABLE = True
except Exception as _e:  # pragma: no cover
    pa = None  # type: ignore
    PYARROW_AVAILABLE = False


ADLS_ACCOUNT_NAME = os.getenv('ADLS_ACCOUNT_NAME', 'dlallworthai')
ADLS_BRONZE_CONTAINER = os.getenv('ADLS_BRONZE_CONTAINER', 'bronze')
SFP2_PREFIX = os.getenv('SFP2_PREFIX', 'sfp2/')

# Defensive: column name must be a plain identifier. No spaces, no dots,
# no path-traversal-style characters.
_COLUMN_NAME_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')

# System / required columns that must never be dropped.
_PROTECTED_COLUMNS_LOWER = frozenset({
    'id', 'isdeleted', 'createddate', 'systemmodstamp',
})


# ---------------------------------------------------------------------------
# Salesforce -> Delta (pyarrow) type mapping
# ---------------------------------------------------------------------------
def _pa_string():
    return pa.string()


def _pa_bool():
    return pa.bool_()


def _pa_int64():
    return pa.int64()


def _pa_float64():
    return pa.float64()


def _pa_date32():
    return pa.date32()


def _pa_timestamp_utc():
    return pa.timestamp('us', tz='UTC')


# Strict whitelist. Maps Salesforce describe `field.type` to a callable that
# returns the pyarrow type. Anything not in this dict is rejected with 400.
SF_TO_DELTA_TYPE: dict[str, Any] = {
    'id': _pa_string,
    'string': _pa_string,
    'picklist': _pa_string,
    'multipicklist': _pa_string,
    'textarea': _pa_string,
    'phone': _pa_string,
    'email': _pa_string,
    'url': _pa_string,
    'encryptedstring': _pa_string,
    'reference': _pa_string,
    'time': _pa_string,        # SF describe gives "HH:MM:SS.sssZ" string
    'base64': _pa_string,
    'boolean': _pa_bool,
    'int': _pa_int64,
    'double': _pa_float64,
    'currency': _pa_float64,
    'percent': _pa_float64,
    'date': _pa_date32,
    'datetime': _pa_timestamp_utc,
}

# Salesforce types we explicitly refuse — these are compound or
# reference-y types that don't have a clean single-column representation.
SF_REJECTED_TYPES: frozenset[str] = frozenset({
    'address', 'location', 'anytype', 'complexvalue', 'combobox',
    'datacategorygroupreference', 'junctionidlist',
})

# Lossy / noteworthy mappings — included in `warnings` on preview.
_LOSSY_NOTES: dict[str, str] = {
    'time': "Salesforce 'time' is stored as an ISO string (HH:MM:SS.sssZ).",
    'reference': "Salesforce 'reference' lands as the related record's Id (string).",
    'base64': "Salesforce 'base64' content is stored as a string; binary blobs aren't decoded.",
    'multipicklist': "Salesforce 'multipicklist' values are stored as a single semicolon-delimited string.",
}


def _table_path(object_name: str) -> str:
    if not object_name or '/' in object_name or '..' in object_name:
        raise ValueError(f"Invalid SFP2 table name: {object_name!r}")
    return (
        f"abfss://{ADLS_BRONZE_CONTAINER}@{ADLS_ACCOUNT_NAME}"
        f".dfs.core.windows.net/{SFP2_PREFIX}{object_name}"
    )


def _ensure_available() -> None:
    if not DELTA_AVAILABLE:
        raise RuntimeError(
            f"deltalake package is not available: {DELTA_IMPORT_ERROR}"
        )
    if not PYARROW_AVAILABLE:
        raise RuntimeError("pyarrow is not available")


def _validate_column_name(column_name: str) -> None:
    if not _COLUMN_NAME_RE.match(column_name or ''):
        raise ValueError(
            f"Invalid column name: {column_name!r}. "
            "Must match ^[A-Za-z_][A-Za-z0-9_]*$"
        )


def _resolve_delta_type(sf_field: dict[str, Any]):
    """Return a pyarrow DataType for a Salesforce describe field.

    Raises ValueError if the SF type is not in the whitelist.
    """
    sf_type = (sf_field or {}).get('type')
    if not sf_type:
        raise ValueError("sf_field is missing 'type'")
    sf_type_lower = str(sf_type).lower()

    if sf_type_lower in SF_REJECTED_TYPES:
        raise ValueError(
            f"Unsupported Salesforce type {sf_type!r}: compound/reference types "
            "are not supported in SFP2 bronze tables."
        )

    factory = SF_TO_DELTA_TYPE.get(sf_type_lower)
    if factory is None:
        raise ValueError(
            f"Unsupported Salesforce type {sf_type!r}. "
            f"Allowed: {sorted(SF_TO_DELTA_TYPE)}."
        )

    # Decimals: when SF gives precision/scale on numeric fields, prefer a
    # decimal128 over a float to preserve exact value (currency, percent).
    if sf_type_lower in ('currency', 'percent', 'double'):
        precision = sf_field.get('precision')
        scale = sf_field.get('scale')
        # SF reports precision INCLUSIVE of scale (e.g. precision=18, scale=2
        # means up to 16 digits before the decimal). delta-rs / parquet caps
        # decimal128 precision at 38; clamp defensively.
        if (
            isinstance(precision, int)
            and isinstance(scale, int)
            and precision > 0
            and 0 <= scale <= precision
            and precision <= 38
        ):
            return pa.decimal128(precision, scale)

    return factory()


def _delta_type_label(arrow_type) -> str:
    """Stable string label for a pyarrow type, used in API responses."""
    return str(arrow_type)


def _ensure_field(name: str, arrow_type) -> Any:
    """Build a delta-rs ``Field`` for ``alter.add_columns(...)``.

    delta-rs's ``add_columns`` requires a ``deltalake.schema.Field`` (which is
    backed by ``deltalake._internal.Field``); a pyarrow Field fails the
    isinstance check with: ``argument 'fields': 'Field' object is not an
    instance of 'Field'``. delta-rs Field expects a delta-native type
    (``PrimitiveType('string')``, ``DecimalType(p, s)``, etc.), NOT a pyarrow
    type. Convert by inspecting the pyarrow type.
    """
    from deltalake.schema import Field as DeltaField  # type: ignore
    from deltalake.schema import PrimitiveType  # type: ignore

    delta_type: Any
    if pa.types.is_string(arrow_type):
        delta_type = PrimitiveType('string')
    elif pa.types.is_boolean(arrow_type):
        delta_type = PrimitiveType('boolean')
    elif pa.types.is_int8(arrow_type):
        delta_type = PrimitiveType('byte')
    elif pa.types.is_int16(arrow_type):
        delta_type = PrimitiveType('short')
    elif pa.types.is_int32(arrow_type):
        delta_type = PrimitiveType('integer')
    elif pa.types.is_int64(arrow_type):
        delta_type = PrimitiveType('long')
    elif pa.types.is_float32(arrow_type):
        delta_type = PrimitiveType('float')
    elif pa.types.is_float64(arrow_type):
        delta_type = PrimitiveType('double')
    elif pa.types.is_date32(arrow_type) or pa.types.is_date64(arrow_type):
        delta_type = PrimitiveType('date')
    elif pa.types.is_timestamp(arrow_type):
        # delta-rs uses 'timestamp' (with timezone) and 'timestamp_ntz'.
        tz = getattr(arrow_type, 'tz', None)
        delta_type = PrimitiveType('timestamp' if tz else 'timestamp_ntz')
    elif pa.types.is_decimal(arrow_type):
        try:
            from deltalake.schema import DecimalType  # type: ignore
            delta_type = DecimalType(arrow_type.precision, arrow_type.scale)
        except Exception:
            # Older delta-rs takes a string spec.
            delta_type = PrimitiveType(
                f'decimal({arrow_type.precision},{arrow_type.scale})'
            )
    elif pa.types.is_binary(arrow_type) or pa.types.is_large_binary(arrow_type):
        delta_type = PrimitiveType('binary')
    else:
        raise ValueError(
            f"No delta-rs type mapping for pyarrow type {arrow_type!r}"
        )

    return DeltaField(name, delta_type, nullable=True, metadata={})


# ---------------------------------------------------------------------------
# Read-only helpers
# ---------------------------------------------------------------------------
def list_tables() -> list[dict[str, Any]]:
    """List Delta tables under bronze/sfp2/."""
    _ensure_available()
    try:
        from azure.identity import DefaultAzureCredential  # type: ignore
        from azure.storage.filedatalake import DataLakeServiceClient  # type: ignore
    except Exception as e:
        raise RuntimeError(
            f"azure-storage-file-datalake not available: {type(e).__name__}: {e}. "
            "Add it to requirements.txt or set SFP2_TABLE_LIST manually."
        ) from e

    account_url = f"https://{ADLS_ACCOUNT_NAME}.dfs.core.windows.net"
    account_key = os.getenv('AZURE_STORAGE_ACCOUNT_KEY') or os.getenv('ADLS_ACCOUNT_KEY')
    if account_key:
        service = DataLakeServiceClient(account_url=account_url, credential=account_key)
    else:
        service = DataLakeServiceClient(
            account_url=account_url,
            credential=DefaultAzureCredential(),
        )
    fs = service.get_file_system_client(ADLS_BRONZE_CONTAINER)
    paths = fs.get_paths(path=SFP2_PREFIX.rstrip('/'), recursive=False)

    tables: list[dict[str, Any]] = []
    prefix = SFP2_PREFIX.rstrip('/') + '/'
    for p in paths:
        if not getattr(p, 'is_directory', False):
            continue
        full = p.name  # e.g. 'sfp2/Account'
        if not full.startswith(prefix):
            continue
        name = full[len(prefix):].strip('/')
        if not name:
            continue
        tables.append({'name': name})

    tables.sort(key=lambda r: r['name'].lower())
    return tables


def get_table_schema(object_name: str) -> list[dict[str, Any]]:
    """Return [{name, type, nullable}] for the given SFP2 Delta table."""
    _ensure_available()
    path = _table_path(object_name)
    dt = DeltaTable(path, storage_options=_build_storage_options())
    arrow_schema = dt.schema().to_arrow()
    return [
        {'name': f.name, 'type': str(f.type), 'nullable': f.nullable}
        for f in arrow_schema
    ]


def _open_table(object_name: str):
    _ensure_available()
    path = _table_path(object_name)
    return DeltaTable(path, storage_options=_build_storage_options())


def _existing_columns_lower(dt) -> dict[str, str]:
    """Map lowercase column name -> original-case name on the open Delta table."""
    arrow_schema = dt.schema().to_arrow()
    return {f.name.lower(): f.name for f in arrow_schema}


def _column_mapping_mode(dt) -> Optional[str]:
    """Return the value of `delta.columnMapping.mode` on the table, or None."""
    try:
        meta = dt.metadata()
        config = getattr(meta, 'configuration', None) or {}
        # delta-rs returns a dict of str->str.
        return config.get('delta.columnMapping.mode')
    except Exception:  # pragma: no cover - metadata variations
        return None


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------
def preview_add_column(
    object_name: str,
    column_name: str,
    sf_field: dict[str, Any],
) -> dict[str, Any]:
    """Compute the proposed Delta type + warnings without mutating the table."""
    _ensure_available()
    _validate_column_name(column_name)

    arrow_type = _resolve_delta_type(sf_field)
    delta_type_label = _delta_type_label(arrow_type)

    warnings: list[str] = []
    sf_type_lower = str(sf_field.get('type', '')).lower()
    if sf_type_lower in _LOSSY_NOTES:
        warnings.append(_LOSSY_NOTES[sf_type_lower])

    # Inspect the existing schema for collisions.
    try:
        dt = _open_table(object_name)
        existing_lower = _existing_columns_lower(dt)
    except Exception as e:
        # If we can't open the table, surface that as a warning rather than
        # blocking the preview — the commit will fail loudly later.
        warnings.append(f"Could not read existing schema: {type(e).__name__}: {e}")
        existing_lower = {}

    if column_name.lower() in existing_lower:
        existing = existing_lower[column_name.lower()]
        if existing == column_name:
            warnings.append(
                f"Column {column_name!r} already exists in {object_name}."
            )
        else:
            warnings.append(
                f"Case-only collision: column {existing!r} already exists in "
                f"{object_name}; adding {column_name!r} would conflict."
            )

    return {
        'success': True,
        'status': 200,
        'object': object_name,
        'column': column_name,
        'sf_type': sf_field.get('type'),
        'delta_type': delta_type_label,
        'nullable': True,
        'warnings': warnings,
    }


# ---------------------------------------------------------------------------
# Mutations
# ---------------------------------------------------------------------------
def _alter_add_columns(dt, fields: list[Any]) -> None:
    """Call delta-rs add_columns API across known versions.

    delta-rs >= 0.18 exposes `dt.alter.add_columns(...)`. Older versions used
    `dt.alter().add_columns(...)`. Fall back gracefully so the same image
    keeps working across upgrades.
    """
    alter = getattr(dt, 'alter', None)
    if alter is None:
        raise RuntimeError(
            "DeltaTable.alter is not available — upgrade `deltalake` to >=0.18."
        )
    if callable(alter):
        # Older API: alter() returns the alter helper.
        alter_obj = alter()
    else:
        alter_obj = alter
    add_fn = getattr(alter_obj, 'add_columns', None)
    if add_fn is None:
        raise RuntimeError(
            "DeltaTable.alter.add_columns is not available — upgrade `deltalake`."
        )
    add_fn(fields)


def _alter_drop_columns(dt, columns: list[str]) -> None:
    """delta-rs Python bindings (through 1.5.x) do NOT expose drop_columns.

    Kept as a stub to make the limitation discoverable in code review. The real
    drop happens in the Synapse `overnight_refresh` notebook via
    ``ALTER TABLE delta.\`abfss://...\` DROP COLUMN \`<col>\```.
    """
    raise RuntimeError(
        "delta-rs Python bindings do not expose drop_columns. "
        "Drops are queued via the audit log and executed during overnight refresh."
    )


def _arrow_to_spark_ddl(arrow_type) -> str:
    """Spark SQL type string for `ALTER TABLE ... ADD COLUMNS` in the worker."""
    if pa.types.is_string(arrow_type):
        return 'STRING'
    if pa.types.is_boolean(arrow_type):
        return 'BOOLEAN'
    if pa.types.is_int8(arrow_type):
        return 'TINYINT'
    if pa.types.is_int16(arrow_type):
        return 'SMALLINT'
    if pa.types.is_int32(arrow_type):
        return 'INT'
    if pa.types.is_int64(arrow_type):
        return 'BIGINT'
    if pa.types.is_float32(arrow_type):
        return 'FLOAT'
    if pa.types.is_float64(arrow_type):
        return 'DOUBLE'
    if pa.types.is_date32(arrow_type) or pa.types.is_date64(arrow_type):
        return 'DATE'
    if pa.types.is_timestamp(arrow_type):
        tz = getattr(arrow_type, 'tz', None)
        return 'TIMESTAMP' if tz else 'TIMESTAMP_NTZ'
    if pa.types.is_decimal(arrow_type):
        return f'DECIMAL({arrow_type.precision},{arrow_type.scale})'
    if pa.types.is_binary(arrow_type) or pa.types.is_large_binary(arrow_type):
        return 'BINARY'
    raise ValueError(f"No Spark DDL mapping for pyarrow type {arrow_type!r}")


def add_column(
    object_name: str,
    column_name: str,
    sf_field: dict[str, Any],
) -> dict[str, Any]:
    """Queue a column add for the next overnight refresh.

    Adds are deferred (not inline) for two reasons:
      1. delta-rs cannot write to tables that have `delta.columnMapping.mode`
         enabled (see PR delta-io/delta-rs#4424). Once the worker drops a
         column from a table, that table becomes unwritable by delta-rs.
      2. A new column is empty until the next overnight Salesforce ingestion
         backfills it, so there's no value in racing to mutate the schema mid-day.

    Returns 202-style ``queued: True`` on success. ``delta_type`` carries the
    Spark DDL string the worker will substitute into ``ALTER TABLE ... ADD
    COLUMNS (col TYPE)``.
    """
    _ensure_available()
    _validate_column_name(column_name)

    arrow_type = _resolve_delta_type(sf_field)
    delta_type_label = _delta_type_label(arrow_type)
    spark_ddl_type = _arrow_to_spark_ddl(arrow_type)

    dt = _open_table(object_name)
    existing_lower = _existing_columns_lower(dt)
    if column_name.lower() in existing_lower:
        return {
            'success': False,
            'status': 409,
            'error': (
                f"Column {existing_lower[column_name.lower()]!r} already exists "
                f"in {object_name}."
            ),
            'object': object_name,
            'column': column_name,
        }

    return {
        'success': True,
        'status': 202,
        'queued': True,
        'object': object_name,
        'column': column_name,
        'sf_type': sf_field.get('type'),
        'delta_type': delta_type_label,
        'spark_ddl_type': spark_ddl_type,
        'message': (
            "Add queued. The column will be added during the next overnight "
            "refresh, and Salesforce data for it will land in the same run."
        ),
    }



def drop_column(object_name: str, column_name: str) -> dict[str, Any]:
    """Queue a column drop for the next overnight refresh.

    delta-rs's Python bindings do not expose ``drop_columns`` (verified through
    deltalake 1.5.x — only ``add_columns``, ``add_constraint``, ``add_feature``,
    ``drop_constraint``, ``set_column_metadata``, and ``set_table_*`` are
    available). The actual ALTER runs in the Synapse `overnight_refresh`
    notebook against the same Delta table; this endpoint just validates the
    request and lets the route handler write a ``drop_queued`` audit row.

    Returns 202-style ``queued: True`` on success. Still returns 400/404 for
    bad inputs so the caller can short-circuit before writing audit noise.
    """
    _ensure_available()
    _validate_column_name(column_name)

    if column_name.lower() in _PROTECTED_COLUMNS_LOWER or column_name.startswith('_'):
        return {
            'success': False,
            'status': 400,
            'error': (
                f"Refusing to drop protected/system column {column_name!r}."
            ),
            'object': object_name,
            'column': column_name,
        }

    dt = _open_table(object_name)
    existing_lower = _existing_columns_lower(dt)
    actual = existing_lower.get(column_name.lower())
    if actual is None:
        return {
            'success': False,
            'status': 404,
            'error': f"Column {column_name!r} does not exist in {object_name}.",
            'object': object_name,
            'column': column_name,
        }

    return {
        'success': True,
        'status': 202,
        'queued': True,
        'object': object_name,
        'column': actual,
        'message': (
            "Drop queued. The column will be removed during the next overnight "
            "refresh (Synapse `overnight_refresh` notebook)."
        ),
    }

