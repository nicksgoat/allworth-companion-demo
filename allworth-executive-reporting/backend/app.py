from flask import Flask, jsonify, request
from flask_cors import CORS
import pandas as pd
import pyodbc
from datetime import datetime
from dateutil.relativedelta import relativedelta
from threading import Lock
import time
import os
from pathlib import Path
from tool_manifest import analytics_routes

# Load .env file for local development (ignored if file doesn't exist)
try:
    from dotenv import load_dotenv
    # Load .env from the same directory as app.py
    env_path = Path(__file__).parent / '.env'
    load_dotenv(env_path)
except ImportError:
    pass  # python-dotenv not installed, use environment variables directly

# Optional: gzip compression for API responses
try:
    from flask_compress import Compress
except ImportError:
    Compress = None

# Optional: ADLS Gen2 Delta Lake reader (isolated from Synapse code path).
# A failure here must not prevent the Synapse endpoints from booting.
try:
    from delta_reader import (
        read_delta_table,
        get_schema as get_delta_schema,
        TRANSFORMATION_LOG_PATH,
        DELTA_AVAILABLE,
        DELTA_IMPORT_ERROR,
    )
    print(f"🪵 Delta reader loaded (available={DELTA_AVAILABLE}) path={TRANSFORMATION_LOG_PATH}")
except Exception as _delta_e:  # pragma: no cover - defensive
    DELTA_AVAILABLE = False
    DELTA_IMPORT_ERROR = f"{type(_delta_e).__name__}: {_delta_e}"
    TRANSFORMATION_LOG_PATH = ''
    read_delta_table = None  # type: ignore
    get_delta_schema = None  # type: ignore
    print(f"⚠️  Delta reader unavailable: {DELTA_IMPORT_ERROR}")

app = Flask(__name__)
CORS(app)  # Enable CORS for React frontend

# JWT validation middleware — must be installed BEFORE any blueprint registers
# its own before_request hooks so the auth check runs first.  Configured via
# ENTRA_TENANT_ID + ENTRA_CLIENT_ID env vars; bypassed entirely if either is
# unset (logged as a warning) or if AUTH_DISABLE=1 (local dev).
try:
    from auth_middleware import install as install_auth_middleware
    install_auth_middleware(app)
except Exception as _auth_e:  # pragma: no cover - defensive
    print(f"⚠️  auth_middleware unavailable: {type(_auth_e).__name__}: {_auth_e}")

# Jarvis — documentation encyclopedia mounted at /jarvis
# Read-side: serves an HTML page + JSON API backed by YAMLs in backend/jarvis/knowledge/.
# Write-side: the in-app editor writes YAMLs to the same dir and appends to .jarvis-history/events.jsonl.
from jarvis.routes import bp as jarvis_bp
app.register_blueprint(jarvis_bp, url_prefix="/jarvis")

# Data Catalog — searchable, visual dictionary of the tho warehouse mounted at
# /catalog. Read-side serves an HTML page + JSON API backed by structured YAMLs
# in backend/catalog/data/ (generated from the ThoughtSpot TML repo). Write-side
# stores curated descriptions in data/overlays/ so they survive regeneration.
try:
    from catalog.routes import bp as catalog_bp
    app.register_blueprint(catalog_bp, url_prefix="/catalog")
    print("📚 Data Catalog blueprint registered at /catalog")
except Exception as _catalog_e:  # pragma: no cover - defensive
    print(f"⚠️  Data Catalog blueprint unavailable: {type(_catalog_e).__name__}: {_catalog_e}")

# Home — team hub / landing page mounted at /home
from home.routes import bp as home_bp
app.register_blueprint(home_bp, url_prefix="/home")

# SFP2 schema manager — admin tool to diff bronze Delta tables vs live Salesforce
# describe(). Defensive import: a missing wheel must not break the rest of the
# Flask app (mirrors the delta_reader pattern below).
try:
    from sfp2.routes import bp as sfp2_bp
    app.register_blueprint(sfp2_bp, url_prefix="/api/sfp2")
    print("🪪 SFP2 schema manager blueprint registered at /api/sfp2")
except Exception as _sfp2_e:  # pragma: no cover - defensive
    print(f"⚠️  SFP2 blueprint unavailable: {type(_sfp2_e).__name__}: {_sfp2_e}")

# Rep Codes — editable lookup table backed by tho.repcodes in Synapse.
try:
    from repcodes.routes import bp as repcodes_bp
    app.register_blueprint(repcodes_bp, url_prefix="/api/repcodes")
    print("📇 Rep codes blueprint registered at /api/repcodes")
except Exception as _rc_e:  # pragma: no cover - defensive
    print(f"⚠️  Rep codes blueprint unavailable: {type(_rc_e).__name__}: {_rc_e}")

# NFBC Adjustment Console — investigate households, write NFBC flow adjustments,
# and re-run the rollforward SPs. Write-capable; reuses get_database_connection
# and the global JWT middleware. Defensive import so a missing dep (e.g. PyYAML
# for the semantic-layer registry) can't break the rest of the app.
try:
    from nfbc.routes import bp as nfbc_bp
    app.register_blueprint(nfbc_bp, url_prefix="/api/nfbc")
    print("🧮 NFBC console blueprint registered at /api/nfbc")
except Exception as _nfbc_e:  # pragma: no cover - defensive
    print(f"⚠️  NFBC blueprint unavailable: {type(_nfbc_e).__name__}: {_nfbc_e}")

# Admin console — manage users, groups and tool-access grants. Group access
# cascades to members. Reuses the global JWT middleware; state is persisted to
# a JSON file in backend/admin/.admin-state/.
try:
    from admin.routes import bp as admin_bp
    app.register_blueprint(admin_bp, url_prefix="/api/admin")
    from admin import store as _admin_store
    _admin_store.init_persistence()
    print("🔐 Admin console blueprint registered at /api/admin")
except Exception as _admin_e:  # pragma: no cover - defensive
    print(f"⚠️  Admin blueprint unavailable: {type(_admin_e).__name__}: {_admin_e}")

# Workspace — assignment-aware identity and exact cross-tool household context.
try:
    from workspace.routes import bp as workspace_bp
    app.register_blueprint(workspace_bp, url_prefix="/api/workspace")
    print("🧭 Connected workspace blueprint registered at /api/workspace")
except Exception as _workspace_e:  # pragma: no cover - defensive
    print(f"⚠️  Workspace blueprint unavailable: {type(_workspace_e).__name__}: {_workspace_e}")

# SFP2 notebook reference index — builds once at app startup. Annotates the
# /api/sfp2/diff response with the notebooks that reference each column so the
# UI can flag still-in-use columns before someone removes them.
try:
    from sfp2 import notebook_refs as _sfp2_notebook_refs
    _sfp2_notebook_refs.init()
    _sfp2_stats = _sfp2_notebook_refs.stats()
    print(
        f"📓 SFP2 notebook index: {_sfp2_stats['notebooks']} notebooks, "
        f"{_sfp2_stats['tokens']} tokens"
    )
except Exception as _sfp2_idx_e:  # pragma: no cover - defensive
    print(
        f"⚠️  SFP2 notebook index unavailable: "
        f"{type(_sfp2_idx_e).__name__}: {_sfp2_idx_e}"
    )

# Fee Calculator — tiered fee computation + household AUM lookup
try:
    from fee_calculator.routes import bp as fee_calc_bp
    app.register_blueprint(fee_calc_bp, url_prefix="/fee-calculator")
    print("💰 Fee Calculator blueprint registered at /fee-calculator")
except Exception as _fee_e:  # pragma: no cover - defensive
    print(f"⚠️  Fee Calculator blueprint unavailable: {type(_fee_e).__name__}: {_fee_e}")

# Pipeline Review — weekly prospect focus list + snapshot history
try:
    from pipeline_review.routes import bp as pipeline_review_bp
    app.register_blueprint(pipeline_review_bp, url_prefix="/pipeline-review")
    print("📈 Pipeline Review blueprint registered at /pipeline-review")
except Exception as _pr_e:  # pragma: no cover - defensive
    print(f"⚠️  Pipeline Review blueprint unavailable: {type(_pr_e).__name__}: {_pr_e}")

# Executive Brief — CEO inbox operating system (mock mode; Graph/Claude later)
try:
    from brief.routes import bp as brief_bp
    app.register_blueprint(brief_bp, url_prefix="/brief")
    print("📬 Executive Brief blueprint registered at /brief")
except Exception as _brief_e:  # pragma: no cover - defensive
    print(f"⚠️  Executive Brief blueprint unavailable: {type(_brief_e).__name__}: {_brief_e}")

# Mailer — reusable email send API for pipelines/automation (app-only Graph)
try:
    from mailer.routes import bp as mailer_bp
    app.register_blueprint(mailer_bp, url_prefix="/mailer")
    print("📨 Mailer blueprint registered at /mailer")
except Exception as _mailer_e:  # pragma: no cover - defensive
    print(f"⚠️  Mailer blueprint unavailable: {type(_mailer_e).__name__}: {_mailer_e}")

# Executive Report — CEO flows + NCNM forecast + GPT-4.1 executive summary
try:
    from executive_report.routes import bp as executive_report_bp
    app.register_blueprint(executive_report_bp, url_prefix="/executive-report")
    print("📊 Executive Report blueprint registered at /executive-report")
except Exception as _exec_e:  # pragma: no cover - defensive
    print(f"⚠️  Executive Report blueprint unavailable: {type(_exec_e).__name__}: {_exec_e}")

# CRM — read-only Client 360 + Advisor book views over the Synapse warehouse.
try:
    from crm.routes import bp as crm_bp
    app.register_blueprint(crm_bp, url_prefix="/api/crm")
    print("👥 CRM blueprint registered at /api/crm")
except Exception as _crm_e:  # pragma: no cover - defensive
    print(f"⚠️  CRM blueprint unavailable: {type(_crm_e).__name__}: {_crm_e}")

# File Explorer — download (and later upload) data-lake files. Reuses the shared
# JWT middleware; Delta tables are surfaced from ADLS Gen2 and shared per user or
# per Admin-console group.
try:
    from file_explorer.routes import bp as file_explorer_bp
    app.register_blueprint(file_explorer_bp, url_prefix="/api/file-explorer")
    print("🗂️  File Explorer blueprint registered at /api/file-explorer")
except Exception as _fe_e:  # pragma: no cover - defensive
    print(f"⚠️  File Explorer blueprint unavailable: {type(_fe_e).__name__}: {_fe_e}")

# Investments — Bond Analyzer workspaces. Blueprints own their /api prefixes.
try:
    from investments.routers import account_analysis as _inv_account_analysis
    from investments.routers import bond_ladder as _inv_bond_ladder
    from investments.routers import dashboard as _inv_dashboard
    from investments.routers import sample_portfolio as _inv_sample_portfolio
    from investments.routers import upload as _inv_upload
    for _inv_mod in (
        _inv_account_analysis, _inv_bond_ladder, _inv_dashboard,
        _inv_sample_portfolio, _inv_upload,
    ):
        app.register_blueprint(_inv_mod.bp)
    print("📈 Investments blueprints registered (bond analyzer)")
    from investments import warmup as _inv_warmup
    _inv_warmup.start()
except Exception as _inv_e:  # pragma: no cover - defensive
    print(f"⚠️  Investments blueprints unavailable: {type(_inv_e).__name__}: {_inv_e}")

# Advisor Mailer — workbook preview and deliberate Microsoft Graph batch send.
try:
    from email_batch.routes import bp as email_batch_bp
    app.register_blueprint(email_batch_bp)
    print("📧 Advisor Mailer blueprint registered at /api/email-batch")
except Exception as _eb_e:  # pragma: no cover - defensive
    print(f"⚠️  Advisor Mailer blueprint unavailable: {type(_eb_e).__name__}: {_eb_e}")

# Financial Planning and its advisor cockpit.
try:
    from planning.routes import bp as planning_bp
    app.register_blueprint(planning_bp, url_prefix="/api/v1")
    print("📐 Financial Planning blueprint registered at /api/v1")
except Exception as _plan_e:  # pragma: no cover - defensive
    print(f"⚠️  Financial Planning blueprint unavailable: {type(_plan_e).__name__}: {_plan_e}")

try:
    from avantos.routes import bp as avantos_bp
    app.register_blueprint(avantos_bp, url_prefix="/api/avantos")
    print("Avantos cockpit registered at /api/avantos")
except Exception as _av_e:  # pragma: no cover - defensive
    print(f"Avantos blueprint unavailable: {type(_av_e).__name__}: {_av_e}")

# Tax-aware, proposal-only what-if rebalancing; never submits trades.
try:
    from rebalancer.routes import bp as rebalancer_bp
    app.register_blueprint(rebalancer_bp, url_prefix="/api/rebalancer")
    print("Mock Rebalancer registered at /api/rebalancer")
except Exception as _rb_e:  # pragma: no cover - defensive
    print(f"Rebalancer blueprint unavailable: {type(_rb_e).__name__}: {_rb_e}")


@app.after_request
def set_iframe_headers(response):
    """Allow embedding in ThoughtSpot liveboards via iframe."""
    response.headers['Content-Security-Policy'] = (
        "frame-ancestors 'self' https://*.thoughtspot.cloud https://*.thoughtspot.com"
    )
    return response

# Enable gzip compression on API responses (typically 70-80% size reduction for JSON)
if Compress is not None:
    app.config['COMPRESS_ALGORITHM'] = 'gzip'
    app.config['COMPRESS_MIN_SIZE'] = 500
    Compress(app)

# ---------------------------------------------------------------------------
# Server-side response cache
# Executive dashboard data doesn't change second-to-second.  A short TTL
# avoids redundant Synapse round-trips when users refresh or multiple users
# hit the page simultaneously.
# ---------------------------------------------------------------------------
CACHE_TTL_SECONDS = int(os.getenv('CACHE_TTL_SECONDS', '300'))  # default 5 min
_response_cache: dict = {}   # key -> (timestamp, response_data)
_cache_lock = Lock()


def _get_cached(key: str):
    """Return cached response data if still fresh, else None."""
    with _cache_lock:
        entry = _response_cache.get(key)
        if entry is None:
            return None
        cached_at, data = entry
        if time.time() - cached_at > CACHE_TTL_SECONDS:
            del _response_cache[key]
            return None
        return data


def _set_cached(key: str, data):
    """Store response data in cache."""
    with _cache_lock:
        _response_cache[key] = (time.time(), data)


def _invalidate_cache():
    """Clear all cached data (useful for admin/debug)."""
    with _cache_lock:
        _response_cache.clear()

# Database connection configuration
SERVER = os.getenv('SYNAPSE_SERVER', 'allworthsynapse.sql.azuresynapse.net')
DATABASE = os.getenv('SYNAPSE_DATABASE', 'DataWarehouse')
DRIVER = os.getenv('ODBC_DRIVER', '{ODBC Driver 18 for SQL Server}')
AUTH_METHOD = os.getenv('AUTH_METHOD', 'ActiveDirectoryInteractive')

# Per-query timeout (seconds). Bounds both the liveness check and real queries
# so a half-dead pooled socket fails fast and reconnects instead of hanging
# until the App Service gateway times out (~230s) and returns a 504.
QUERY_TIMEOUT = int(os.getenv('SYNAPSE_QUERY_TIMEOUT', '30'))

# Log current ODBC driver being used
print(f"🔧 Using ODBC Driver: {DRIVER}")

# Connection pool to reuse authenticated connection
_connection_pool = {'conn': None, 'lock': Lock()}

# Mapping from database metric names to frontend metric names
METRIC_MAP = {
    '1 - Leads': 'Leads',
    '2 - Appointments Completed': 'Appointments',
    '3 - New Clients': 'Clients',
    '4 - NCNM': 'NCNM'
}

# Mapping from database channel names to frontend channel names (lowercase keys for case-insensitive matching)
CHANNEL_MAP = {
    'advisor driven': 'Advisor Enabled',
    'advisor recruiting': 'Advisor Enabled',
    'referral': 'Advisor Enabled',
    'promoter': 'Advisor Enabled',
    'self-sourced': 'Advisor Enabled',
    'other': 'Advisor Enabled',
    'beneficiary': 'Advisor Enabled',
    'media driven': 'Media',
    'paid leads': 'Paid Leads',
    'crp': 'CRP',
    'fidelity': 'CRP',
    'schwab': 'CRP',
    'total': 'Total',
    'radio': 'Media',
    'other media': 'Media',
    'target market': 'Media'
}

def get_database_connection():
    """
    Establish connection to Azure Synapse using configured authentication method
    Reuses existing connection to avoid repeated auth prompts
    """
    with _connection_pool['lock']:
        # Try to reuse existing connection
        if _connection_pool['conn'] is not None:
            try:
                # Test if connection is still alive. conn.timeout (set below when
                # the connection was created) bounds this so a dead socket raises
                # quickly instead of blocking until the gateway 504s.
                cursor = _connection_pool['conn'].cursor()
                cursor.execute("SELECT 1")
                cursor.close()
                print("♻️  Reusing existing connection")
                return _connection_pool['conn']
            except:
                print("🔄 Previous connection expired, reconnecting...")
                _connection_pool['conn'] = None
        
        # Build connection string based on auth method
        print(f"🔐 Authenticating with method: {AUTH_METHOD}")
        
        if AUTH_METHOD == 'ServicePrincipal':
            client_id = os.getenv('AZURE_CLIENT_ID')
            client_secret = os.getenv('AZURE_CLIENT_SECRET')
            tenant_id = os.getenv('AZURE_TENANT_ID')
            
            if not all([client_id, client_secret, tenant_id]):
                raise ValueError("Service Principal credentials not configured. Set AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, and AZURE_TENANT_ID")
            
            conn_str = (
                f'DRIVER={DRIVER};'
                f'SERVER={SERVER};'
                f'DATABASE={DATABASE};'
                f'Authentication=ActiveDirectoryServicePrincipal;'
                f'UID={client_id}@{tenant_id};'
                f'PWD={client_secret};'
                f'Encrypt=yes;'
                f'TrustServerCertificate=no'
            )
            
        elif AUTH_METHOD == 'SqlPassword':
            username = os.getenv('SYNAPSE_USERNAME')
            password = os.getenv('SYNAPSE_PASSWORD')
            
            if not all([username, password]):
                raise ValueError("SQL credentials not configured. Set SYNAPSE_USERNAME and SYNAPSE_PASSWORD")
            
            conn_str = (
                f'DRIVER={DRIVER};'
                f'SERVER={SERVER};'
                f'DATABASE={DATABASE};'
                f'UID={username};'
                f'PWD={password};'
                f'Encrypt=yes;'
                f'TrustServerCertificate=no'
            )
            
        elif AUTH_METHOD == 'ActiveDirectoryInteractive':
            print("⚠️  Interactive auth requires browser - only works locally, not in containers")
            conn_str = (
                f'DRIVER={DRIVER};'
                f'SERVER={SERVER};'
                f'DATABASE={DATABASE};'
                f'Authentication=ActiveDirectoryInteractive;'
                f'Encrypt=yes;'
                f'TrustServerCertificate=no'
            )
        else:
            raise ValueError(f"Unknown AUTH_METHOD: {AUTH_METHOD}. Use ServicePrincipal, SqlPassword, or ActiveDirectoryInteractive")
        
        conn = pyodbc.connect(conn_str, timeout=30)
        # Bound every query on this connection (including the reuse liveness
        # check above) so a stale/half-open socket can't hang a request.
        conn.timeout = QUERY_TIMEOUT
        _connection_pool['conn'] = conn
        print("✅ Authenticated! Connection will be reused for subsequent requests")
        return conn


@app.route('/api/kpi-metrics', methods=['GET'])
def get_kpi_metrics():
    """Fetch KPI metrics from Synapse"""
    cached = _get_cached('kpi-metrics')
    if cached is not None:
        print("⚡ Returning cached kpi-metrics")
        return jsonify(cached)

    try:
        print("=" * 60)
        print("📊 Attempting to connect to Azure Synapse...")
        print(f"Server: {SERVER}")
        print(f"Database: {DATABASE}")
        print("=" * 60)
        
        conn = get_database_connection()
        print("✅ Connected to Synapse successfully!")
        
        # Get current month and calculate days elapsed for pro-rating
        today = datetime.now()
        current_month_start = today.replace(day=1)
        days_in_month = (current_month_start + relativedelta(months=1) - relativedelta(days=1)).day
        days_elapsed = today.day
        prorate_factor = days_elapsed / days_in_month
        
        print(f"📅 Today: {today.strftime('%Y-%m-%d')}, Days elapsed: {days_elapsed}/{days_in_month}, Prorate: {prorate_factor:.2f}")
        
        query = """
        WITH CurrentData AS (
            SELECT 
                g.Metric AS metric_name,
                g.Channel AS channel,
                g.Date AS raw_date,
                FORMAT(g.Date, 'MMM yyyy') AS period,
                COALESCE(SUM(cf.Actual), 0) AS actual_value,
                MAX(g.Goal) AS goal_value,
                CASE 
                    WHEN g.Metric = '4 - NCNM' THEN 'USD'
                    ELSE NULL 
                END AS currency,
                CASE 
                    WHEN g.Metric = '4 - NCNM' THEN 'millions'
                    ELSE 'count'
                END AS unit
            FROM aip.goals_20260109 g
            LEFT JOIN tho.Combined_Fact cf 
                ON cf.Goal_First_Touch_ID = g.Unique_ID
            WHERE g.Metric IN ('1 - Leads', '2 - Appointments Completed', '3 - New Clients', '4 - NCNM')
                AND g.Date >= DATEADD(month, -15, GETDATE())
                AND g.Date <= EOMONTH(GETDATE())
                AND LOWER(g.Channel) IN ('advisor driven', 'advisor recruiting', 'beneficiary', 'referral', 'promoter', 'self-sourced', 'other', 'media driven', 'paid leads', 'crp', 'fidelity', 'schwab', 'radio', 'other media', 'target market')
            GROUP BY 
                g.Metric,
                g.Channel,
                g.Date,
                CASE WHEN g.Metric = '4 - NCNM' THEN 'USD' ELSE NULL END,
                CASE WHEN g.Metric = '4 - NCNM' THEN 'millions' ELSE 'count' END
        ),
        PriorYearData AS (
            SELECT 
                g.Metric AS metric_name,
                g.Channel AS channel,
                DATEADD(year, 1, g.Date) AS mapped_date,
                COALESCE(SUM(cf.Actual), 0) AS py_actual_value
            FROM aip.goals_20260109 g
            LEFT JOIN tho.Combined_Fact cf 
                ON cf.Goal_First_Touch_ID = g.Unique_ID
            WHERE g.Metric IN ('1 - Leads', '2 - Appointments Completed', '3 - New Clients', '4 - NCNM')
                AND g.Date >= DATEADD(month, -27, GETDATE())
                AND g.Date < DATEADD(month, -3, GETDATE())
            GROUP BY 
                g.Metric,
                g.Channel,
                g.Date
        )
        SELECT 
            c.metric_name,
            c.channel,
            c.period,
            c.raw_date,
            c.actual_value,
            c.goal_value,
            c.currency,
            c.unit,
            COALESCE(py.py_actual_value, 0) AS py_actual_value
        FROM CurrentData c
        LEFT JOIN PriorYearData py 
            ON c.metric_name = py.metric_name 
            AND LOWER(c.channel) = LOWER(py.channel)
            AND c.raw_date = py.mapped_date
        ORDER BY 
            c.raw_date DESC,
            c.metric_name,
            c.channel
        """
        
        print("🔍 Executing query...")
        df = pd.read_sql(query, conn)
        
        print(f"✅ Query successful! Retrieved {len(df)} rows")
        print(f"📋 Channels from DB: {df['channel'].unique().tolist()}")
        print(f"📋 Metrics from DB: {df['metric_name'].unique().tolist()}")
        
        # Map metric names to frontend names
        df['metric_name'] = df['metric_name'].map(METRIC_MAP).fillna(df['metric_name'])
        
        # Map channel names to frontend names (case-insensitive)
        df['channel'] = df['channel'].str.lower().map(CHANNEL_MAP).fillna(df['channel'])
        
        print(f"📋 Channels after mapping: {df['channel'].unique().tolist()}")
        print(f"📋 Metrics after mapping: {df['metric_name'].unique().tolist()}")
        
        # Aggregate rows that map to the same channel
        df = df.groupby(['metric_name', 'channel', 'period']).agg({
            'actual_value': 'sum',
            'goal_value': 'sum',
            'py_actual_value': 'sum',
            'currency': 'first',
            'unit': 'first'
        }).reset_index()
        
        print(f"📋 After channel aggregation: {len(df)} rows")
        
        # Convert NCNM from dollars to millions
        mask = df['metric_name'] == 'NCNM'
        if mask.any():
            df.loc[mask, 'actual_value'] = df.loc[mask, 'actual_value'] / 1000000
            df.loc[mask, 'goal_value'] = df.loc[mask, 'goal_value'] / 1000000
            df.loc[mask, 'py_actual_value'] = df.loc[mask, 'py_actual_value'] / 1000000
        
        # Prorate PY and goal for current month
        current_month_str = today.strftime('%b %Y')
        print(f"📅 Current month string: {current_month_str}, Prorate factor: {prorate_factor:.2f}")
        
        is_current_month = df['period'] == current_month_str
        if is_current_month.any():
            df.loc[is_current_month, 'py_prorated'] = df.loc[is_current_month, 'py_actual_value'] * prorate_factor
            df.loc[is_current_month, 'goal_prorated'] = df.loc[is_current_month, 'goal_value'] * prorate_factor
            print(f"📊 Prorated {is_current_month.sum()} rows for current month")
        else:
            df['py_prorated'] = df['py_actual_value']
            df['goal_prorated'] = df['goal_value']
        
        df.loc[~is_current_month, 'py_prorated'] = df.loc[~is_current_month, 'py_actual_value']
        df.loc[~is_current_month, 'goal_prorated'] = df.loc[~is_current_month, 'goal_value']
        
        # Calculate totals per metric/period
        totals = df.groupby(['metric_name', 'period']).agg({
            'actual_value': 'sum',
            'goal_value': 'sum',
            'py_actual_value': 'sum',
            'py_prorated': 'sum',
            'goal_prorated': 'sum',
            'currency': 'first',
            'unit': 'first'
        }).reset_index()
        totals['channel'] = 'Total'
        
        print(f"📋 Totals calculated: {len(totals)} rows")
        
        if 'raw_date' in df.columns:
            df = df.drop(columns=['raw_date'])
        
        df = pd.concat([df, totals], ignore_index=True)
        
        # Replace NaN with None for proper JSON serialization
        df = df.replace({pd.NA: None, float('nan'): None})
        import numpy as np
        df = df.replace({np.nan: None})
        
        metrics = df.to_dict('records')
        
        print(f"📤 Returning {len(metrics)} metrics to frontend (including totals)")
        print("=" * 60)
        
        response_data = {
            'success': True,
            'data': metrics,
            'count': len(metrics)
        }
        _set_cached('kpi-metrics', response_data)
        
        return jsonify(response_data)
        
    except pyodbc.Error as db_error:
        error_msg = str(db_error)
        print("=" * 60)
        print("❌ Database Connection Error:")
        print(error_msg)
        print("=" * 60)
        return jsonify({
            'success': False,
            'error': 'Database connection failed',
            'details': error_msg,
            'help': 'Please ensure you are logged into Azure AD and have access to the Synapse DataWarehouse'
        }), 500
        
    except Exception as e:
        error_msg = str(e)
        print("=" * 60)
        print("❌ Unexpected Error:")
        print(error_msg)
        print("=" * 60)
        return jsonify({
            'success': False,
            'error': error_msg
        }), 500


@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()})


@app.route('/api/cache-clear', methods=['POST'])
def clear_cache():
    """Admin endpoint to force-clear the server cache"""
    _invalidate_cache()
    return jsonify({'success': True, 'message': 'Cache cleared'})


# ---------------------------------------------------------------------------
# /api/transformation-log — reads the ADLS Gen2 Delta table at
#   abfss://silver@dlallworthai.dfs.core.windows.net/logging/transformation_log/
# via delta-rs (pure Python, no Spark/ODBC/Synapse). Fully isolated from the
# Synapse endpoints: import is guarded, errors are caught locally, and a 503
# is returned if delta-rs is unavailable.
# ---------------------------------------------------------------------------
@app.route('/api/transformation-log', methods=['GET'])
def get_transformation_log():
    """Return rows from the pipeline transformation_log Delta table."""
    if not DELTA_AVAILABLE or read_delta_table is None:
        return jsonify({
            'success': False,
            'error': f'Delta Lake reader is unavailable: {DELTA_IMPORT_ERROR}',
        }), 503

    # Parse & clamp query params
    try:
        limit = int(request.args.get('limit', 500))
    except (TypeError, ValueError):
        limit = 500
    limit = max(1, min(limit, 5000))

    since_raw = request.args.get('since')  # ISO date/datetime, optional
    no_cache = request.args.get('no_cache', '').lower() in ('1', 'true', 'yes')

    cache_key = f'transformation-log:{limit}:{since_raw or ""}'
    if not no_cache:
        cached = _get_cached(cache_key)
        if cached is not None:
            print(f"⚡ Returning cached {cache_key}")
            return jsonify(cached)

    try:
        print(f"🪵 Reading Delta table: {TRANSFORMATION_LOG_PATH} (limit={limit}, since={since_raw})")

        # Optional timestamp filter pushdown. We try a few common column names;
        # if none exist on the table, we fall back to reading without filter.
        filters = None
        since_dt = None
        if since_raw:
            try:
                # Accept 'YYYY-MM-DD' or full ISO
                since_dt = pd.to_datetime(since_raw, utc=True).to_pydatetime()
            except Exception as e:
                print(f"⚠️  Ignoring invalid 'since' param '{since_raw}': {e}")
                since_dt = None

        if since_dt is not None:
            try:
                import pyarrow.compute as pc
                schema_names = {f['name'] for f in get_delta_schema(TRANSFORMATION_LOG_PATH)}
                ts_col = next(
                    (c for c in (
                        'event_time', 'timestamp', 'log_time', 'created_at',
                        'load_time', 'run_time', 'ingest_time'
                    ) if c in schema_names),
                    None,
                )
                if ts_col:
                    filters = pc.field(ts_col) >= pc.scalar(since_dt)
                    print(f"   Applied filter on column '{ts_col}' >= {since_dt.isoformat()}")
                else:
                    print("   No recognizable timestamp column on table; skipping 'since' filter")
            except Exception as e:
                print(f"⚠️  Could not build filter, returning unfiltered: {e}")
                filters = None

        df = read_delta_table(TRANSFORMATION_LOG_PATH, filters=filters, limit=limit)

        # Sort newest-first if we can infer a timestamp column
        for candidate in (
            'event_time', 'timestamp', 'log_time', 'created_at',
            'load_time', 'run_time', 'ingest_time',
        ):
            if candidate in df.columns:
                try:
                    df = df.sort_values(candidate, ascending=False)
                except Exception:
                    pass
                break

        # Serialize: convert timestamps/np types to JSON-friendly values
        rows = df.head(limit).to_dict(orient='records')
        # pandas may emit Timestamp / NaT; let Flask's json encoder handle via str()
        def _clean(v):
            if v is None:
                return None
            if isinstance(v, float) and (v != v):  # NaN
                return None
            if hasattr(v, 'isoformat'):
                try:
                    return v.isoformat()
                except Exception:
                    return str(v)
            return v

        rows = [{k: _clean(v) for k, v in r.items()} for r in rows]

        payload = {
            'success': True,
            'source': TRANSFORMATION_LOG_PATH,
            'row_count': len(rows),
            'columns': list(df.columns),
            'fetched_at': datetime.utcnow().isoformat() + 'Z',
            'rows': rows,
        }

        _set_cached(cache_key, payload)
        print(f"✅ transformation-log returned {len(rows)} rows")
        return jsonify(payload)

    except Exception as e:
        error_msg = f"Failed to read transformation_log Delta table: {e}"
        print(f"❌ {error_msg}")
        return jsonify({'success': False, 'error': error_msg}), 500


# ---------------------------------------------------------------------------
# Combined endpoint – returns kpi-metrics, net-flows and detailed metrics in
# a single HTTP response.  This is the primary endpoint the frontend should
# call to avoid 3 sequential round-trips to Azure Synapse.
# ---------------------------------------------------------------------------
def _build_kpi_metrics():
    """Internal helper: build kpi-metrics payload (reused by individual + combined endpoints)."""
    cached = _get_cached('kpi-metrics')
    if cached is not None:
        return cached

    conn = get_database_connection()
    today = datetime.now()
    current_month_start = today.replace(day=1)
    days_in_month = (current_month_start + relativedelta(months=1) - relativedelta(days=1)).day
    days_elapsed = today.day
    prorate_factor = days_elapsed / days_in_month

    query = """
    WITH CurrentData AS (
        SELECT 
            g.Metric AS metric_name,
            g.Channel AS channel,
            g.Date AS raw_date,
            FORMAT(g.Date, 'MMM yyyy') AS period,
            COALESCE(SUM(cf.Actual), 0) AS actual_value,
            MAX(g.Goal) AS goal_value,
            CASE WHEN g.Metric = '4 - NCNM' THEN 'USD' ELSE NULL END AS currency,
            CASE WHEN g.Metric = '4 - NCNM' THEN 'millions' ELSE 'count' END AS unit
        FROM aip.goals_20260109 g
        LEFT JOIN tho.Combined_Fact cf ON cf.Goal_First_Touch_ID = g.Unique_ID
        WHERE g.Metric IN ('1 - Leads','2 - Appointments Completed','3 - New Clients','4 - NCNM')
          AND g.Date >= DATEADD(month, -15, GETDATE())
          AND g.Date <= EOMONTH(GETDATE())
          AND LOWER(g.Channel) IN ('advisor driven','advisor recruiting','beneficiary','referral','promoter','self-sourced','other','media driven','paid leads','crp','fidelity','schwab','radio','other media','target market')
        GROUP BY g.Metric, g.Channel, g.Date,
                 CASE WHEN g.Metric='4 - NCNM' THEN 'USD' ELSE NULL END,
                 CASE WHEN g.Metric='4 - NCNM' THEN 'millions' ELSE 'count' END
    ),
    PriorYearData AS (
        SELECT 
            g.Metric AS metric_name, g.Channel AS channel,
            DATEADD(year,1,g.Date) AS mapped_date,
            COALESCE(SUM(cf.Actual),0) AS py_actual_value
        FROM aip.goals_20260109 g
        LEFT JOIN tho.Combined_Fact cf ON cf.Goal_First_Touch_ID = g.Unique_ID
        WHERE g.Metric IN ('1 - Leads','2 - Appointments Completed','3 - New Clients','4 - NCNM')
          AND g.Date >= DATEADD(month,-27,GETDATE())
          AND g.Date <  DATEADD(month,-3,GETDATE())
        GROUP BY g.Metric, g.Channel, g.Date
    )
    SELECT c.metric_name, c.channel, c.period, c.raw_date,
           c.actual_value, c.goal_value, c.currency, c.unit,
           COALESCE(py.py_actual_value,0) AS py_actual_value
    FROM CurrentData c
    LEFT JOIN PriorYearData py
        ON c.metric_name=py.metric_name AND LOWER(c.channel)=LOWER(py.channel) AND c.raw_date=py.mapped_date
    ORDER BY c.raw_date DESC, c.metric_name, c.channel
    """

    import numpy as np
    df = pd.read_sql(query, conn)
    df['metric_name'] = df['metric_name'].map(METRIC_MAP).fillna(df['metric_name'])
    df['channel'] = df['channel'].str.lower().map(CHANNEL_MAP).fillna(df['channel'])
    df = df.groupby(['metric_name','channel','period']).agg({
        'actual_value':'sum','goal_value':'sum','py_actual_value':'sum','currency':'first','unit':'first'
    }).reset_index()

    mask = df['metric_name']=='NCNM'
    if mask.any():
        for col in ('actual_value','goal_value','py_actual_value'):
            df.loc[mask, col] = df.loc[mask, col] / 1_000_000

    current_month_str = today.strftime('%b %Y')
    is_cm = df['period']==current_month_str
    df['py_prorated'] = df['py_actual_value']
    df['goal_prorated'] = df['goal_value']
    if is_cm.any():
        df.loc[is_cm,'py_prorated'] = df.loc[is_cm,'py_actual_value'] * prorate_factor
        df.loc[is_cm,'goal_prorated'] = df.loc[is_cm,'goal_value'] * prorate_factor

    totals = df.groupby(['metric_name','period']).agg({
        'actual_value':'sum','goal_value':'sum','py_actual_value':'sum',
        'py_prorated':'sum','goal_prorated':'sum','currency':'first','unit':'first'
    }).reset_index()
    totals['channel'] = 'Total'
    if 'raw_date' in df.columns:
        df = df.drop(columns=['raw_date'])
    df = pd.concat([df, totals], ignore_index=True)
    df = df.replace({pd.NA: None, float('nan'): None})
    df = df.replace({np.nan: None})

    result = {'success': True, 'data': df.to_dict('records'), 'count': len(df)}
    _set_cached('kpi-metrics', result)
    return result


def _build_net_flows():
    """Internal helper: build net-flows payload."""
    cached = _get_cached('net-flows')
    if cached is not None:
        return cached

    conn = get_database_connection()
    today = datetime.now()
    current_month_start = today.replace(day=1)
    days_in_month = (current_month_start + relativedelta(months=1) - relativedelta(days=1)).day
    days_elapsed = today.day
    prorate_factor = days_elapsed / days_in_month

    query = """
    WITH ActualFlows AS (
        SELECT 
            DATEFROMPARTS(YEAR(CAST(d.Date AS date)),MONTH(CAST(d.Date AS date)),1) AS period_date,
            COALESCE(SUM(rf.NCNM),0) AS ncnm_actual,
            COALESCE(SUM(rf.ECNM),0) AS ecnm_actual,
            COALESCE(SUM(rf.Distribution),0) AS distributions_actual,
            COALESCE(SUM(rf.Attrition),0) AS attrition_actual,
            COALESCE(SUM(ISNULL(rf.NCNM,0)+ISNULL(rf.ECNM,0)+ISNULL(rf.Distribution,0)+ISNULL(rf.Attrition,0)+ISNULL(rf.expenses,0)),0) AS net_flows_actual,
            g.Reporting_Period_Key
        FROM tho.Household_Rollforward rf
        LEFT OUTER JOIN aip.DateDimension d ON rf.Reporting_Period_Key=d.DateKey
        JOIN aip.Goals_Net_Flows_2025 g ON rf.EOMONTH_Key=g.Reporting_Period_Key
        GROUP BY DATEFROMPARTS(YEAR(CAST(d.Date AS date)),MONTH(CAST(d.Date AS date)),1), g.Reporting_Period_Key
    ),
    PYFlows AS (
        SELECT 
            DATEADD(year,1,DATEFROMPARTS(YEAR(CAST(d.Date AS date)),MONTH(CAST(d.Date AS date)),1)) AS period_date,
            COALESCE(SUM(rf.NCNM),0) AS ncnm_py, COALESCE(SUM(rf.ECNM),0) AS ecnm_py,
            COALESCE(SUM(rf.Distribution),0) AS distributions_py, COALESCE(SUM(rf.Attrition),0) AS attrition_py,
            COALESCE(SUM(ISNULL(rf.NCNM,0)+ISNULL(rf.ECNM,0)+ISNULL(rf.Distribution,0)+ISNULL(rf.Attrition,0)+ISNULL(rf.expenses,0)),0) AS net_flows_py
        FROM tho.Household_Rollforward rf
        LEFT OUTER JOIN aip.DateDimension d ON rf.Reporting_Period_Key=d.DateKey
        WHERE DATEFROMPARTS(YEAR(CAST(d.Date AS date)),MONTH(CAST(d.Date AS date)),1) >= DATEADD(month,-15,DATEADD(year,-1,GETDATE()))
          AND DATEFROMPARTS(YEAR(CAST(d.Date AS date)),MONTH(CAST(d.Date AS date)),1) <= EOMONTH(DATEADD(year,-1,GETDATE()))
        GROUP BY DATEADD(year,1,DATEFROMPARTS(YEAR(CAST(d.Date AS date)),MONTH(CAST(d.Date AS date)),1))
    ),
    GoalFlows AS (
        SELECT Reporting_Period_Key,
            COALESCE(SUM(NCNM),0) AS ncnm_goal, COALESCE(SUM(ECNM),0) AS ecnm_goal,
            COALESCE(SUM(Attrition),0) AS attrition_goal, COALESCE(SUM(Distributions),0) AS distributions_goal,
            COALESCE(SUM(Goal),0) AS net_flows_goal
        FROM aip.Goals_Net_Flows_2025
        GROUP BY Reporting_Period_Key
    )
    SELECT a.period_date, FORMAT(a.period_date,'MMM yyyy') AS period,
        COALESCE(SUM(a.ncnm_actual),0) AS ncnm_actual, COALESCE(SUM(a.ecnm_actual),0) AS ecnm_actual,
        COALESCE(SUM(a.net_flows_actual),0) AS net_flows_actual,
        COALESCE(SUM(a.attrition_actual),0) AS attrition_actual, COALESCE(SUM(a.distributions_actual),0) AS distributions_actual,
        COALESCE(SUM(g.ncnm_goal),0) AS ncnm_goal, COALESCE(SUM(g.ecnm_goal),0) AS ecnm_goal,
        COALESCE(SUM(g.attrition_goal),0) AS attrition_goal, COALESCE(SUM(g.distributions_goal),0) AS distributions_goal,
        COALESCE(SUM(g.net_flows_goal),0) AS net_flows_goal,
        COALESCE(MAX(py.ncnm_py),0) AS ncnm_py, COALESCE(MAX(py.ecnm_py),0) AS ecnm_py,
        COALESCE(MAX(py.net_flows_py),0) AS net_flows_py,
        COALESCE(MAX(py.attrition_py),0) AS attrition_py, COALESCE(MAX(py.distributions_py),0) AS distributions_py
    FROM ActualFlows a
    LEFT OUTER JOIN GoalFlows g ON a.Reporting_Period_Key=g.Reporting_Period_Key
    LEFT OUTER JOIN PYFlows py ON a.period_date=py.period_date
    WHERE a.period_date >= DATEADD(month,-15,GETDATE()) AND a.period_date <= EOMONTH(GETDATE())
    GROUP BY a.period_date
    ORDER BY a.period_date DESC
    """

    df = pd.read_sql(query, conn)
    current_month_str = today.strftime('%b %Y')
    results = []
    net_flow_metrics = [
        ('Net Flows','net_flows_actual','net_flows_goal','net_flows_py'),
        ('NCNM_NF','ncnm_actual','ncnm_goal','ncnm_py'),
        ('ECNM','ecnm_actual','ecnm_goal','ecnm_py'),
        ('Distributions','distributions_actual','distributions_goal','distributions_py'),
        ('Attrition','attrition_actual','attrition_goal','attrition_py'),
    ]
    for _, row in df.iterrows():
        period = row['period']
        is_current = period == current_month_str
        for metric_name, actual_col, goal_col, py_col in net_flow_metrics:
            actual = float(row[actual_col]) / 1_000_000
            goal   = float(row[goal_col])   / 1_000_000
            py_actual = float(row[py_col])  / 1_000_000
            results.append({
                'metric_name': metric_name, 'channel': 'Total', 'period': period,
                'actual_value': actual, 'goal_value': goal, 'py_actual_value': py_actual,
                'py_prorated': py_actual * prorate_factor if is_current else py_actual,
                'goal_prorated': goal * prorate_factor if is_current else goal,
                'currency': 'USD', 'unit': 'millions'
            })

    result = {'success': True, 'data': results, 'count': len(results)}
    _set_cached('net-flows', result)
    return result


def _build_detailed_metrics():
    """Internal helper: build kpi-metrics-detailed payload."""
    cached = _get_cached('kpi-metrics-detailed')
    if cached is not None:
        return cached

    conn = get_database_connection()
    today = datetime.now()
    current_month_start = today.replace(day=1)
    days_in_month = (current_month_start + relativedelta(months=1) - relativedelta(days=1)).day
    days_elapsed = today.day
    prorate_factor = days_elapsed / days_in_month

    query = """
    WITH CurrentData AS (
        SELECT 
            g.Metric AS metric_name, g.Channel AS channel_middle,
            g.Date AS raw_date, FORMAT(g.Date,'MMM yyyy') AS period,
            COALESCE(SUM(cf.Actual),0) AS actual_value, MAX(g.Goal) AS goal_value,
            CASE WHEN g.Metric='4 - NCNM' THEN 'USD' ELSE NULL END AS currency,
            CASE WHEN g.Metric='4 - NCNM' THEN 'millions' ELSE 'count' END AS unit
        FROM aip.goals_20260109 g
        LEFT JOIN tho.Combined_Fact cf ON cf.Goal_First_Touch_ID=g.Unique_ID
        WHERE g.Metric IN ('1 - Leads','2 - Appointments Completed','3 - New Clients','4 - NCNM')
          AND g.Date >= DATEADD(month,-15,GETDATE()) AND g.Date <= EOMONTH(GETDATE())
          AND LOWER(g.Channel) IN ('advisor driven','advisor recruiting','beneficiary','referral','promoter','self-sourced','other','media driven','paid leads','crp','fidelity','schwab','radio','other media','target market')
        GROUP BY g.Metric, g.Channel, g.Date,
                 CASE WHEN g.Metric='4 - NCNM' THEN 'USD' ELSE NULL END,
                 CASE WHEN g.Metric='4 - NCNM' THEN 'millions' ELSE 'count' END
    ),
    PriorYearData AS (
        SELECT g.Metric AS metric_name, g.Channel AS channel_middle,
               DATEADD(year,1,g.Date) AS mapped_date,
               COALESCE(SUM(cf.Actual),0) AS py_actual_value
        FROM aip.goals_20260109 g
        LEFT JOIN tho.Combined_Fact cf ON cf.Goal_First_Touch_ID=g.Unique_ID
        WHERE g.Metric IN ('1 - Leads','2 - Appointments Completed','3 - New Clients','4 - NCNM')
          AND g.Date >= DATEADD(month,-27,GETDATE()) AND g.Date < DATEADD(month,-3,GETDATE())
        GROUP BY g.Metric, g.Channel, g.Date
    )
    SELECT c.metric_name, c.channel_middle, c.period, c.raw_date,
           c.actual_value, c.goal_value, c.currency, c.unit,
           COALESCE(py.py_actual_value,0) AS py_actual_value
    FROM CurrentData c
    LEFT JOIN PriorYearData py
        ON c.metric_name=py.metric_name AND LOWER(c.channel_middle)=LOWER(py.channel_middle) AND c.raw_date=py.mapped_date
    ORDER BY c.raw_date DESC, c.metric_name, c.channel_middle
    """

    import numpy as np
    df = pd.read_sql(query, conn)
    df['metric_name'] = df['metric_name'].map(METRIC_MAP).fillna(df['metric_name'])
    df['channel'] = df['channel_middle'].str.lower().map(CHANNEL_PARENT_MAP).fillna(df['channel_middle'])
    df['channel_middle'] = df['channel_middle'].str.lower().map(CHANNEL_MIDDLE_DISPLAY).fillna(df['channel_middle'])
    df = df.groupby(['metric_name','channel','channel_middle','period']).agg({
        'actual_value':'sum','goal_value':'sum','py_actual_value':'sum','currency':'first','unit':'first'
    }).reset_index()

    mask = df['metric_name']=='NCNM'
    if mask.any():
        for col in ('actual_value','goal_value','py_actual_value'):
            df.loc[mask,col] = df.loc[mask,col] / 1_000_000

    current_month_str = today.strftime('%b %Y')
    is_cm = df['period']==current_month_str
    df['py_prorated'] = df['py_actual_value']
    df['goal_prorated'] = df['goal_value']
    if is_cm.any():
        df.loc[is_cm,'py_prorated'] = df.loc[is_cm,'py_actual_value'] * prorate_factor
        df.loc[is_cm,'goal_prorated'] = df.loc[is_cm,'goal_value'] * prorate_factor

    if 'raw_date' in df.columns:
        df = df.drop(columns=['raw_date'])
    df = df.replace({pd.NA: None, float('nan'): None})
    df = df.replace({np.nan: None})

    result = {'success': True, 'data': df.to_dict('records'), 'count': len(df)}
    _set_cached('kpi-metrics-detailed', result)
    return result


@app.route('/api/all-metrics', methods=['GET'])
def get_all_metrics():
    """
    Combined endpoint – returns kpi-metrics, net-flows, and detailed metrics
    in a single HTTP response.  This eliminates 3 sequential HTTP round-trips
    from the frontend.

    Queries run sequentially on the shared Synapse connection to avoid
    "connection busy" errors, but the server-side cache means most requests
    return instantly without hitting the database at all.
    """
    def _safe_build(name, builder):
        try:
            return builder()
        except Exception as exc:
            print(f"⚠️  {name} failed: {exc}")
            return {'success': False, 'error': str(exc), 'data': []}

    kpi = _safe_build('kpiMetrics', _build_kpi_metrics)
    nf  = _safe_build('netFlows', _build_net_flows)
    det = _safe_build('detailedMetrics', _build_detailed_metrics)

    return jsonify({
        'success': True,
        'kpiMetrics': kpi,
        'netFlows': nf,
        'detailedMetrics': det,
    })


# Reverse mapping to get parent channel from child channel
CHANNEL_PARENT_MAP = {
    'advisor driven': 'Advisor Enabled',
    'advisor recruiting': 'Advisor Enabled',
    'referral': 'Advisor Enabled',
    'promoter': 'Advisor Enabled',
    'self-sourced': 'Advisor Enabled',
    'other': 'Advisor Enabled',
    'beneficiary': 'Advisor Enabled',
    'media driven': 'Media',
    'radio': 'Media',
    'other media': 'Media',
    'target market': 'Media',
    'paid leads': 'Paid Leads',
    'crp': 'CRP',
    'fidelity': 'CRP',
    'schwab': 'CRP',
}

# Display names for channel_middle values
CHANNEL_MIDDLE_DISPLAY = {
    'advisor driven': 'Advisor Driven',
    'advisor recruiting': 'Advisor Recruiting',
    'referral': 'Referral',
    'promoter': 'Promoter',
    'self-sourced': 'Self-Sourced',
    'other': 'Other',
    'beneficiary': 'Beneficiary',
    'media driven': 'Media Driven',
    'radio': 'Radio',
    'other media': 'Other Media',
    'target market': 'Target Market',
    'paid leads': 'Paid Leads',
    'crp': 'CRP',
    'fidelity': 'Fidelity',
    'schwab': 'Schwab',
}


@app.route('/api/kpi-metrics-detailed', methods=['GET'])
def get_kpi_metrics_detailed():
    """Fetch KPI metrics with channel_middle granularity (non-aggregated channels)"""
    cached = _get_cached('kpi-metrics-detailed')
    if cached is not None:
        print("⚡ Returning cached kpi-metrics-detailed")
        return jsonify(cached)

    try:
        print("=" * 60)
        print("📊 Fetching detailed KPI metrics (channel_middle)...")
        print("=" * 60)
        
        conn = get_database_connection()
        
        today = datetime.now()
        current_month_start = today.replace(day=1)
        days_in_month = (current_month_start + relativedelta(months=1) - relativedelta(days=1)).day
        days_elapsed = today.day
        prorate_factor = days_elapsed / days_in_month
        
        # Query returns non-aggregated channel data
        query = """
        WITH CurrentData AS (
            SELECT 
                g.Metric AS metric_name,
                g.Channel AS channel_middle,
                g.Date AS raw_date,
                FORMAT(g.Date, 'MMM yyyy') AS period,
                COALESCE(SUM(cf.Actual), 0) AS actual_value,
                MAX(g.Goal) AS goal_value,
                CASE 
                    WHEN g.Metric = '4 - NCNM' THEN 'USD'
                    ELSE NULL 
                END AS currency,
                CASE 
                    WHEN g.Metric = '4 - NCNM' THEN 'millions'
                    ELSE 'count'
                END AS unit
            FROM aip.goals_20260109 g
            LEFT JOIN tho.Combined_Fact cf 
                ON cf.Goal_First_Touch_ID = g.Unique_ID
            WHERE g.Metric IN ('1 - Leads', '2 - Appointments Completed', '3 - New Clients', '4 - NCNM')
                AND g.Date >= DATEADD(month, -15, GETDATE())
                AND g.Date <= EOMONTH(GETDATE())
                AND LOWER(g.Channel) IN ('advisor driven', 'advisor recruiting', 'beneficiary', 'referral', 'promoter', 'self-sourced', 'other', 'media driven', 'paid leads', 'crp', 'fidelity', 'schwab', 'radio', 'other media', 'target market')
            GROUP BY 
                g.Metric,
                g.Channel,
                g.Date,
                CASE WHEN g.Metric = '4 - NCNM' THEN 'USD' ELSE NULL END,
                CASE WHEN g.Metric = '4 - NCNM' THEN 'millions' ELSE 'count' END
        ),
        PriorYearData AS (
            SELECT 
                g.Metric AS metric_name,
                g.Channel AS channel_middle,
                DATEADD(year, 1, g.Date) AS mapped_date,
                COALESCE(SUM(cf.Actual), 0) AS py_actual_value
            FROM aip.goals_20260109 g
            LEFT JOIN tho.Combined_Fact cf 
                ON cf.Goal_First_Touch_ID = g.Unique_ID
            WHERE g.Metric IN ('1 - Leads', '2 - Appointments Completed', '3 - New Clients', '4 - NCNM')
                AND g.Date >= DATEADD(month, -27, GETDATE())
                AND g.Date < DATEADD(month, -3, GETDATE())
            GROUP BY 
                g.Metric,
                g.Channel,
                g.Date
        )
        SELECT 
            c.metric_name,
            c.channel_middle,
            c.period,
            c.raw_date,
            c.actual_value,
            c.goal_value,
            c.currency,
            c.unit,
            COALESCE(py.py_actual_value, 0) AS py_actual_value
        FROM CurrentData c
        LEFT JOIN PriorYearData py 
            ON c.metric_name = py.metric_name 
            AND LOWER(c.channel_middle) = LOWER(py.channel_middle)
            AND c.raw_date = py.mapped_date
        ORDER BY 
            c.raw_date DESC,
            c.metric_name,
            c.channel_middle
        """
        
        print("🔍 Executing detailed query...")
        df = pd.read_sql(query, conn)
        
        print(f"✅ Query successful! Retrieved {len(df)} rows")
        
        # Map metric names to frontend names
        df['metric_name'] = df['metric_name'].map(METRIC_MAP).fillna(df['metric_name'])
        
        # Add parent channel column
        df['channel'] = df['channel_middle'].str.lower().map(CHANNEL_PARENT_MAP).fillna(df['channel_middle'])
        
        # Format channel_middle display names
        df['channel_middle'] = df['channel_middle'].str.lower().map(CHANNEL_MIDDLE_DISPLAY).fillna(df['channel_middle'])
        
        # Aggregate by channel_middle (in case of duplicates)
        df = df.groupby(['metric_name', 'channel', 'channel_middle', 'period']).agg({
            'actual_value': 'sum',
            'goal_value': 'sum',
            'py_actual_value': 'sum',
            'currency': 'first',
            'unit': 'first'
        }).reset_index()
        
        # Convert NCNM from dollars to millions
        mask = df['metric_name'] == 'NCNM'
        if mask.any():
            df.loc[mask, 'actual_value'] = df.loc[mask, 'actual_value'] / 1000000
            df.loc[mask, 'goal_value'] = df.loc[mask, 'goal_value'] / 1000000
            df.loc[mask, 'py_actual_value'] = df.loc[mask, 'py_actual_value'] / 1000000
        
        # Prorate PY and goal for current month
        current_month_str = today.strftime('%b %Y')
        is_current_month = df['period'] == current_month_str
        if is_current_month.any():
            df.loc[is_current_month, 'py_prorated'] = df.loc[is_current_month, 'py_actual_value'] * prorate_factor
            df.loc[is_current_month, 'goal_prorated'] = df.loc[is_current_month, 'goal_value'] * prorate_factor
        else:
            df['py_prorated'] = df['py_actual_value']
            df['goal_prorated'] = df['goal_value']
        
        df.loc[~is_current_month, 'py_prorated'] = df.loc[~is_current_month, 'py_actual_value']
        df.loc[~is_current_month, 'goal_prorated'] = df.loc[~is_current_month, 'goal_value']
        
        if 'raw_date' in df.columns:
            df = df.drop(columns=['raw_date'])
        
        # Replace NaN with None
        df = df.replace({pd.NA: None, float('nan'): None})
        import numpy as np
        df = df.replace({np.nan: None})
        
        metrics = df.to_dict('records')
        
        print(f"📤 Returning {len(metrics)} detailed metrics")
        print("=" * 60)
        
        response_data = {
            'success': True,
            'data': metrics,
            'count': len(metrics)
        }
        _set_cached('kpi-metrics-detailed', response_data)
        
        return jsonify(response_data)
        
    except Exception as e:
        error_msg = str(e)
        print(f"❌ Detailed Metrics Error: {error_msg}")
        return jsonify({
            'success': False,
            'error': error_msg
        }), 500


@app.route('/api/net-flows', methods=['GET'])
def get_net_flows():
    """Fetch Net Flows metrics from Synapse (Net Flows, NCNM, ECNM, Distributions, Attrition)"""
    cached = _get_cached('net-flows')
    if cached is not None:
        print("⚡ Returning cached net-flows")
        return jsonify(cached)

    try:
        print("=" * 60)
        print("📊 Fetching Net Flows data from Synapse...")
        print(f"📅 Server time: {datetime.now().isoformat()}")
        print("=" * 60)
        
        conn = get_database_connection()
        print("✅ Database connection acquired for net-flows")
        
        today = datetime.now()
        current_month_start = today.replace(day=1)
        days_in_month = (current_month_start + relativedelta(months=1) - relativedelta(days=1)).day
        days_elapsed = today.day
        prorate_factor = days_elapsed / days_in_month
        
        query = """
        WITH ActualFlows AS (
            SELECT 
                DATEFROMPARTS(YEAR(CAST(d.Date AS date)), MONTH(CAST(d.Date AS date)), 1) AS period_date,
                COALESCE(SUM(rf.NCNM), 0) AS ncnm_actual,
                COALESCE(SUM(rf.ECNM), 0) AS ecnm_actual,
                COALESCE(SUM(rf.Distribution), 0) AS distributions_actual,
                COALESCE(SUM(rf.Attrition), 0) AS attrition_actual,
                COALESCE(SUM(
                    ISNULL(rf.NCNM, 0) + ISNULL(rf.ECNM, 0) + 
                    ISNULL(rf.Distribution, 0) + ISNULL(rf.Attrition, 0) + ISNULL(rf.expenses, 0)
                ), 0) AS net_flows_actual,
                g.Reporting_Period_Key
            FROM tho.Household_Rollforward rf
            LEFT OUTER JOIN aip.DateDimension d ON rf.Reporting_Period_Key = d.DateKey
            JOIN aip.Goals_Net_Flows_2025 g ON rf.EOMONTH_Key = g.Reporting_Period_Key
            GROUP BY 
                DATEFROMPARTS(YEAR(CAST(d.Date AS date)), MONTH(CAST(d.Date AS date)), 1),
                g.Reporting_Period_Key
        ),
        PYFlows AS (
            SELECT 
                /* Shift PY month forward 1 year so it aligns with the current-year period */
                DATEADD(year, 1, DATEFROMPARTS(YEAR(CAST(d.Date AS date)), MONTH(CAST(d.Date AS date)), 1)) AS period_date,
                COALESCE(SUM(rf.NCNM), 0) AS ncnm_py,
                COALESCE(SUM(rf.ECNM), 0) AS ecnm_py,
                COALESCE(SUM(rf.Distribution), 0) AS distributions_py,
                COALESCE(SUM(rf.Attrition), 0) AS attrition_py,
                COALESCE(SUM(
                    ISNULL(rf.NCNM, 0) + ISNULL(rf.ECNM, 0) +
                    ISNULL(rf.Distribution, 0) + ISNULL(rf.Attrition, 0) + ISNULL(rf.expenses, 0)
                ), 0) AS net_flows_py
            FROM tho.Household_Rollforward rf
            LEFT OUTER JOIN aip.DateDimension d ON rf.Reporting_Period_Key = d.DateKey
            WHERE DATEFROMPARTS(YEAR(CAST(d.Date AS date)), MONTH(CAST(d.Date AS date)), 1)
                  >= DATEADD(month, -15, DATEADD(year, -1, GETDATE()))
              AND DATEFROMPARTS(YEAR(CAST(d.Date AS date)), MONTH(CAST(d.Date AS date)), 1)
                  <= EOMONTH(DATEADD(year, -1, GETDATE()))
            GROUP BY 
                DATEADD(year, 1, DATEFROMPARTS(YEAR(CAST(d.Date AS date)), MONTH(CAST(d.Date AS date)), 1))
        ),
        GoalFlows AS (
            SELECT 
                Reporting_Period_Key,
                COALESCE(SUM(NCNM), 0) AS ncnm_goal,
                COALESCE(SUM(ECNM), 0) AS ecnm_goal,
                COALESCE(SUM(Attrition), 0) AS attrition_goal,
                COALESCE(SUM(Distributions), 0) AS distributions_goal,
                COALESCE(SUM(Goal), 0) AS net_flows_goal
            FROM aip.Goals_Net_Flows_2025
            GROUP BY Reporting_Period_Key
        )
        SELECT 
            a.period_date,
            FORMAT(a.period_date, 'MMM yyyy') AS period,
            COALESCE(SUM(a.ncnm_actual), 0) AS ncnm_actual,
            COALESCE(SUM(a.ecnm_actual), 0) AS ecnm_actual,
            COALESCE(SUM(a.net_flows_actual), 0) AS net_flows_actual,
            COALESCE(SUM(a.attrition_actual), 0) AS attrition_actual,
            COALESCE(SUM(a.distributions_actual), 0) AS distributions_actual,
            COALESCE(SUM(g.ncnm_goal), 0) AS ncnm_goal,
            COALESCE(SUM(g.ecnm_goal), 0) AS ecnm_goal,
            COALESCE(SUM(g.attrition_goal), 0) AS attrition_goal,
            COALESCE(SUM(g.distributions_goal), 0) AS distributions_goal,
            COALESCE(SUM(g.net_flows_goal), 0) AS net_flows_goal,
            COALESCE(MAX(py.ncnm_py), 0) AS ncnm_py,
            COALESCE(MAX(py.ecnm_py), 0) AS ecnm_py,
            COALESCE(MAX(py.net_flows_py), 0) AS net_flows_py,
            COALESCE(MAX(py.attrition_py), 0) AS attrition_py,
            COALESCE(MAX(py.distributions_py), 0) AS distributions_py
        FROM ActualFlows a
        LEFT OUTER JOIN GoalFlows g ON a.Reporting_Period_Key = g.Reporting_Period_Key
        LEFT OUTER JOIN PYFlows py ON a.period_date = py.period_date
        WHERE a.period_date >= DATEADD(month, -15, GETDATE())
          AND a.period_date <= EOMONTH(GETDATE())
        GROUP BY a.period_date
        ORDER BY a.period_date DESC
        """
        
        print("🔍 Executing Net Flows query...")
        query_start = datetime.now()
        df = pd.read_sql(query, conn)
        query_duration = (datetime.now() - query_start).total_seconds()
        print(f"✅ Net Flows query successful! Retrieved {len(df)} rows in {query_duration:.2f}s")
        
        if len(df) > 0:
            print(f"📋 Columns: {df.columns.tolist()}")
            print(f"📋 Periods: {df['period'].tolist() if 'period' in df.columns else 'N/A'}")
        
        if len(df) == 0:
            print("⚠️ No data returned from Net Flows query")
            return jsonify({
                'success': True,
                'data': [],
                'count': 0
            })
        
        current_month_str = today.strftime('%b %Y')
        results = []
        
        net_flow_metrics = [
            ('Net Flows', 'net_flows_actual', 'net_flows_goal', 'net_flows_py'),
            ('NCNM_NF', 'ncnm_actual', 'ncnm_goal', 'ncnm_py'),
            ('ECNM', 'ecnm_actual', 'ecnm_goal', 'ecnm_py'),
            ('Distributions', 'distributions_actual', 'distributions_goal', 'distributions_py'),
            ('Attrition', 'attrition_actual', 'attrition_goal', 'attrition_py'),
        ]
        
        for _, row in df.iterrows():
            period = row['period']
            is_current = period == current_month_str
            
            for metric_name, actual_col, goal_col, py_col in net_flow_metrics:
                actual = float(row[actual_col]) / 1000000
                goal = float(row[goal_col]) / 1000000
                py_actual = float(row[py_col]) / 1000000
                
                results.append({
                    'metric_name': metric_name,
                    'channel': 'Total',
                    'period': period,
                    'actual_value': actual,
                    'goal_value': goal,
                    'py_actual_value': py_actual,
                    'py_prorated': py_actual * prorate_factor if is_current else py_actual,
                    'goal_prorated': goal * prorate_factor if is_current else goal,
                    'currency': 'USD',
                    'unit': 'millions'
                })
        
        print(f"📤 Returning {len(results)} Net Flows metrics")
        
        response_data = {
            'success': True,
            'data': results,
            'count': len(results)
        }
        _set_cached('net-flows', response_data)
        
        return jsonify(response_data)
        
    except Exception as e:
        error_msg = str(e)
        import traceback
        print(f"❌ Net Flows Error: {error_msg}")
        print(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': error_msg
        }), 500


# ---------------------------------------------------------------------------
# User Analytics – page view tracking stored in Azure Synapse
# ---------------------------------------------------------------------------
_ANALYTICS_TABLE = 'aip.page_views'
_analytics_buffer: list = []
_analytics_buffer_lock = Lock()
_ANALYTICS_FLUSH_SIZE = int(os.environ.get('ANALYTICS_FLUSH_SIZE', '1'))  # events before flushing to Synapse
# Whether aip.page_views has the [environment] column. None = not yet checked;
# cached after the first probe so reads/writes can degrade gracefully when the
# column is missing and the app's SQL login can't ALTER the table.
_analytics_env_col = None
_ANALYTICS_DETAIL_LIMIT = int(os.environ.get('ANALYTICS_DETAIL_LIMIT', '500'))  # detail rows returned
_ANALYTICS_TOP_USERS = int(os.environ.get('ANALYTICS_TOP_USERS', '10'))  # rows in the Top Users breakdown


def _site_env() -> str:
    """Which deployment recorded/queries a view: 'prod' or 'dev'.

    App Usage only surfaces prod traffic, so every tracked view is stamped with
    the site it came from. Prefer an explicit APP_ENV; otherwise fall back to
    the dev slot's AUTH_DISABLE=1 marker (prod does not set it).
    """
    env = (os.environ.get('APP_ENV') or '').strip().lower()
    if env in ('prod', 'production'):
        return 'prod'
    if env in ('dev', 'development', 'staging'):
        return 'dev'
    if (os.environ.get('AUTH_DISABLE') or '').strip().lower() in ('1', 'true', 'yes', 'on'):
        return 'dev'
    return 'prod'


def _ensure_analytics_table(conn):
    """Create the analytics table in Synapse if it doesn't exist."""
    try:
        cursor = conn.cursor()
        cursor.execute(f"""
            IF NOT EXISTS (
                SELECT * FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_SCHEMA = 'aip' AND TABLE_NAME = 'page_views'
            )
            CREATE TABLE {_ANALYTICS_TABLE} (
                [id]              INT IDENTITY(1,1) NOT NULL,
                [timestamp]       DATETIME2         NOT NULL,
                [page]            NVARCHAR(500)     NULL,
                [referrer]        NVARCHAR(1000)    NULL,
                [user_agent]      NVARCHAR(1000)    NULL,
                [ip_address]      NVARCHAR(45)      NULL,
                [screen_width]    INT               NULL,
                [screen_height]   INT               NULL,
                [window_width]    INT               NULL,
                [window_height]   INT               NULL,
                [load_time_ms]    INT               NULL,
                [is_embedded]     BIT               NULL,
                [timezone]        NVARCHAR(100)     NULL,
                [language]        NVARCHAR(20)      NULL,
                [user_email]      NVARCHAR(320)     NULL,
                [environment]     NVARCHAR(20)      NULL
            )
        """)
        cursor.commit()
        cursor.close()
    except Exception as e:
        print(f"⚠️  Analytics table check/create failed: {e}")
    # Best-effort add the environment column on a pre-existing table.
    _ensure_env_column(conn)


def _ensure_env_column(conn) -> bool:
    """Return True if aip.page_views has an [environment] column.

    Adds it when missing and permitted; the result is cached so a login without
    ALTER rights only fails once and analytics keep working (env filter skipped).
    """
    global _analytics_env_col
    if _analytics_env_col is not None:
        return _analytics_env_col
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = 'aip' AND TABLE_NAME = 'page_views'
              AND COLUMN_NAME = 'environment'
        """)
        exists = int((cursor.fetchone() or [0])[0] or 0) > 0
        if not exists:
            try:
                cursor.execute(f"ALTER TABLE {_ANALYTICS_TABLE} ADD [environment] NVARCHAR(20) NULL")
                cursor.commit()
                exists = True
                print("📊 Added [environment] column to aip.page_views")
            except Exception as e:
                print(f"⚠️  Could not add [environment] column; analytics will run without the env filter: {e}")
                exists = False
        cursor.close()
        _analytics_env_col = exists
    except Exception as e:
        print(f"⚠️  [environment] column check failed; assuming absent: {e}")
        _analytics_env_col = False
    return _analytics_env_col


def _flush_analytics_buffer():
    """Write buffered page-view events to Synapse."""
    with _analytics_buffer_lock:
        if not _analytics_buffer:
            return
        rows = list(_analytics_buffer)
        _analytics_buffer.clear()

    try:
        conn = get_database_connection()
        _ensure_analytics_table(conn)
        has_env = _ensure_env_column(conn)
        cursor = conn.cursor()
        for row in rows:
            if has_env:
                cursor.execute(f"""
                    INSERT INTO {_ANALYTICS_TABLE}
                        ([timestamp], [page], [referrer], [user_agent], [ip_address],
                         [screen_width], [screen_height], [window_width], [window_height],
                         [load_time_ms], [is_embedded], [timezone], [language],
                         [user_email], [environment])
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    row['timestamp'],
                    row.get('page'),
                    row.get('referrer'),
                    row.get('user_agent'),
                    row.get('ip_address'),
                    row.get('screen_width'),
                    row.get('screen_height'),
                    row.get('window_width'),
                    row.get('window_height'),
                    row.get('load_time_ms'),
                    row.get('is_embedded'),
                    row.get('timezone'),
                    row.get('language'),
                    row.get('user_email'),
                    row.get('environment'),
                )
            else:
                cursor.execute(f"""
                    INSERT INTO {_ANALYTICS_TABLE}
                        ([timestamp], [page], [referrer], [user_agent], [ip_address],
                         [screen_width], [screen_height], [window_width], [window_height],
                         [load_time_ms], [is_embedded], [timezone], [language],
                         [user_email])
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    row['timestamp'],
                    row.get('page'),
                    row.get('referrer'),
                    row.get('user_agent'),
                    row.get('ip_address'),
                    row.get('screen_width'),
                    row.get('screen_height'),
                    row.get('window_width'),
                    row.get('window_height'),
                    row.get('load_time_ms'),
                    row.get('is_embedded'),
                    row.get('timezone'),
                    row.get('language'),
                    row.get('user_email'),
                )
        cursor.commit()
        cursor.close()
        print(f"📊 Flushed {len(rows)} page-view(s) to Synapse")
    except Exception as e:
        print(f"⚠️  Analytics flush failed: {e}")
        # Put rows back so they aren't lost
        with _analytics_buffer_lock:
            _analytics_buffer.extend(rows)


def _resolve_user_identity(req):
    """Extract user email from SSO headers, trying multiple common providers.
    Returns (email, source) where source indicates which header matched."""
    # Order matters – most specific first
    candidates = [
        # Azure App Service EasyAuth / Entra ID
        ('X-MS-CLIENT-PRINCIPAL-NAME', 'EasyAuth'),
        # Azure AD Application Proxy
        ('X-MS-PROXY-USER', 'AzureADProxy'),
        # Common reverse-proxy / SSO gateway headers
        ('X-Forwarded-User', 'Proxy'),
        ('X-Forwarded-Email', 'Proxy'),
        ('X-User-Email', 'Proxy'),
        ('X-Auth-Request-Email', 'OAuth2Proxy'),
        ('Remote-User', 'RemoteUser'),
        # Okta / generic OIDC
        ('X-Okta-User', 'Okta'),
        ('Oidc-Claim-Email', 'OIDC'),
        ('Oidc-Claim-Preferred-Username', 'OIDC'),
    ]
    for header, source in candidates:
        value = req.headers.get(header)
        if value:
            return value.strip(), source
    return None, None


@app.route('/api/debug-headers', methods=['GET'])
def debug_headers():
    """Return all request headers (dev/debug only) to identify SSO headers."""
    headers = {k: v for k, v in request.headers}
    email, source = _resolve_user_identity(request)
    return jsonify({
        'detected_user': email,
        'detection_source': source,
        'all_headers': headers,
    })


@app.route('/api/track', methods=['POST'])
def track_page_view():
    """Record a page-view event from the frontend."""
    try:
        data = request.get_json(silent=True) or {}

        # Determine client IP (respects proxies)
        ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        if ip and ',' in ip:
            ip = ip.split(',')[0].strip()

        # Resolve user identity from SSO headers (auto-detects provider)
        user_email, _source = _resolve_user_identity(request)
        # Frontend can also pass identity explicitly as fallback
        if not user_email:
            user_email = data.get('userEmail')

        event = {
            'timestamp': datetime.utcnow(),
            'page': data.get('page', '/'),
            'referrer': data.get('referrer'),
            'user_agent': request.headers.get('User-Agent', '')[:1000],
            'ip_address': ip,
            'screen_width': data.get('screenWidth'),
            'screen_height': data.get('screenHeight'),
            'window_width': data.get('windowWidth'),
            'window_height': data.get('windowHeight'),
            'load_time_ms': data.get('loadTimeMs'),
            'is_embedded': data.get('isEmbedded'),
            'timezone': data.get('timezone'),
            'language': data.get('language'),
            'user_email': user_email,
            'environment': _site_env(),
        }

        with _analytics_buffer_lock:
            _analytics_buffer.append(event)
            should_flush = len(_analytics_buffer) >= _ANALYTICS_FLUSH_SIZE

        # Flush in the request thread if buffer is full, otherwise it will
        # flush on next full buffer or on the /api/analytics read
        if should_flush:
            _flush_analytics_buffer()

        return jsonify({'success': True}), 202

    except Exception as e:
        print(f"⚠️  Track error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# Map a tracked page path to a tool id + display name. Ordered most-specific
# first so /reporting/kpi wins over / and /app-usage over /admin.
#
# Every user-facing route MUST have an entry here so App Usage attributes its
# page views to the right tool; unmapped paths fall through to ('other',
# 'Other'). The tool id should match the tool's `id` in tool-manifest.json and the
# <ToolGuard toolId=...> on its React route. When you add a new tool/report,
# add its route here as part of the tool checklist (see copilot-instructions.md).
_TOOL_ROUTES = analytics_routes()


def _page_to_tool(page):
    """Map a tracked page path to (tool_id, display_name)."""
    p = ('/' + (page or '/').strip().lstrip('/')).rstrip('/').lower() or '/'
    for prefix, tid, name in _TOOL_ROUTES:
        pref = prefix.rstrip('/').lower() or '/'
        if pref == '/':
            if p == '/':
                return tid, name
        elif p == pref or p.startswith(pref + '/'):
            return tid, name
    return 'other', 'Other'


def _analytics_filters(args, has_env_column=True):
    """Build the shared WHERE clause + params from query args.

    Returns (where_sql, params, days, emails, mode). Emails are parameterized to
    prevent SQL injection. The environment filter is only applied when the table
    actually has an [environment] column (``has_env_column``).
    """
    try:
        days = int(args.get('days', 30))
    except (TypeError, ValueError):
        days = 30
    days = max(1, min(days, 3650))

    mode = (args.get('email_mode') or 'include').strip().lower()
    if mode not in ('include', 'exclude'):
        mode = 'include'

    raw = args.get('emails', '') or ''
    emails = [e.strip().lower() for e in raw.split(',') if e.strip()]

    where = ['[timestamp] >= DATEADD(day, -?, GETUTCDATE())']
    params = [days]

    # Environment scope. App Usage surfaces PROD traffic only by default, so
    # dev-site views are filtered out. Rows written before per-site tagging have
    # a NULL environment and are treated as prod (legacy history is kept). The
    # filter is skipped entirely when the column doesn't exist yet.
    env = (args.get('env') or 'prod').strip().lower()
    if has_env_column:
        if env == 'prod':
            where.append("([environment] = 'prod' OR [environment] IS NULL)")
        elif env == 'dev':
            where.append("[environment] = 'dev'")
        # 'all' → no environment filter

    if emails:
        placeholders = ','.join(['?'] * len(emails))
        if mode == 'exclude':
            where.append(f'(LOWER([user_email]) NOT IN ({placeholders}) OR [user_email] IS NULL)')
        else:
            where.append(f'LOWER([user_email]) IN ({placeholders})')
        params.extend(emails)
    return ' AND '.join(where), params, days, emails, mode


@app.route('/api/analytics', methods=['GET'])
def get_analytics():
    """Return page-view analytics summary from Synapse."""
    try:
        # Flush any pending events first
        _flush_analytics_buffer()

        conn = get_database_connection()
        _ensure_analytics_table(conn)

        has_env = _ensure_env_column(conn)
        where_sql, params, days, emails, mode = _analytics_filters(request.args, has_env)

        # Optional tool include/exclude filter (used by the App Usage right-click
        # menu). Resolved against the same page->tool mapping as the breakdown.
        tools_filter = [t.strip() for t in (request.args.get('tools', '') or '').split(',') if t.strip()]
        tool_mode = (request.args.get('tool_mode') or 'include').strip().lower()
        if tool_mode not in ('include', 'exclude'):
            tool_mode = 'include'

        # Per-page counts (day + email filter only). Drives the per-tool
        # breakdown and resolves which pages the tool filter selects.
        page_query = f"""
        SELECT
            [page]                       AS [page],
            COUNT(*)                     AS [views],
            COUNT(DISTINCT [ip_address]) AS [unique_visitors],
            COUNT(DISTINCT [user_email]) AS [unique_users]
        FROM {_ANALYTICS_TABLE}
        WHERE {where_sql}
        GROUP BY [page]
        """
        pages = pd.read_sql(page_query, conn, params=params).to_dict('records')

        def _page_selected(page) -> bool:
            if not tools_filter:
                return True
            tid, _ = _page_to_tool(page)
            in_set = tid in tools_filter
            return (not in_set) if tool_mode == 'exclude' else in_set

        selected_pages = [r.get('page') for r in pages if _page_selected(r.get('page'))]

        # Aggregate the selected pages into tools (see _page_to_tool).
        tool_map: dict = {}
        for row in pages:
            if not _page_selected(row.get('page')):
                continue
            tid, name = _page_to_tool(row.get('page'))
            agg = tool_map.setdefault(
                tid,
                {'tool_id': tid, 'tool': name, 'views': 0, 'unique_visitors': 0, 'unique_users': 0},
            )
            agg['views'] += int(row.get('views') or 0)
            # Distinct counts are per-page; summing across a tool's pages is an
            # approximation (a user active on two pages of one tool counts twice).
            agg['unique_visitors'] += int(row.get('unique_visitors') or 0)
            agg['unique_users'] += int(row.get('unique_users') or 0)
        by_tool = sorted(tool_map.values(), key=lambda r: r['views'], reverse=True)

        # Summary + daily honor the day/email filters plus the tool filter (via a
        # page IN clause built from the resolved pages).
        s_where, s_params = where_sql, list(params)
        tool_active = bool(tools_filter)
        empty = tool_active and not selected_pages
        if tool_active and selected_pages:
            placeholders = ','.join(['?'] * len(selected_pages))
            s_where = f"{where_sql} AND [page] IN ({placeholders})"
            s_params = list(params) + selected_pages

        if empty:
            summary = {
                'total_views': 0, 'unique_visitors': 0, 'unique_users': 0,
                'first_visit': None, 'last_visit': None,
            }
            daily = []
            details = []
            by_user = []
        else:
            summary = pd.read_sql(f"""
                SELECT
                    COUNT(*)                       AS total_views,
                    COUNT(DISTINCT [ip_address])   AS unique_visitors,
                    COUNT(DISTINCT [user_email])   AS unique_users,
                    MIN([timestamp])               AS first_visit,
                    MAX([timestamp])               AS last_visit
                FROM {_ANALYTICS_TABLE}
                WHERE {s_where}
            """, conn, params=s_params).to_dict('records')[0]

            daily = pd.read_sql(f"""
                SELECT
                    CAST([timestamp] AS DATE)    AS [date],
                    COUNT(*)                     AS [views],
                    COUNT(DISTINCT [ip_address]) AS [unique_visitors]
                FROM {_ANALYTICS_TABLE}
                WHERE {s_where}
                GROUP BY CAST([timestamp] AS DATE)
                ORDER BY [date] ASC
            """, conn, params=s_params).to_dict('records')

            # Detailed rows (newest first) honoring the SAME filters as the
            # charts, so filtering a chart also filters this table. Capped so the
            # payload stays small; the UI notes when it's truncated.
            detail_df = pd.read_sql(f"""
                SELECT TOP {int(_ANALYTICS_DETAIL_LIMIT)}
                    [timestamp]  AS [timestamp],
                    [user_email] AS [user_email],
                    [page]       AS [page]
                FROM {_ANALYTICS_TABLE}
                WHERE {s_where}
                ORDER BY [timestamp] DESC
            """, conn, params=s_params)
            # NULL text columns come back from pandas as float NaN, which would
            # serialize as an invalid `NaN` JSON token (browsers reject it → the
            # frontend sees "HTTP 200 OK"). Coerce every NaN/NaT to None first.
            detail_rows = detail_df.astype(object).where(pd.notnull(detail_df), None).to_dict('records')
            details = []
            for r in detail_rows:
                page = r.get('page')
                tid, name = _page_to_tool(page if isinstance(page, str) else None)
                ts = r.get('timestamp')
                details.append({
                    'timestamp': ts.isoformat() if hasattr(ts, 'isoformat') else (str(ts) if ts is not None else None),
                    'user_email': r.get('user_email') if isinstance(r.get('user_email'), str) else None,
                    'page': page if isinstance(page, str) else None,
                    'tool_id': tid,
                    'tool': name,
                })

            # Top Users — view counts grouped by user, honoring the same
            # day/email/tool filters as the charts. NULL emails (anonymous
            # traffic) collapse into a single row with user_email = None.
            user_df = pd.read_sql(f"""
                SELECT TOP {int(_ANALYTICS_TOP_USERS)}
                    [user_email] AS [user_email],
                    COUNT(*)     AS [views]
                FROM {_ANALYTICS_TABLE}
                WHERE {s_where}
                GROUP BY [user_email]
                ORDER BY [views] DESC
            """, conn, params=s_params)
            user_rows = user_df.astype(object).where(pd.notnull(user_df), None).to_dict('records')
            by_user = [
                {
                    'user_email': r.get('user_email') if isinstance(r.get('user_email'), str) else None,
                    'views': int(r.get('views') or 0),
                }
                for r in user_rows
            ]

        # All-time distinct emails for the filter dropdown.
        emails_df = pd.read_sql(
            f"SELECT DISTINCT [user_email] FROM {_ANALYTICS_TABLE} "
            f"WHERE [user_email] IS NOT NULL ORDER BY [user_email]",
            conn,
        )
        known_emails = [e for e in emails_df['user_email'].tolist() if e]

        # Convert date objects to strings for JSON serialization
        for row in daily:
            if hasattr(row.get('date'), 'isoformat'):
                row['date'] = row['date'].isoformat()

        for key in ('first_visit', 'last_visit'):
            if hasattr(summary.get(key), 'isoformat'):
                summary[key] = summary[key].isoformat()
        for key in ('total_views', 'unique_visitors', 'unique_users'):
            if summary.get(key) is not None:
                summary[key] = int(summary[key])

        return jsonify({
            'success': True,
            'days': days,
            'email_mode': mode,
            'emails_filter': emails,
            'emails': known_emails,
            'tools_filter': tools_filter,
            'tool_mode': tool_mode,
            'summary': summary,
            'daily': daily,
            'by_tool': by_tool,
            'by_user': by_user,
            'details': details,
            'details_limit': int(_ANALYTICS_DETAIL_LIMIT),
            'details_truncated': bool(summary.get('total_views') or 0) and int(summary.get('total_views') or 0) > len(details),
        })

    except Exception as e:
        error_msg = str(e)
        print(f"⚠️  Analytics read error: {error_msg}")
        return jsonify({'success': False, 'error': error_msg}), 500


if __name__ == '__main__':
    print("=" * 60)
    print("🚀 Flask Backend Server Starting...")
    print(f"   Cache TTL: {CACHE_TTL_SECONDS}s")
    print(f"   Compression: {'enabled' if Compress is not None else 'disabled (install flask-compress)'}")
    print("=" * 60)
    print(f"Backend API: http://localhost:5000")
    print(f"Health Check: http://localhost:5000/api/health")
    print(f"All Metrics:  http://localhost:5000/api/all-metrics")
    print(f"KPI Metrics:  http://localhost:5000/api/kpi-metrics")
    print(f"Net Flows:    http://localhost:5000/api/net-flows")
    print(f"Analytics:    http://localhost:5000/api/analytics")
    print("=" * 60)
    app.run(debug=True, host='0.0.0.0', port=5000)
