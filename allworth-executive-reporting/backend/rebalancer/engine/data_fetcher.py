"""
Data fetching utilities for portfolio optimization data
"""

import os
import polars as pl
import asyncio
from typing import List, Dict, Optional, Any
import logging
from datetime import datetime, timedelta

from .cash_utils import canonicalize_sweep_cash_symbol, is_sweep_cash_symbol
from .target_allocation import calculate_effective_target_allocation_with_cash

logger = logging.getLogger(__name__)

DISALLOWED_TARGET_MODEL_SET = "AWF Equity"

# Try to import aioodbc for true async database operations
try:
    import aioodbc
    AIOODBC_AVAILABLE = True
except ImportError:
    AIOODBC_AVAILABLE = False
    logger.warning("aioodbc not available. Async SQL Server functionality will be limited.")

# Fallback to pyodbc if aioodbc not available
try:
    import pyodbc
    PYODBC_AVAILABLE = True
except ImportError:
    PYODBC_AVAILABLE = False
    logger.warning("pyodbc not available. SQL Server functionality will be limited.")


def _roll_up_sweep_cash_holdings(df: pl.DataFrame) -> pl.DataFrame:
    """Canonicalize known sweep-cash aliases into a single CASH holding."""
    if df is None or df.is_empty() or "Symbol" not in df.columns:
        return df

    if df.filter(
        pl.col("Symbol").map_elements(is_sweep_cash_symbol, return_dtype=pl.Boolean)
    ).is_empty():
        return df

    numeric_sum_cols = {
        "Shares",
        "Quantity",
        "Market Value",
        "Cost Basis",
        "Unrealized Gain Loss",
    }
    yes_no_cols = {
        "Exclude From Billing",
        "Exclude From Performance",
    }

    normalized = df.with_columns(
        pl.col("Symbol")
        .map_elements(canonicalize_sweep_cash_symbol, return_dtype=pl.Utf8)
        .alias("Symbol")
    )

    agg_exprs = []
    for col in normalized.columns:
        if col == "Symbol":
            continue
        if col in numeric_sum_cols:
            agg_exprs.append(pl.col(col).fill_null(0).sum().alias(col))
        elif col in yes_no_cols:
            agg_exprs.append(
                pl.when((pl.col(col).fill_null("No") == "Yes").any())
                .then(pl.lit("Yes"))
                .otherwise(pl.lit("No"))
                .alias(col)
            )
        else:
            agg_exprs.append(pl.col(col).drop_nulls().first().alias(col))

    rolled = normalized.group_by("Symbol").agg(agg_exprs).sort("Symbol")

    updates = []
    if "Asset Class" in rolled.columns:
        updates.append(
            pl.when(pl.col("Symbol") == "CASH")
            .then(pl.lit("Cash"))
            .otherwise(pl.col("Asset Class"))
            .alias("Asset Class")
        )
    if "Current Price" in rolled.columns:
        updates.append(
            pl.when(pl.col("Symbol") == "CASH")
            .then(pl.lit(1.0))
            .otherwise(pl.col("Current Price"))
            .alias("Current Price")
        )
    if "Security Type" in rolled.columns:
        updates.append(
            pl.when(pl.col("Symbol") == "CASH")
            .then(pl.lit("Cash"))
            .otherwise(pl.col("Security Type"))
            .alias("Security Type")
        )

    return rolled.with_columns(updates) if updates else rolled


def _normalize_sweep_cash_security_info(df: pl.DataFrame) -> pl.DataFrame:
    """Normalize sweep-cash aliases in security metadata to the canonical CASH symbol."""
    if df is None or df.is_empty() or "Symbol" not in df.columns:
        return df

    normalized = df.with_columns(
        pl.col("Symbol")
        .map_elements(canonicalize_sweep_cash_symbol, return_dtype=pl.Utf8)
        .alias("Symbol")
    )

    updates = []
    if "Asset Class" in normalized.columns:
        updates.append(
            pl.when(pl.col("Symbol") == "CASH")
            .then(pl.lit("Cash"))
            .otherwise(pl.col("Asset Class"))
            .alias("Asset Class")
        )
    if "Category" in normalized.columns:
        updates.append(
            pl.when(pl.col("Symbol") == "CASH")
            .then(pl.lit("Cash"))
            .otherwise(pl.col("Category"))
            .alias("Category")
        )
    if "Security Description" in normalized.columns:
        updates.append(
            pl.when(pl.col("Symbol") == "CASH")
            .then(pl.lit("Cash"))
            .otherwise(pl.col("Security Description"))
            .alias("Security Description")
        )
    if "Security Type" in normalized.columns:
        updates.append(
            pl.when(pl.col("Symbol") == "CASH")
            .then(pl.lit("Cash"))
            .otherwise(pl.col("Security Type"))
            .alias("Security Type")
        )
    if "Current Price" in normalized.columns:
        updates.append(
            pl.when(pl.col("Symbol") == "CASH")
            .then(pl.lit(1.0))
            .otherwise(pl.col("Current Price"))
            .alias("Current Price")
        )

    if updates:
        normalized = normalized.with_columns(updates)

    temp_cols = []
    if "Rebalance Category" in normalized.columns:
        normalized = normalized.with_columns(
            pl.when(pl.col("Rebalance Category").cast(pl.Utf8).str.strip_chars().fill_null("") == "")
            .then(pl.lit(None))
            .otherwise(pl.col("Rebalance Category"))
            .alias("Rebalance Category")
        )
        normalized = normalized.with_columns(
            pl.col("Rebalance Category").is_not_null().cast(pl.Int8).alias("__has_rebalance_category")
        )
        temp_cols.append("__has_rebalance_category")
        normalized = normalized.sort(
            ["Symbol", "__has_rebalance_category"],
            descending=[False, True],
        )

    agg_exprs = []
    for col in normalized.columns:
        if col == "Symbol" or col in temp_cols:
            continue
        agg_exprs.append(pl.col(col).drop_nulls().first().alias(col))

    return normalized.group_by("Symbol", maintain_order=True).agg(agg_exprs).sort("Symbol")

class DataFetcher:
    """Fetches data from SQL Server and other sources using async aioodbc"""

    def __init__(self, connection_string: str = None):
        """Initialize data fetcher with database connection"""

        if connection_string:
            self.connection_string = connection_string
        else:
            # Build connection string from environment variables for Azure Synapse
            server = os.environ.get('SQL_SERVER')
            database = os.environ.get('SQL_DATABASE')
            username = os.environ.get('SQL_USERNAME')
            password = os.environ.get('SQL_PASSWORD')

            # Azure Synapse optimized connection string
            self.connection_string = (
                f"DRIVER={{ODBC Driver 18 for SQL Server}};"
                f"SERVER=tcp:{server},1433;"
                f"DATABASE={database};"
                f"UID={username};"
                f"PWD={password};"
                f"Encrypt=yes;"
                f"TrustServerCertificate=no;"
                f"Connection Timeout=30;"
            )

    async def sql_query(self, query: str) -> pl.DataFrame:
        """Execute SQL query and return as Polars DataFrame using aioodbc"""

        logger.info(f"📊 Executing SQL query: {query[:100]}{'...' if len(query) > 100 else ''}")

        # Try aioodbc first (true async) - create connection per query to avoid event loop issues
        if AIOODBC_AVAILABLE:
            return await self._sql_query_aioodbc(query)

        # Fallback to pyodbc with thread executor
        if PYODBC_AVAILABLE:
            return await self._sql_query_pyodbc(query)

        logger.warning("⚠️ No database driver available. Returning empty DataFrame.")
        return pl.DataFrame()

    async def _sql_query_aioodbc(self, query: str) -> pl.DataFrame:
        """Execute SQL query using aioodbc (true async) - connection per query"""
        try:
            # Create connection per query to avoid event loop issues with asyncio.run()
            async with aioodbc.connect(dsn=self.connection_string, autocommit=True) as conn:
                async with conn.cursor() as cursor:
                    logger.debug(f"📝 Executing query: {query}")
                    await cursor.execute(query)

                    # Get column names
                    columns = [column[0] for column in cursor.description]
                    logger.debug(f"📋 Query columns: {columns}")

                    # Fetch all rows
                    rows = await cursor.fetchall()
                    logger.info(f"✅ Query returned {len(rows)} rows")

                    if not rows:
                        return pl.DataFrame()

                    # Convert rows to list of lists (aioodbc returns Row objects)
                    data = [[value for value in row] for row in rows]

                    return pl.DataFrame(data, schema=columns, orient='row')

        except Exception as e:
            logger.error(f"❌ aioodbc SQL query error: {e}")
            logger.error(f"❌ Error type: {type(e).__name__}")
            self._log_sanitized_connection_string()
            raise

    async def _sql_query_pyodbc(self, query: str) -> pl.DataFrame:
        """Execute SQL query using pyodbc with thread executor (fallback)"""

        loop = asyncio.get_event_loop()

        def _execute():
            try:
                logger.info(f"🔌 Connecting to Azure Synapse (pyodbc fallback)")

                conn = pyodbc.connect(self.connection_string)
                conn.autocommit = True
                logger.info("✅ Successfully connected to database")

                cursor = conn.cursor()
                cursor.execute(query)

                columns = [column[0] for column in cursor.description]
                rows = cursor.fetchall()
                logger.info(f"✅ Query returned {len(rows)} rows")

                data = [dict(zip(columns, row)) for row in rows]

                cursor.close()
                conn.close()

                return pl.DataFrame(data) if data else pl.DataFrame()

            except Exception as e:
                logger.error(f"❌ pyodbc SQL query error: {e}")
                raise

        return await loop.run_in_executor(None, _execute)

    def _log_sanitized_connection_string(self):
        """Log connection string with password masked"""
        try:
            sanitized = self.connection_string
            if 'PWD=' in sanitized:
                parts = sanitized.split('PWD=')
                if len(parts) > 1:
                    password_part = parts[1].split(';')[0]
                    sanitized = sanitized.replace(password_part, '***')
            logger.error(f"🔗 Connection string (sanitized): {sanitized}")
        except:
            logger.error("🔗 Connection string sanitization failed")

    async def get_upload_account_id(self, account_number: str, force_refresh: bool = False) -> tuple[str, str, float, float, str, str, str, bool]:
        """Get Tamarac upload account ID, strategy, value, cash reserve, custodian, email, owner ID, and taxable flag.

        OPTIMIZED: Results are cached for 60 seconds to reduce repeated database calls

        Args:
            account_number: The account number to look up
            force_refresh: If True, bypasses cache and fetches fresh data from DB
        """
        from .async_utils import account_cache

        cache_key = f'upload_account:{account_number}'

        # Check cache first (unless force_refresh)
        if not force_refresh:
            cached = account_cache.get(cache_key)
            if cached is not None:
                logger.debug(f"📦 Cache hit for account {account_number}")
                return cached

        logger.info(f"🔍 Looking up upload account ID for account: {account_number}")

        query = f"""
            SELECT TOP 1
                A.[Upload_Account_ID] AS [Upload Account ID],
                A.[Rebalancing_Model_Name] AS [Current Strategy],
                A.[Total_Account_Value] AS [Total Account Value],
                A.[Total_Cash_Reserve_Goal_Dollar] AS [Cash Reserve],
                A.[Custodian] AS [Custodian],
                A.[sf_advisor_email] AS [Email],
                U.[User_Id] AS [OwnerID],
                A.[Taxable] AS [Taxable]
            FROM [tho].[Current_Account_Demographic] AS A
            LEFT JOIN [tho].[User] AS U
            ON U.[email] = A.[sf_advisor_email]
            WHERE A.[Account_Number] = '{account_number.replace("'", "''")}'
        """

        logger.debug(f"📊 SQL Query: {query}")

        try:
            df = await self.sql_query(query)
            logger.debug(f"📊 Query returned DataFrame with columns: {df.columns if df.columns else 'Empty'}")

            if df.is_empty():
                logger.warning(f"⚠️ Account {account_number} not found in database")
                raise ValueError(f"Account {account_number} not found")

            upload_id = df['Upload Account ID'][0]

            # Safely extract current strategy
            if 'Current Strategy' in df.columns:
                current_strategy = df['Current Strategy'][0]
                # Handle None/null values
                if current_strategy is None or str(current_strategy).lower() in ['none', 'null', '']:
                    current_strategy = None
            else:
                logger.warning("⚠️ 'Current Strategy' column not found in query results")
                current_strategy = None

            if 'Total Account Value' in df.columns:
                total_account_value = df['Total Account Value'][0]
                # Handle None/null values
                if total_account_value is None:
                    total_account_value = None
            else:
                logger.warning("⚠️ 'Total Account Value' column not found in query results")
                total_account_value = None

            if 'Cash Reserve' in df.columns:
                cash_reserve = df['Cash Reserve'][0]
                # Handle None/null values
                if cash_reserve is None:
                    cash_reserve = None
            else:
                logger.warning("⚠️ 'Cash Reserve' column not found in query results")
                cash_reserve = None

            if 'Custodian' in df.columns:
                custodian = df['Custodian'][0]
                if custodian is None or str(custodian).strip().lower() in ('none', 'null', ''):
                    custodian = None
            else:
                logger.warning("⚠️ 'Custodian' column not found in query results")
                custodian = None

            if 'Email' in df.columns:
                email = df['Email'][0]
                # Account email should be non-null
                if not email or str(email).strip().lower() in ('none', 'null', ''):
                    logger.error(f"❌ Email is missing for account {account_number}")
                    raise ValueError(f"Email not found for account {account_number}")
            else:
                logger.error("❌ 'Email' column not found in query results")
                raise ValueError("Email column missing from database query")

            if 'OwnerID' in df.columns:
                owner_id = df['OwnerID'][0]
                # Validate owner_id is present
                if owner_id is None or str(owner_id).strip().lower() in ('none', 'null', ''):
                    logger.error(f"❌ OwnerID is missing for account {account_number}")
                    raise ValueError(f"OwnerID not found for account {account_number}")
            else:
                logger.error("❌ 'OwnerID' column not found in query results")
                raise ValueError("OwnerID column missing from database query")

            if 'Taxable' in df.columns:
                taxable_raw = df['Taxable'][0]
                is_taxable = str(taxable_raw).strip().lower() == 'yes' if taxable_raw else False
            else:
                logger.warning("⚠️ 'Taxable' column not found in query results")
                is_taxable = False

            logger.info(f"✅ Upload account ID: {upload_id} for account {account_number}")
            logger.debug(
                f"   Current Strategy: {current_strategy or 'Not set'}, "
                f"Value: {total_account_value or 'Not set'}, "
                f"Custodian: {custodian or 'Not set'}, Taxable: {is_taxable}"
            )

            # Cache the result
            result = (
                upload_id, current_strategy, total_account_value, cash_reserve,
                custodian, email, owner_id, is_taxable
            )
            account_cache.set(cache_key, result)

            return result

        except Exception as e:
            logger.error(f"❌ Error in get_upload_account_id: {e}")
            logger.error(f"❌ Error type: {type(e).__name__}")
            raise



    async def get_validation_email(self, sf_account_email: str) -> list[str]:
        """Get list of emails that have access to view the account.

        Returns:
            list of allowed viewer email addresses (empty on error or not found)

        OPTIMIZED: Result is cached in account_cache (60 s TTL) to avoid a
        repeated tho.RLS round-trip on every access check within the same request
        cycle.
        """

        logger.info("🔎 Fetching allowed viewer emails for owner: %s", sf_account_email)

        if not sf_account_email:
            logger.error("❌ No account email provided")
            return []

        from .async_utils import account_cache

        cache_key = f'validation_emails:{sf_account_email}'
        cached = account_cache.get(cache_key)
        if cached is not None:
            logger.debug("📦 Cache hit for validation emails: %s", sf_account_email)
            return cached

        query = f"""
            SELECT [email], [ViewAccess1], [ViewAccess2], [ViewAccess3], [ViewAccess4]
            FROM [tho].[RLS]
            WHERE [email] = '{sf_account_email.replace("'", "''")}'
        """

        try:
            df = await self.sql_query(query)
        except Exception as e:
            logger.error(f"❌ Database error fetching RLS: {e}")
            return []

        if df is None or df.is_empty():
            logger.warning(f"⚠️ RLS row not found for email: {sf_account_email}")
            account_cache.set(cache_key, [])
            return []

        # Take the first row (assuming one row per owner email)
        row = df.row(0)

        # Convert entire row to list of emails
        collected = list(row)

        # Normalize: lowercase, strip, remove nulls/empties
        cleaned = [
            str(e).strip().lower()
            for e in collected
            if e and str(e).strip().lower() not in ("null", "none", "nan", "")
        ]

        logger.debug("📬 Raw row values: %s", collected)
        logger.info("✅ Allowed viewers for %s: %s", sf_account_email, cleaned)
        account_cache.set(cache_key, cleaned)
        return cleaned


    async def check_mock_rebalancer_training(self, user_email: str) -> bool:
        """Check if the user has completed Mock Rebalancer training.

        Returns True when [Complete_Mock_Rebalancer_Training] = 1 in tho.RLS
        for the given user email, False otherwise.

        OPTIMIZED: Result is cached in account_cache (60 s TTL) so repeated
        requests within the same minute skip the database round-trip.
        """
        if not user_email:
            logger.warning("⚠️ check_mock_rebalancer_training called with empty email")
            return False

        from .async_utils import account_cache

        cache_key = f'training_check:{user_email}'
        cached = account_cache.get(cache_key)
        if cached is not None:
            logger.debug(f"📦 Cache hit for Mock Rebalancer training check: {user_email}")
            return cached

        query = f"""
            SELECT TOP 1 [Complete_Mock_Rebalancer_Training]
            FROM [tho].[RLS]
            WHERE [email] = '{user_email.replace("'", "''")}'
        """

        try:
            df = await self.sql_query(query)
        except Exception as e:
            logger.error(f"❌ Database error checking Mock Rebalancer training for {user_email}: {e}")
            return False

        if df is None or df.is_empty():
            logger.warning(f"⚠️ No RLS row found for user: {user_email}")
            account_cache.set(cache_key, False)
            return False

        value = df["Complete_Mock_Rebalancer_Training"][0]
        is_trained = str(value).strip() == "1" if value is not None else False
        logger.info(f"{'✅' if is_trained else '❌'} Mock Rebalancer training status for {user_email}: {is_trained}")
        account_cache.set(cache_key, is_trained)
        return is_trained

    async def get_target_allocations(self) -> Dict[str, Any]:
        """Get list of available target allocation models with model names and allocations"""

        logger.info("📈 Fetching available target allocation models")

        disallowed_model_set = DISALLOWED_TARGET_MODEL_SET.replace("'", "''")
        query = f"""
            SELECT DISTINCT [Model Name] AS [Model Name], [Allocation] AS [Allocation]
            FROM [tho].[Model_List]
            WHERE COALESCE([Model Set], '') <> '{disallowed_model_set}'
            ORDER BY [Model Name], [Allocation]
        """

        logger.debug(f"📊 SQL Query: {query}")
        df = await self.sql_query(query)

        # Handle empty DataFrame (when database is not available)
        if df.is_empty() or 'Model Name' not in df.columns or 'Allocation' not in df.columns:
            logger.warning("⚠️ No allocation data found or database unavailable")
            return {'model_names': [], 'allocations_by_model': {}}

        # Get unique model names
        model_names = sorted(df['Model Name'].unique().to_list())

        # Custom sort function for allocations (e.g., "60/40" -> sort by first number)
        def allocation_sort_key(allocation_str):
            """Sort allocations by the first number (equity allocation): 0/100, 10/90, ..., 100/0"""
            try:
                # Extract first number from allocation string (e.g., "60/40" -> 60)
                first_num = int(allocation_str.split('/')[0])
                return first_num
            except (ValueError, IndexError):
                # If parsing fails, return large number to sort to end
                return 999

        # Build allocations grouped by model in a single pass.
        allocations_by_model = {}
        for model, allocations_df in df.group_by('Model Name', maintain_order=True):
            model_key = model[0] if isinstance(model, tuple) else model
            allocations = allocations_df['Allocation'].to_list()
            allocations_by_model[model_key] = sorted(allocations, key=allocation_sort_key)

        logger.info(f"✅ Found {len(model_names)} model names with allocations")
        return {
            'model_names': model_names,
            'allocations_by_model': allocations_by_model
        }

    async def get_target_name(self, model: str, allocation: str) -> Optional[str]:
        """Get the full allocation model name from model name and allocation

        OPTIMIZED: Results cached for 5 minutes (allocations_cache) since model
        names rarely change.
        """
        from .async_utils import allocations_cache

        cache_key = f'target_name:no_awf_equity:{model}:{allocation}'
        cached = allocations_cache.get(cache_key)
        if cached is not None:
            logger.debug(f"📦 Cache hit for target name {model} - {allocation}")
            return cached

        logger.info(f"📈 Fetching allocation model name for: {model} - {allocation}")

        disallowed_model_set = DISALLOWED_TARGET_MODEL_SET.replace("'", "''")
        query = f"""
            SELECT [Allocation Model Name] AS [Allocation Model Name]
            FROM [tho].[Model_List]
            WHERE [Model Name] = '{model.replace("'", "''")}'
            AND [Allocation] = '{allocation.replace("'", "''")}'
            AND COALESCE([Model Set], '') <> '{disallowed_model_set}'
        """

        logger.debug(f"📊 SQL Query: {query}")
        df = await self.sql_query(query)

        # Handle empty DataFrame (when database is not available)
        if df.is_empty() or 'Allocation Model Name' not in df.columns:
            logger.warning("⚠️ No allocation model name found or database unavailable")
            return None

        allocation_name = df['Allocation Model Name'][0]
        allocations_cache.set(cache_key, allocation_name)
        logger.info(f"✅ Found allocation model name: {allocation_name}")
        return allocation_name


    async def get_target_allocation_details(self, model_name: str) -> Dict[str, Any]:
        """Get detailed target allocation with securities and asset class breakdown

        OPTIMIZED: Results cached for 10 minutes (allocation_details_cache) since
        target allocation weights change infrequently.
        """
        from .async_utils import allocation_details_cache

        cache_key = f'target_details:{model_name}'
        cached = allocation_details_cache.get(cache_key)
        if cached is not None:
            logger.debug(f"📦 Cache hit for allocation details: {model_name}")
            return cached

        logger.info(f"📊 Fetching detailed allocation for model: {model_name}")

        # Get target allocation weights with security info
        query = f"""
            SELECT DISTINCT TOP 1000
                A.[Ticker] AS [Symbol],
                B.[Security_Description] AS [Security Name],
                CAST(A.[Weight] AS FLOAT) AS [Target Weight],
                B.[Asset_Class] AS [Asset Class],
                B.[Rebalance_Category] AS [Rebalance Category],
                B.[Subsector] AS [Subsector],
                C.[Broad Category] AS [Category]
            FROM [tho].[Asset_Allocation_Security_Weights] AS A
            LEFT JOIN [tav].[Security_Info] AS B ON A.[Ticker] = B.[Symbol]
			LEFT JOIN [tav].[Fund_Substitutes] AS C ON A.[Ticker] = C.[Symbol]
            WHERE A.[Allocation Model Name] = '{model_name.replace("'", "''")}'
            AND A.[Weight] IS NOT NULL
            AND A.[Weight] > 0
            ORDER BY A.[Weight] DESC
        """

        logger.debug(f"📊 SQL Query: {query}")

        try:
            df = await self.sql_query(query)

            if df.is_empty():
                logger.warning(f"⚠️ No allocation details found for: {model_name}")
                return {'securities': [], 'assetClasses': {}}

            rows = df.iter_rows(named=True)
            securities = []
            asset_class_totals = {}

            for row in rows:
                symbol = row.get('Symbol')
                weight = float(row.get('Target Weight', 0)) * 100
                asset_class = row.get('Asset Class') or 'Unclassified'
                securities.append({
                    'symbol': symbol,
                    'name': row.get('Security Name', symbol),
                    'weight': weight,
                    'assetClass': asset_class,
                    'category': row.get('Category', '')
                })
                asset_class_totals[asset_class] = asset_class_totals.get(asset_class, 0.0) + weight

            logger.info(f"✅ Loaded {len(securities)} securities across {len(asset_class_totals)} asset classes")

            result = {
                'securities': securities,
                'assetClasses': asset_class_totals
            }
            allocation_details_cache.set(cache_key, result)
            return result

        except Exception as e:
            logger.error(f"❌ Failed to fetch allocation details for {model_name}: {e}", exc_info=True)
            return {'securities': [], 'assetClasses': {}}

    async def get_effective_target_allocation_details(
        self,
        model_name: str,
        budget_value: float,
        cash_reserve: float = None,
        carve_out: float = 0.0,
        minimum_cash_percent: float = 0.02
    ) -> Dict[str, Any]:
        """
        Get target allocation details adjusted for cash reserves and carve-outs.

        Uses the shared utility function calculate_effective_target_allocation_with_cash()
        from optimizer.py to ensure consistent calculations across UI and optimization.

        Args:
            model_name: Name of the target allocation model
            budget_value: Total portfolio value
            cash_reserve: Dollar amount to reserve as cash (optional)
            carve_out: Dollar amount carved out (e.g., for distribution)
            minimum_cash_percent: Minimum cash % if no reserve specified (default 2%)

        Returns:
            Dict with 'securities' and 'assetClasses' adjusted for cash requirements
        """
        logger.info(f"📊 Calculating effective allocation for {model_name} with cash adjustments")
        budget_value = float(budget_value or 0.0)
        cash_reserve = float(cash_reserve) if cash_reserve is not None else None
        carve_out = float(carve_out or 0.0)
        logger.debug(f"   Budget: ${budget_value:,.2f}, Reserve: ${cash_reserve or 0:,.2f}, Carve-out: ${carve_out:,.2f}")

        # Get base target allocation from database
        base_data = await self.get_target_allocation_details(model_name)

        if not base_data['securities']:
            return base_data

        if budget_value <= 0:
            logger.warning(f"⚠️ Budget value is zero or negative: ${budget_value:,.2f}")
            return base_data

        # Convert securities list to Polars DataFrame for the shared function
        # Note: weights in base_data are already percentages (e.g., 60.0), need to convert to decimals
        target_df_data = []
        for sec in base_data['securities']:
            if sec['symbol'] != 'CASH':  # Exclude CASH if it exists
                target_df_data.append({
                    'Symbol': sec['symbol'],
                    'Target Weight': sec['weight'] / 100.0  # Convert percentage to decimal
                })

        if not target_df_data:
            logger.warning("No non-cash securities found in target allocation")
            return base_data

        target_df = pl.DataFrame(target_df_data)

        # Use the shared utility function from optimizer.py
        adjusted_df, cash_floor_dollars = calculate_effective_target_allocation_with_cash(
            target_allocation=target_df,
            budget_value=budget_value,
            cash_reserve=cash_reserve,
            carve_out=carve_out,
            minimum_cash_percent=minimum_cash_percent
        )

        logger.debug(f"💰 Cash floor: ${cash_floor_dollars:,.2f}")

        # Convert adjusted Polars DataFrame back to dict format for UI
        adjusted_securities = []
        adjusted_asset_classes = {}
        base_security_lookup = {
            sec['symbol']: (
                sec.get('assetClass', 'Unclassified'),
                sec.get('category', ''),
                sec.get('name', sec.get('symbol', ''))
            )
            for sec in base_data['securities']
        }

        logger.debug(f"📋 Processing {len(adjusted_df)} securities from adjusted allocation")

        for row in adjusted_df.iter_rows(named=True):
            symbol = row['Symbol']
            weight_decimal = row['Target Weight']
            weight_percent = weight_decimal * 100.0  # Convert back to percentage

            # Get asset class and category from original data
            asset_class = 'Cash'
            category = 'Cash'
            name = 'Cash'

            if symbol != 'CASH':
                asset_class, category, name = base_security_lookup.get(
                    symbol,
                    ('Unclassified', '', symbol)
                )

            adjusted_securities.append({
                'symbol': symbol,
                'name': name,
                'weight': weight_percent,
                'assetClass': asset_class,
                'category': category
            })

            # Log each security for debugging
            if symbol == 'CASH' or asset_class == 'Cash':
                logger.debug(f"   💵 {symbol}: {weight_percent:.4f}% (asset class: {asset_class})")

            # Aggregate by asset class
            if asset_class not in adjusted_asset_classes:
                adjusted_asset_classes[asset_class] = 0.0
            adjusted_asset_classes[asset_class] += weight_percent

        # Use the aggregated cash weight from the normalized DataFrame
        # (not recalculated from cash_floor_dollars, as normalization may adjust it)
        cash_weight_percent = adjusted_asset_classes.get('Cash', 0.0)

        # Log totals for verification
        total_securities_weight = sum([s['weight'] for s in adjusted_securities])
        total_asset_class_weight = sum(adjusted_asset_classes.values())
        logger.debug(f"📊 Total securities weight: {total_securities_weight:.4f}%")
        logger.debug(f"📊 Total asset class weight: {total_asset_class_weight:.4f}%")

        logger.info(f"✅ Effective allocation: {len(adjusted_securities)} securities, cash={cash_weight_percent:.2f}%")
        logger.debug(f"   Asset classes: {', '.join([f'{ac}: {w:.2f}%' for ac, w in adjusted_asset_classes.items()])}")

        return {
            'securities': adjusted_securities,
            'assetClasses': adjusted_asset_classes,
            'cashReserve': cash_floor_dollars,
            'cashWeight': cash_weight_percent,
            'budgetValue': budget_value  # Total portfolio value used for target calculations
        }

    async def get_target_allocation(self, model_name: str) -> pl.DataFrame:
        """Get target allocation weights for a model"""

        logger.info(f"📊 Fetching allocation details for model: {model_name}")

        # Azure Synapse optimized query with correct column names
        query = f"""
            SELECT TOP 1000
                [Ticker] AS [Symbol],
                CAST([Weight] AS FLOAT) AS [Target Weight]
            FROM [tho].[Asset_Allocation_Security_Weights]
            WHERE [Allocation Model Name] = '{model_name.replace("'", "''")}'
            AND [Weight] IS NOT NULL
            AND [Weight] > 0
            ORDER BY [Weight] DESC
        """

        logger.debug(f"📊 SQL Query: {query}")

        try:
            df = await self.sql_query(query)
            logger.info(f"✅ Found {len(df)} positions for model: {model_name}")
            return df
        except Exception as e:
            logger.error(f"❌ Failed to fetch allocation for {model_name}: {e}")
            # Return empty DataFrame on error
            return pl.DataFrame()

    async def get_target_allocation_metadata(self, model_name: str) -> Dict[str, Any]:
        """Get target allocation model metadata for Salesforce payload"""

        logger.info(f"📊 Fetching allocation metadata for model: {model_name}")

        # First try to get metadata from allocation weights table
        query = f"""
            SELECT [Model Set] AS [Model Set], 
                   [Model Type] AS [Model Type], 
                   [Portfolio Allocation] AS [Portfolio Allocation]
            FROM [tho].[Model_List] AS A
            WHERE A.[Allocation Model Name] = '{model_name.replace("'", "''")}'
        """

        logger.debug(f"📊 SQL Query: {query}")

        try:
            df = await self.sql_query(query)

            if df is None or df.is_empty():
                logger.warning(f"⚠️ No allocation data found for model: {model_name}")
                return self._get_default_model_metadata(model_name)

            # Use the database results
            row = df.to_dicts()[0]
            metadata = {
                "Model Type": row.get("Model Type", None),
                "Model Set": row.get("Model Set", None),
                "Portfolio Allocation": row.get("Portfolio Allocation", None)
            }
            logger.info(f"✅ Retrieved model metadata from database: {metadata}")
            return metadata

        except Exception as e:
            logger.error(f"❌ Failed to fetch metadata for {model_name}: {e}")
            return self._get_default_model_metadata(model_name)

    def _get_default_model_metadata(self, model_name: str) -> Dict[str, Any]:
        """Get default model metadata when database lookup fails"""

        return {
            "Model Type": None,
            "Model Set": None,
            "Portfolio Allocation": None
        }

    async def get_portfolio_from_db(self, upload_account_id: str) -> pl.DataFrame:
        """Get portfolio holdings from database"""

        logger.info(f"📈 Fetching portfolio for upload account ID: {upload_account_id}")

        query = f"""
        SELECT
                [Symbol] AS [Symbol],
                CAST([Quantity] AS FLOAT) AS [Shares],
                CAST([Quantity] AS FLOAT) AS [Quantity],
                CAST([Total_Account_Value] AS FLOAT) AS [Market Value],
                CAST([Cost_Basis] AS FLOAT) AS [Cost Basis],
                CAST([Current_Price] AS FLOAT) AS [Current Price],
                CAST([Total_Unrealized_Gain_Loss] AS FLOAT) AS [Unrealized Gain Loss],
                [Security_Type] AS [Security Type],
                [Asset_Class] AS [Asset Class],
                [Exclude_From_Billing] AS [Exclude From Billing],
                [Exclude_From_Performance] AS [Exclude From Performance],
                [Restriction_Type] AS [Restriction Type],
                [Subsector] AS [Subsector],
                [Rebalance_Category] AS [Rebalance Category]
            FROM [tho].[Account_Daily_Holdings]
            WHERE [avaccountuploadid] = '{upload_account_id}' and [Total_Account_Value] > 0
            ORDER BY [Symbol]

        """

        logger.debug(f"📊 SQL Query: {query}")
        df = await self.sql_query(query)
        df = _roll_up_sweep_cash_holdings(df)
        logger.info(f"✅ Found {len(df)} portfolio positions")
        return df


    async def _fetch_substitute_rows(
        self,
        upload_account_id: str,
        target_allocation: str,
    ) -> pl.DataFrame:
        """Run the 3-source ranked substitute query and return the raw result.

        Result columns: [Ticker] (target model symbol), [Substitute] (held symbol),
        [Ranking], and [Is Default].  [Is Default] is 1 when the pair exists
        in tav.Security_Substitutes, even if the same pair also appears in an
        account-specific source.
        When the same (Ticker, Substitute) pair appears in multiple sources the
        highest Ranking is kept via MAX().  Results are cached per account+model.
        """
        from .async_utils import allocations_cache

        cache_key = f'subs_raw:{upload_account_id}:{target_allocation}'
        cached = allocations_cache.get(cache_key)
        if cached is not None:
            logger.debug(f"📦 Cache hit for raw substitutes: {upload_account_id}")
            return cached

        esc_account = str(upload_account_id).replace("'", "''")
        esc_target  = str(target_allocation).replace("'", "''")

        # ── Toggle: set to True to include Alternative Sets as a substitute source ──
        USE_ALTERNATIVE_SETS = False
        alt_sets_clause = f"""
                UNION ALL

                SELECT B.[Symbol]               AS [Ticker],
                       B.[Substitute_Symbol]   AS [Substitute],
                       ROW_NUMBER() OVER (
                           PARTITION BY A.[Alternate_Security_Set_Name]
                           ORDER BY B.[Symbol_Rank] DESC
                       ) + 2                    AS [Ranking],
                       0                        AS [Is Default]
                FROM [tav].[Alternative_Sets] AS A
                JOIN [tav].[Alternate_Set_Substitutes] AS B
                    ON  A.[Alternate_Security_Set_Name] = B.[Alternate_Security_Set_Name]
                    AND A.[Security_Level_Model_Name]   = B.[Model_Name]
                WHERE A.[Upload_Account_ID] = '{esc_account}'
                  AND B.[Symbol] IN (
                      SELECT [Ticker] FROM [tho].[Asset_Allocation_Security_Weights]
                      WHERE [Allocation Model Name] = '{esc_target}'
                  )
        """ if USE_ALTERNATIVE_SETS else ""

        query = f"""
            WITH all_subs AS (
                SELECT [Ticker],
                       [Substitute],
                       1 AS [Ranking],
                       1 AS [Is Default]
                FROM [tav].[Security_Substitutes]
                WHERE [Ticker] IN (
                    SELECT [Ticker] FROM [tho].[Asset_Allocation_Security_Weights]
                    WHERE [Allocation Model Name] = '{esc_target}'
                )

                UNION ALL

                SELECT [Symbol]              AS [Ticker],
                       [Substitute_Symbol]  AS [Substitute],
                       2                    AS [Ranking],
                       0                    AS [Is Default]
                FROM [tav].[Account_Substitutes]
                WHERE [Upload_Account_ID] = '{esc_account}'
                  AND [Substitute_Symbol] != [Symbol]
                {alt_sets_clause}
            ),
            deduped AS (
                SELECT [Ticker],
                       [Substitute],
                       MAX([Ranking]) AS [Ranking],
                       MAX([Is Default]) AS [Is Default]
                FROM   all_subs
                WHERE  [Ticker]     IS NOT NULL
                  AND  [Substitute] IS NOT NULL
                  AND  [Ticker]     != [Substitute]
                GROUP BY [Ticker], [Substitute]
            )
            SELECT [Ticker], [Substitute], [Ranking], [Is Default]
            FROM   deduped
            ORDER BY [Substitute],
                     CASE WHEN [Is Default] = 1 THEN 0 ELSE 1 END,
                     [Ranking],
                     [Ticker]
        """

        logger.info(f"📈 Fetching substitutes for account {upload_account_id} / model '{target_allocation}'")
        df = await self.sql_query(query)
        logger.info(f"✅ Raw substitute rows: {len(df)}")
        allocations_cache.set(cache_key, df)
        return df

    async def get_substitutes_per_account(self, upload_account_id: str, target_allocation: str) -> pl.DataFrame:
        """Return substitute mappings as a DataFrame with columns
        [Substitute Symbol], [Symbol], [Ranking], [Is Default], [Upload Account ID]."""
        df = await self._fetch_substitute_rows(upload_account_id, target_allocation)
        if df is None or df.is_empty():
            return pl.DataFrame()
        return df.rename({"Substitute": "Substitute Symbol", "Ticker": "Symbol"}).with_columns(
            pl.lit(upload_account_id).alias("Upload Account ID")
        )

    async def get_substitutes_per_symbol(
        self,
        upload_account_id: str,
        target_allocation: str,
        portfolio_symbols: Optional[List[str]] = None,
    ) -> Dict[str, str]:
        """Return substitute mappings as {held_symbol: target_model_symbol}.

        If portfolio_symbols is provided only entries whose held symbol
        (Substitute column) appears in that list are included.
        """
        from .async_utils import allocations_cache

        normalize = lambda value: str(value or "").strip().upper()

        normalized_portfolio_symbols = sorted({
            normalize(sym) for sym in (portfolio_symbols or []) if normalize(sym)
        })
        cache_key = (
            f"subs_by_symbol:{upload_account_id}:{target_allocation}:"
            f"{'|'.join(normalized_portfolio_symbols) if normalized_portfolio_symbols else '*'}"
        )
        cached = allocations_cache.get(cache_key)
        if cached is not None:
            logger.debug(f"📦 Cache hit for symbol-level substitutes: {upload_account_id}")
            return cached

        raw_df = await self._fetch_substitute_rows(upload_account_id, target_allocation)
        if raw_df is None or raw_df.is_empty():
            allocations_cache.set(cache_key, {})
            return {}

        portfolio_symbol_set = set(normalized_portfolio_symbols)
        symbol_map: Dict[str, str] = {}
        if {"Is Default", "Ranking"}.issubset(set(raw_df.columns)):
            rows = raw_df.sort(["Is Default", "Ranking"], descending=[True, False]).iter_rows(named=True)
        elif "Ranking" in raw_df.columns:
            rows = raw_df.sort("Ranking").iter_rows(named=True)
        else:
            rows = raw_df.iter_rows(named=True)
        for row in rows:
            target_symbol = normalize(row.get("Ticker"))
            held_symbol   = normalize(row.get("Substitute"))
            if not target_symbol or not held_symbol:
                continue
            if portfolio_symbol_set and held_symbol not in portfolio_symbol_set:
                continue
            symbol_map.setdefault(held_symbol, target_symbol)

        logger.info(
            f"✅ Built {len(symbol_map)} symbol-level substitute mappings for account {upload_account_id}"
        )
        allocations_cache.set(cache_key, symbol_map)
        return symbol_map


    async def get_substitute_security_wash_sale(self, upload_account_id: str, target_allocation: str) -> pl.DataFrame:
        """Return standard substitute rows eligible for wash-sale replacement buys."""
        from .async_utils import allocations_cache

        cache_key = f"wash_sale_subs:{upload_account_id}:{target_allocation}"
        cached = allocations_cache.get(cache_key)
        if cached is not None:
            logger.debug(f"📦 Cache hit for wash-sale substitutes: {upload_account_id}")
            return cached

        esc_account = str(upload_account_id or "").replace("'", "''")
        esc_target = str(target_allocation or "").replace("'", "''")
        if not esc_target:
            empty = pl.DataFrame(
                schema={
                    "Ticker": pl.Utf8,
                    "Substitute": pl.Utf8,
                    "Ranking": pl.Int64,
                    "Is Default": pl.Int64,
                }
            )
            allocations_cache.set(cache_key, empty)
            return empty

        query = f"""
            SELECT S.[Ticker],
                   S.[Substitute],
                   1 AS [Ranking],
                   1 AS [Is Default],
                   TickerHolding.[Wash_Sale] AS [Ticker Wash Sale Blocked],
                   SubstituteHolding.[Wash_Sale] AS [Substitute Wash Sale Blocked]
            FROM [tav].[Security_Substitutes] AS S
            LEFT JOIN [tho].[Account_Daily_Holdings] AS TickerHolding
                ON S.[Ticker] = TickerHolding.[Symbol]
                AND TickerHolding.[avaccountuploadid] = '{esc_account}'
            LEFT JOIN [tho].[Account_Daily_Holdings] AS SubstituteHolding
                ON S.[Substitute] = SubstituteHolding.[Symbol]
                AND SubstituteHolding.[avaccountuploadid] = '{esc_account}'
            WHERE (
                S.[Ticker] IN (
                    SELECT [Ticker]
                    FROM [tho].[Asset_Allocation_Security_Weights]
                    WHERE [Allocation Model Name] = '{esc_target}'
                )
                OR S.[Substitute] IN (
                    SELECT [Ticker]
                    FROM [tho].[Asset_Allocation_Security_Weights]
                    WHERE [Allocation Model Name] = '{esc_target}'
                )
            )
              AND S.[Ticker] IS NOT NULL
              AND S.[Substitute] IS NOT NULL
              AND S.[Ticker] != S.[Substitute]
        """

        logger.info(
            f"🔍 Fetching wash-sale substitute securities for account {upload_account_id} / "
            f"model '{target_allocation}'"
        )
        logger.debug(f"📊 SQL Query: {query}")
        df = await self.sql_query(query)
        if df is None:
            df = pl.DataFrame(
                schema={
                    "Ticker": pl.Utf8,
                    "Substitute": pl.Utf8,
                    "Ranking": pl.Int64,
                    "Is Default": pl.Int64,
                }
            )
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "[WASH_SALE_DEBUG] get_substitute_security_wash_sale_result "
                f"upload_account_id={upload_account_id!r} target_allocation={target_allocation!r} "
                f"rows={df.to_dicts() if not df.is_empty() else []}"
            )
        logger.info(f"✅ Found {len(df)} wash-sale substitute row(s)")
        allocations_cache.set(cache_key, df)
        return df



    async def get_additional_security_info(self, upload_account_id: str, target_allocation: str) -> pl.DataFrame:
        """Get additional security information including wash sale and fractional share data"""

        logger.info(f"🔍 Fetching additional security info for account: {upload_account_id}")

        query = f"""
              WITH Combined AS
            (
                SELECT
                    A.[Symbol] AS [Symbol],
                    A.[Asset_Class] AS [Asset Class],
                    A.[Subsector] AS [Subsector],
                    A.[Current_Price] AS [Current Price],
                    A.[Security_Type] AS [Security Type],
                    A.[Security_Description] AS [Security Description],
                    B.[Broad Category] AS [Category],
                    A.[Wash_Sale] AS [Wash Sale Blocked],
                    A.[Rebalance_Category] AS [Rebalance Category],
                    A.[Rebalance_Category] AS [Account Rebalance Category],
                    NULL AS [Target Rebalance Category],
                    NULL AS [Security Info Rebalance Category],
                    'Account_Daily_Holdings' AS [Metadata Source],
                    CASE
                        WHEN A.[Security_Type] IN ('Mutual Funds')
                            OR A.[Security_Description] LIKE '%ETF%'
                        THEN 'Yes'
                        ELSE NULL
                    END AS [Allows Fractional],
                    CASE WHEN A.[Security_Restriction_Type] = 'Unmanaged' THEN 'Yes' ELSE 'No' END AS [Unmanaged]
                FROM [tho].[Account_Daily_Holdings] AS A
                LEFT JOIN [tav].[Fund_Substitutes] AS B
                    ON A.[Symbol] = B.[Symbol]
                WHERE A.[avaccountuploadid] = '{upload_account_id}'

                UNION ALL

                SELECT
                    A.[Ticker] AS [Symbol],
                    C.[Asset_Class] AS [Asset Class],
                    C.[Subsector] AS [Subsector],
                    C.[Current_Price] AS [Current Price],
                    C.[Security_Type] AS [Security Type],
                    C.[Security_Description] AS [Security Description],
                    B.[Broad Category] AS [Category],
                    NULL AS [Wash Sale Blocked],
                    C.[Rebalance_Category] AS [Rebalance Category],
                    NULL AS [Account Rebalance Category],
                    NULL AS [Target Rebalance Category],
                    C.[Rebalance_Category] AS [Security Info Rebalance Category],
                    'Target_Model/Security_Info' AS [Metadata Source],
                    CASE
                        WHEN C.[Security_Type] IN ('Mutual Funds')
                            OR C.[Security_Description] LIKE '%ETF%'
                        THEN 'Yes'
                        ELSE NULL
                    END AS [Allows Fractional],
                    CASE WHEN H.[Security_Restriction_Type] = 'Unmanaged' THEN 'Yes' ELSE 'No' END AS [Unmanaged]
                FROM [tho].[Asset_Allocation_Security_Weights] AS A
                LEFT JOIN [tav].[Fund_Substitutes] AS B
                    ON A.[Ticker] = B.[Symbol]
                LEFT JOIN [tav].[Security_Info] AS C
                    ON A.[Ticker] = C.[Symbol]
                LEFT JOIN [tho].[Account_Daily_Holdings] AS H
                    ON A.[Ticker] = H.[Symbol] AND H.[avaccountuploadid] = '{upload_account_id}'
                WHERE A.[Allocation Model Name] = '{target_allocation}'
                AND A.[Weight] IS NOT NULL
                AND H.[Symbol] IS NULL

                UNION ALL

                SELECT
                    S.[Substitute_Symbol] AS [Symbol],
                    C.[Asset_Class] AS [Asset Class],
                    C.[Subsector] AS [Subsector],
                    C.[Current_Price] AS [Current Price],
                    C.[Security_Type] AS [Security Type],
                    C.[Security_Description] AS [Security Description],
                    B.[Broad Category] as [Category],
                    NULL AS [Wash Sale Blocked],
                    C.[Rebalance_Category] AS [Rebalance Category],
                    NULL AS [Account Rebalance Category],
                    NULL AS [Target Rebalance Category],
                    C.[Rebalance_Category] AS [Security Info Rebalance Category],
                    'Account_Substitute/Security_Info' AS [Metadata Source],
                    CASE
                        WHEN C.[Security_Type] IN ('Mutual Funds')
                            OR C.[Security_Description] LIKE '%ETF%'
                        THEN 'Yes'
                        ELSE NULL
                    END AS [Allows Fractional],
                    CASE WHEN H.[Security_Restriction_Type] = 'Unmanaged' THEN 'Yes' ELSE 'No' END AS [Unmanaged]
                FROM [tav].[Account_Substitutes] AS S
                LEFT JOIN [tav].[Fund_Substitutes] AS B
                    ON S.[Substitute_Symbol] = B.[Symbol]
                LEFT JOIN [tav].[Security_Info] AS C
                    ON S.[Substitute_Symbol] = C.[Symbol]
                LEFT JOIN [tho].[Account_Daily_Holdings] AS H
                    ON S.[Substitute_Symbol] = H.[Symbol] AND H.[avaccountuploadid] = '{upload_account_id}'
                WHERE S.[Upload_Account_ID] = '{upload_account_id}'
                AND S.[Substitute_Symbol] IS NOT NULL
                AND S.[Symbol] IS NOT NULL
                AND S.[Substitute_Symbol] != S.[Symbol]

                UNION ALL

                SELECT
                    WS.[Ticker] AS [Symbol],
                    C.[Asset_Class] AS [Asset Class],
                    C.[Subsector] AS [Subsector],
                    C.[Current_Price] AS [Current Price],
                    C.[Security_Type] AS [Security Type],
                    C.[Security_Description] AS [Security Description],
                    B.[Broad Category] as [Category],
                    NULL AS [Wash Sale Blocked],
                    C.[Rebalance_Category] AS [Rebalance Category],
                    NULL AS [Account Rebalance Category],
                    NULL AS [Target Rebalance Category],
                    C.[Rebalance_Category] AS [Security Info Rebalance Category],
                    'Wash_Sale_Substitute/Security_Info' AS [Metadata Source],
                    CASE
                        WHEN C.[Security_Type] IN ('Mutual Funds')
                            OR C.[Security_Description] LIKE '%ETF%'
                        THEN 'Yes'
                        ELSE NULL
                    END AS [Allows Fractional],
                    CASE WHEN H.[Security_Restriction_Type] = 'Unmanaged' THEN 'Yes' ELSE 'No' END AS [Unmanaged]
                FROM [tav].[Security_Substitutes] AS WS
                LEFT JOIN [tav].[Fund_Substitutes] AS B
                    ON WS.[Ticker] = B.[Symbol]
                LEFT JOIN [tav].[Security_Info] AS C
                    ON WS.[Ticker] = C.[Symbol]
                LEFT JOIN [tho].[Account_Daily_Holdings] AS H
                    ON WS.[Ticker] = H.[Symbol] AND H.[avaccountuploadid] = '{upload_account_id}'
                WHERE WS.[Ticker] IS NOT NULL
                AND WS.[Substitute] IS NOT NULL
                AND WS.[Ticker] != WS.[Substitute]
                AND (
                    WS.[Ticker] IN (
                        SELECT [Ticker]
                        FROM [tho].[Asset_Allocation_Security_Weights]
                        WHERE [Allocation Model Name] = '{target_allocation}'
                    )
                    OR WS.[Substitute] IN (
                        SELECT [Ticker]
                        FROM [tho].[Asset_Allocation_Security_Weights]
                        WHERE [Allocation Model Name] = '{target_allocation}'
                    )
                )

                UNION ALL

                SELECT
                    WS.[Substitute] AS [Symbol],
                    C.[Asset_Class] AS [Asset Class],
                    C.[Subsector] AS [Subsector],
                    C.[Current_Price] AS [Current Price],
                    C.[Security_Type] AS [Security Type],
                    C.[Security_Description] AS [Security Description],
                    B.[Broad Category] as [Category],
                    NULL AS [Wash Sale Blocked],
                    C.[Rebalance_Category] AS [Rebalance Category],
                    NULL AS [Account Rebalance Category],
                    NULL AS [Target Rebalance Category],
                    C.[Rebalance_Category] AS [Security Info Rebalance Category],
                    'Wash_Sale_Substitute/Security_Info' AS [Metadata Source],
                    CASE
                        WHEN C.[Security_Type] IN ('Mutual Funds')
                            OR C.[Security_Description] LIKE '%ETF%'
                        THEN 'Yes'
                        ELSE NULL
                    END AS [Allows Fractional],
                    CASE WHEN H.[Security_Restriction_Type] = 'Unmanaged' THEN 'Yes' ELSE 'No' END AS [Unmanaged]
                FROM [tav].[Security_Substitutes] AS WS
                LEFT JOIN [tav].[Fund_Substitutes] AS B
                    ON WS.[Substitute] = B.[Symbol]
                LEFT JOIN [tav].[Security_Info] AS C
                    ON WS.[Substitute] = C.[Symbol]
                LEFT JOIN [tho].[Account_Daily_Holdings] AS H
                    ON WS.[Substitute] = H.[Symbol] AND H.[avaccountuploadid] = '{upload_account_id}'
                WHERE WS.[Ticker] IS NOT NULL
                AND WS.[Substitute] IS NOT NULL
                AND WS.[Ticker] != WS.[Substitute]
                AND (
                    WS.[Ticker] IN (
                        SELECT [Ticker]
                        FROM [tho].[Asset_Allocation_Security_Weights]
                        WHERE [Allocation Model Name] = '{target_allocation}'
                    )
                    OR WS.[Substitute] IN (
                        SELECT [Ticker]
                        FROM [tho].[Asset_Allocation_Security_Weights]
                        WHERE [Allocation Model Name] = '{target_allocation}'
                    )
                )
            )

            SELECT DISTINCT A.*, B.[Volatility]
            FROM Combined AS A
            JOIN [tav].[Asset_Class_Historical_Volatility] AS B
            ON A.[Asset Class] = B.[Asset Class]
        """

        logger.debug(f"📊 SQL Query: {query}")
        df = await self.sql_query(query)
        df = _normalize_sweep_cash_security_info(df)
        debug_logging = logger.isEnabledFor(logging.DEBUG) or os.environ.get(
            "TAX_TOOLS_MODEL_ASSIGNMENT_DEBUG", ""
        ).lower() in {"1", "true", "yes", "on"}
        if debug_logging and df is not None and not df.is_empty() and "Symbol" in df.columns:
            trace_rows = (
                df.with_columns(
                    pl.col("Symbol").cast(pl.Utf8).str.strip_chars().str.to_uppercase().alias("_symbol_upper")
                )
                .filter(pl.col("_symbol_upper") == "BND")
                .drop("_symbol_upper")
                .to_dicts()
            )
            if trace_rows:
                logger.debug(
                    "[MODEL_ASSIGNMENT_DEBUG] get_additional_security_info_trace "
                    f"upload_account_id={upload_account_id!r} target_allocation={target_allocation!r} "
                    f"rows={trace_rows}"
                )
        if df is not None and not df.is_empty() and "Rebalance Category" in df.columns:
            missing_rebalance = (
                df.with_columns([
                    pl.col("Symbol").cast(pl.Utf8).str.strip_chars().alias("_symbol"),
                    pl.col("Rebalance Category").cast(pl.Utf8).str.strip_chars().fill_null("").alias("_rebalance_category"),
                ])
                .filter(
                    (pl.col("_symbol") != "")
                    & (pl.col("_symbol") != "CASH")
                    & (pl.col("_rebalance_category") == "")
                )
                .select([
                    col for col in [
                        "Symbol", "Asset Class", "Category", "Security Type", "Security Description",
                        "Account Rebalance Category", "Target Rebalance Category",
                        "Security Info Rebalance Category", "Metadata Source",
                    ] if col in df.columns
                ])
                .to_dicts()
            )
            if missing_rebalance:
                logger.debug(
                    "[MODEL_ASSIGNMENT_DEBUG] get_additional_security_info_missing_rebalance_category "
                    f"symbols={missing_rebalance}"
                )
                logger.warning(
                    "Additional security info missing explicit Rebalance Category for symbols: "
                    f"{missing_rebalance}"
                )
        logger.info(f"✅ Found security info for {len(df)} symbols")
        return df

    async def get_salesforce_account_id(self, upload_account_id: str) -> Dict[str, str]:
        """Get Salesforce account mapping"""

        logger.info(f"🔍 Looking up Salesforce account ID for: {upload_account_id}")

        query = f"""
            SELECT
                A.[Id] AS [sf_fin_account_id],
                A.[Name] AS [sf_fin_account_name],
                A.[Model_Name__c] AS [Current_Model__c],
                A.[FinServ__Household__c] AS [Household__c],
                B.[Wealth_Opportunity__c] AS [Wealth_Opportunity__c]
            FROM [sfp].[FinServ__FinancialAccount__c] AS A
			JOIN [sfp].[Account] AS B
			ON A.[FinServ__Household__c] = B.[Id]
            WHERE A.[FinServ__FinancialAccountNumber__c] = '{upload_account_id}'
        """

        logger.debug(f"📊 SQL Query: {query}")
        df = await self.sql_query(query)

        if df.is_empty():
            logger.warning(f"⚠️ No Salesforce mapping found for account: {upload_account_id}")
            return None

        result = df.to_dicts()[0]
        if (
            "Wealth_Opportunity__c" not in result
            and "Wealth Opportunity__c" in result
        ):
            result["Wealth_Opportunity__c"] = result.get("Wealth Opportunity__c")
        logger.info(f"✅ Found Salesforce mapping: {result}")
        return result
