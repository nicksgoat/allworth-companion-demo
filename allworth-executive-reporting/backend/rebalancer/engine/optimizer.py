"""
Portfolio optimization engine using CVXPY convex optimization
"""

import cvxpy as cp
import numpy as np
import polars as pl
import logging
import datetime
import hashlib
import json
import os
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime as dt
import time
from collections import defaultdict

from .individual_stock_liquidation import (
    find_off_model_individual_stock_lots,
    find_off_category_legacy_lots,
)
from .target_allocation import calculate_effective_target_allocation_with_cash

logger = logging.getLogger(__name__)

DEFAULT_CAT = "Uncategorized"
OPTIMIZER_MODEL_ASSIGNMENT_VERSION = "rebalance-category-corridor-v2"


def _optimizer_diagnostics_enabled() -> bool:
    """Allow expensive console diagnostics only when explicitly enabled."""
    return os.environ.get("TAX_TOOLS_OPTIMIZER_DIAGNOSTICS", "").lower() in {"1", "true", "yes", "on"}


def _fingerprint_logging_enabled() -> bool:
    """Full-run fingerprinting is expensive; keep it opt-in."""
    return os.environ.get("TAX_TOOLS_OPTIMIZER_FINGERPRINT", "").lower() in {"1", "true", "yes", "on"}


def _multi_solver_compare_enabled() -> bool:
    """Run all fallback solvers and pick the best candidate when explicitly enabled."""
    return os.environ.get("TAX_TOOLS_MULTI_SOLVER_COMPARE", "").lower() in {"1", "true", "yes", "on"}


def _diagnostic_print(*args, **kwargs) -> None:
    """Log optimizer diagnostics only when explicitly requested."""
    if _optimizer_diagnostics_enabled():
        logger.info(" ".join(str(arg) for arg in args))


def _verbose_debug_logging_enabled() -> bool:
    return (
        logger.isEnabledFor(logging.DEBUG)
        or _optimizer_diagnostics_enabled()
        or os.environ.get("TAX_TOOLS_MODEL_ASSIGNMENT_DEBUG", "").lower() in {"1", "true", "yes", "on"}
    )


def _normalize_rebalance_category_for_tolerance(value: Any) -> str:
    """Normalize explicit Rebalance Category values used by model assignment."""
    category = str(value or "").strip().lower()
    if category == "equity":
        return "equity"
    if category in {"fixed", "fixed income"}:
        return "fixed income"
    return ""

# ============================================================================
# VALIDATION ERROR CLASS
# ============================================================================

class OptimizationValidationError(Exception):
    """Raised when optimization inputs fail validation."""
    
    def __init__(self, message: str, errors: List[str], suggestions: List[str] = None):
        self.message = message
        self.errors = errors
        self.suggestions = suggestions or []
        super().__init__(self.message)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'message': self.message,
            'errors': self.errors,
            'suggestions': self.suggestions
        }


# ============================================================================
# VALIDATION FUNCTIONS (Module-level for reuse)
# ============================================================================

def validate_portfolio_data(portfolio: pl.DataFrame) -> Tuple[bool, List[str], List[str]]:
    """
    Validate portfolio DataFrame has required columns and valid data.
    
    Returns:
        Tuple of (is_valid, errors_list, warnings_list)
    """
    errors = []
    warnings = []
    
    if portfolio is None:
        errors.append("Portfolio is None")
        return False, errors, warnings
    
    if len(portfolio) == 0:
        errors.append("Portfolio is empty (no positions)")
        return False, errors, warnings
    
    # Required columns
    required_cols = ['Symbol', 'Lot Quantity', 'Lot Cost Basis']
    missing_cols = [c for c in required_cols if c not in portfolio.columns]
    if missing_cols:
        errors.append(f"Missing required columns: {missing_cols}")
    
    # Check for NULL symbols
    if 'Symbol' in portfolio.columns:
        null_symbols = portfolio.filter(pl.col('Symbol').is_null())
        if len(null_symbols) > 0:
            errors.append(f"Found {len(null_symbols)} rows with NULL symbols")
    
    # Check for negative quantities
    if 'Lot Quantity' in portfolio.columns:
        neg_qty = portfolio.filter(pl.col('Lot Quantity') < 0)
        if len(neg_qty) > 0:
            bad_symbols = neg_qty['Symbol'].to_list()[:5]
            errors.append(f"Negative quantities for: {bad_symbols}")
    
    # Check for Current Price column (needed later)
    if 'Current Price' not in portfolio.columns:
        warnings.append("'Current Price' column missing - will be added from portfolio_info")
    else:
        # Check for NULL/zero prices (excluding CASH)
        bad_prices = portfolio.filter(
            (pl.col('Symbol') != 'CASH') & 
            ((pl.col('Current Price').is_null()) | (pl.col('Current Price') <= 0))
        )
        if len(bad_prices) > 0:
            bad_symbols = bad_prices['Symbol'].unique().to_list()[:5]
            warnings.append(f"Securities with NULL/zero prices: {bad_symbols}")
    
    return len(errors) == 0, errors, warnings


def validate_target_allocation(target_allocation: pl.DataFrame) -> Tuple[bool, List[str], List[str]]:
    """
    Validate target allocation DataFrame.
    
    Returns:
        Tuple of (is_valid, errors_list, warnings_list)
    """
    errors = []
    warnings = []
    
    if target_allocation is None:
        errors.append("Target allocation is None")
        return False, errors, warnings
    
    if len(target_allocation) == 0:
        errors.append("Target allocation is empty (no securities)")
        return False, errors, warnings
    
    # Required columns
    required_cols = ['Symbol', 'Target Weight']
    missing_cols = [c for c in required_cols if c not in target_allocation.columns]
    if missing_cols:
        errors.append(f"Missing required columns in target allocation: {missing_cols}")
        return False, errors, warnings
    
    # Check weights sum to ~1.0
    total_weight = float(target_allocation['Target Weight'].sum())
    if abs(total_weight - 1.0) > 0.05:
        warnings.append(f"Target weights sum to {total_weight:.4f}, not 1.0 - will be normalized")
    
    # Check for negative weights
    neg_weights = target_allocation.filter(pl.col('Target Weight') < 0)
    if len(neg_weights) > 0:
        errors.append(f"Negative target weights found for: {neg_weights['Symbol'].to_list()}")
    
    # Check for NaN weights
    nan_weights = target_allocation.filter(pl.col('Target Weight').is_nan())
    if len(nan_weights) > 0:
        errors.append(f"NaN target weights found for: {nan_weights['Symbol'].to_list()}")
    
    return len(errors) == 0, errors, warnings


def validate_tax_parameters(
    short_term_rate: float,
    long_term_rate: float,
    max_tax_bill: float,
    realized_gains_constraint: Optional[float]
) -> Tuple[bool, List[str], List[str]]:
    """
    Validate tax parameters are within reasonable bounds.
    
    Returns:
        Tuple of (is_valid, errors_list, warnings_list)
    """
    errors = []
    warnings = []
    
    # Tax rates should be between 0 and 1
    if not (0 <= short_term_rate <= 1):
        errors.append(f"Short-term tax rate {short_term_rate} must be between 0 and 1")
    
    if not (0 <= long_term_rate <= 1):
        errors.append(f"Long-term tax rate {long_term_rate} must be between 0 and 1")
    
    # Max tax bill should be non-negative
    if max_tax_bill < 0:
        errors.append(f"Max tax bill cannot be negative: {max_tax_bill}")
    
    # Warning if tax budget is very small
    if 0 < max_tax_bill < 100:
        warnings.append(f"Tax budget ${max_tax_bill:.2f} is very small - may limit rebalancing")
    
    # Realized gains constraint
    if realized_gains_constraint is not None and realized_gains_constraint < 0:
        errors.append(f"Realized gains constraint cannot be negative: {realized_gains_constraint}")
    
    return len(errors) == 0, errors, warnings


def check_feasibility(
    portfolio_value: float,
    cash_floor: float,
    max_tax_bill: float,
    total_unrealized_gains: float,
    short_term_rate: float,
    long_term_rate: float
) -> Tuple[bool, List[str], List[str]]:
    """
    Check if the optimization problem is likely feasible before running solver.
    
    This is a quick heuristic check - not a guarantee, but catches obvious issues.
    
    Returns:
        Tuple of (likely_feasible, issues_list, suggestions_list)
    """
    issues = []
    suggestions = []
    
    # 1. Cash floor cannot exceed portfolio value
    if cash_floor > portfolio_value:
        issues.append(f"Cash floor ${cash_floor:,.2f} exceeds portfolio value ${portfolio_value:,.2f}")
        suggestions.append(f"Reduce cash reserve to less than ${portfolio_value:,.2f}")
    
    # 2. Cash floor should not be more than 50% of portfolio (practical limit)
    if portfolio_value > 0 and cash_floor > portfolio_value * 0.5:
        issues.append(f"Cash floor ${cash_floor:,.2f} is {cash_floor/portfolio_value:.0%} of portfolio")
        suggestions.append("Consider reducing cash reserve to allow meaningful rebalancing")
    
    # 3. If all positions have gains and tax budget is effectively 0, can't rebalance
    if total_unrealized_gains > 0 and max_tax_bill < 1:
        issues.append("Portfolio has unrealized gains but tax budget is near zero")
        suggestions.append("Increase tax budget to allow selling positions with gains")
    
    # 4. Estimate minimum tax needed for basic rebalancing (5% turnover)
    estimated_turnover = portfolio_value * 0.05
    # Worst case: all sales are short-term gains
    estimated_min_tax = estimated_turnover * short_term_rate
    if max_tax_bill < estimated_min_tax and max_tax_bill > 0:
        issues.append(f"Tax budget ${max_tax_bill:,.2f} may be too low for meaningful rebalancing")
        suggestions.append(f"Consider increasing tax budget to at least ${estimated_min_tax:,.2f}")
    
    # 5. Portfolio value should be positive
    if portfolio_value <= 0:
        issues.append(f"Portfolio value is ${portfolio_value:,.2f} (must be positive)")
        suggestions.append("Check that positions have valid quantities and prices")
    
    return len(issues) == 0, issues, suggestions


def sanitize_numeric_array(arr: np.ndarray, name: str, default: float = 0.0) -> np.ndarray:
    """
    Sanitize a numeric array by replacing NaN/inf values.
    
    Args:
        arr: NumPy array to sanitize
        name: Name of the array (for logging)
        default: Value to replace bad values with
    
    Returns:
        Sanitized array
    """
    original_bad = np.sum(~np.isfinite(arr))
    if original_bad > 0:
        logger.warning(f"⚠️ Sanitizing {name}: replacing {original_bad} NaN/inf values with {default}")
        arr = np.nan_to_num(arr, nan=default, posinf=default, neginf=default)
    return arr


class PortfolioOptimizer:
    def __init__(self, portfolio: pl.DataFrame, target_allocation: pl.DataFrame,
                 portfolio_info: pl.DataFrame, total_cash, carve_out: float = 0.0,
                 cash_reserve: float = 0.0):
        self.portfolio = portfolio
        self.target_allocation = target_allocation
        self.adjusted_target_allocation = None
        self.category_target_map = {}  # Populated during legacy mode optimization
        self.portfolio_info = portfolio_info
        self.total_cash = float(total_cash or 0.0)
        self.carve_out = max(0.0, float(carve_out))
        self.minimum_cash_percent = 0.02    
        self.cash_reserve = (
            None if cash_reserve is None else max(0.0, float(cash_reserve))
        )
        self._cash_floor_dollars = None
        self._original_target_symbols = self._target_symbol_set(target_allocation)
        self._forced_individual_stock_liquidation_lots = tuple()
        self._stable_sort_inputs()

    def _target_symbol_set(self, target_allocation: pl.DataFrame) -> set[str]:
        if target_allocation is None or target_allocation.is_empty() or "Symbol" not in target_allocation.columns:
            return set()
        return {
            str(symbol or "").strip()
            for symbol in target_allocation.get_column("Symbol").to_list()
            if str(symbol or "").strip()
        }

    def _stable_sort_frame(self, frame: pl.DataFrame, preferred_cols: List[str]) -> pl.DataFrame:
        """Apply a deterministic sort using available columns plus original row order."""
        if frame is None or frame.is_empty():
            return frame

        temp_idx = "__stable_row_idx"
        sort_cols = [col for col in preferred_cols if col in frame.columns]
        if not sort_cols:
            return frame

        return (
            frame.with_row_count(temp_idx)
            .sort(sort_cols + [temp_idx])
            .drop(temp_idx)
        )

    def _stable_sort_inputs(self) -> None:
        """Keep portfolio and target allocation in a deterministic row order."""
        self.portfolio = self._stable_sort_frame(
            self.portfolio,
            [
                "Symbol",
                "Date",
                "Lot Quantity",
                "Lot Cost Basis",
                "Current Price",
                "Security Description",
                "Security Type",
            ],
        )
        self.target_allocation = self._stable_sort_frame(
            self.target_allocation,
            ["Symbol", "Target Weight", "Asset Class", "Category"],
        )
        self.portfolio_info = self._stable_sort_frame(
            self.portfolio_info,
            ["Symbol", "Current Price", "Asset Class", "Category", "Security Type"],
        )

    def _log_run_fingerprint(
        self,
        *,
        short_term_rate: float,
        long_term_rate: float,
        max_tax_bill: float,
        realized_gains_constraint: Optional[float],
        legacy_mode: bool,
        wash_sale: bool,
        constraint_type: str,
        trade_restrictions: Dict[str, List[str]],
    ) -> None:
        """Log a stable fingerprint so equivalent runs can be compared across environments."""
        if not _fingerprint_logging_enabled():
            return

        portfolio_cols = [
            col for col in [
                "Symbol", "Lot Quantity", "Lot Cost Basis", "Current Price", "Date",
                "Asset Class", "Subsector", "Category", "Substitution", "Unmanaged", "Wash Sale Blocked",
            ] if col in self.portfolio.columns
        ]
        target_cols = [
            col for col in ["Symbol", "Target Weight", "Asset Class", "Category"]
            if col in self.target_allocation.columns
        ]

        payload = {
            "portfolio": self._stable_sort_frame(self.portfolio.select(portfolio_cols), portfolio_cols).to_dicts(),
            "target": self._stable_sort_frame(self.target_allocation.select(target_cols), target_cols).to_dicts(),
            "excluded": sorted(getattr(self, "_excluded_securities", set())),
            "trade_restrictions": {
                key: sorted(set(value or [])) for key, value in sorted((trade_restrictions or {}).items())
            },
            "params": {
                "short_term_rate": round(float(short_term_rate), 10),
                "long_term_rate": round(float(long_term_rate), 10),
                "max_tax_bill": round(float(max_tax_bill), 10),
                "realized_gains_constraint": None if realized_gains_constraint is None else round(float(realized_gains_constraint), 10),
                "legacy_mode": bool(legacy_mode),
                "wash_sale": bool(wash_sale),
                "constraint_type": constraint_type,
                "carve_out": round(float(self.carve_out or 0.0), 10),
                "cash_reserve": None if self.cash_reserve is None else round(float(self.cash_reserve), 10),
                "total_cash": round(float(self.total_cash or 0.0), 10),
            },
        }
        fingerprint = hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        logger.info(
            "[Determinism] fingerprint=%s portfolio_rows=%s target_rows=%s excluded=%s restrictions=%s",
            fingerprint,
            len(payload["portfolio"]),
            len(payload["target"]),
            len(payload["excluded"]),
            {k: len(v) for k, v in payload["trade_restrictions"].items()},
        )
    
    def _validate_optimization_inputs(
        self,
        short_term_rate: float,
        long_term_rate: float,
        max_tax_bill: float,
        realized_gains_constraint: Optional[float]
    ) -> Tuple[bool, List[str], List[str]]:
        """
        Comprehensive validation to ensure convex optimization will succeed.
        
        This checks:
        1. Data quality (no NaN, inf, negative prices)
        2. Constraint feasibility (budget, cash, tax constraints are achievable)
        3. Problem structure (ensures convexity)
        4. Numerical stability (values in reasonable ranges)
        
        Returns:
            Tuple of (is_valid, critical_errors, warnings)
        """
        errors = []
        warnings = []
        
        logger.info("🔍 Validating optimization inputs for convex feasibility...")
        
        # ===== 1. PORTFOLIO DATA QUALITY =====
        
        # Check for required columns
        required_cols = ['Symbol', 'Lot Quantity', 'Lot Cost Basis', 'Current Price']
        missing = [c for c in required_cols if c not in self.portfolio.columns]
        if missing:
            errors.append(f"Missing required columns: {missing}")
        
        # Check for NaN/inf in critical numeric columns
        if 'Current Price' in self.portfolio.columns:
            prices = self.portfolio['Current Price'].to_numpy()
            if np.any(np.isnan(prices)):
                nan_symbols = self.portfolio.filter(pl.col('Current Price').is_nan())['Symbol'].to_list()
                errors.append(f"NaN prices for securities: {nan_symbols[:5]}")
            if np.any(np.isinf(prices)):
                inf_symbols = self.portfolio.filter(pl.col('Current Price').is_infinite())['Symbol'].to_list()
                errors.append(f"Infinite prices for securities: {inf_symbols[:5]}")
            if np.any(prices < 0):
                neg_symbols = self.portfolio.filter(pl.col('Current Price') < 0)['Symbol'].to_list()
                errors.append(f"Negative prices for securities: {neg_symbols[:5]}")
            if np.any((prices == 0) & (self.portfolio['Symbol'].to_numpy() != 'CASH')):
                zero_symbols = self.portfolio.filter(
                    (pl.col('Current Price') == 0) & (pl.col('Symbol') != 'CASH')
                )['Symbol'].to_list()
                warnings.append(f"Zero prices (may cause division issues): {zero_symbols[:5]}")
        
        if 'Lot Quantity' in self.portfolio.columns:
            quantities = self.portfolio['Lot Quantity'].to_numpy()
            if np.any(np.isnan(quantities)):
                errors.append("NaN quantities found in portfolio")
            if np.any(quantities < 0):
                warnings.append("Negative quantities found (short positions)")
        
        if 'Lot Cost Basis' in self.portfolio.columns:
            costs = self.portfolio['Lot Cost Basis'].to_numpy()
            if np.any(np.isnan(costs)):
                warnings.append("NaN cost basis found - may affect tax calculations")
            if np.any(costs < 0):
                warnings.append("Negative cost basis found (may be correct for some scenarios)")
        
        # ===== 2. TARGET ALLOCATION VALIDATION =====
        
        if 'Target Weight' in self.target_allocation.columns:
            weights = self.target_allocation['Target Weight'].to_numpy()
            
            # Check for NaN/inf
            if np.any(np.isnan(weights)):
                errors.append("NaN weights in target allocation")
            if np.any(np.isinf(weights)):
                errors.append("Infinite weights in target allocation")
            
            # Check for negative weights (breaks convexity)
            if np.any(weights < 0):
                neg_symbols = self.target_allocation.filter(pl.col('Target Weight') < 0)['Symbol'].to_list()
                errors.append(f"Negative target weights (not convex): {neg_symbols[:5]}")
            
            # Check weights sum to approximately 1.0
            total_weight = float(np.sum(weights))
            if abs(total_weight - 1.0) > 0.05:
                warnings.append(f"Target weights sum to {total_weight:.4f}, not 1.0")
            
            # Check for unreasonably small weights (numerical issues)
            tiny_weights = self.target_allocation.filter(
                (pl.col('Target Weight') > 0) & (pl.col('Target Weight') < 0.0001)
            )
            if len(tiny_weights) > 0:
                warnings.append(f"{len(tiny_weights)} targets < 0.01% may cause numerical issues")
        
        # ===== 3. TAX PARAMETERS VALIDATION =====
        
        # Check tax rates are in valid range [0, 1]
        if not (0 <= short_term_rate <= 1):
            errors.append(f"Short-term tax rate {short_term_rate:.2%} must be in [0, 1]")
        if not (0 <= long_term_rate <= 1):
            errors.append(f"Long-term tax rate {long_term_rate:.2%} must be in [0, 1]")
        
        # Logical check: long-term rate should be <= short-term rate
        if long_term_rate > short_term_rate:
            warnings.append(f"Long-term rate ({long_term_rate:.1%}) > short-term rate ({short_term_rate:.1%})")
        
        # Check max_tax_bill is non-negative
        if max_tax_bill < 0:
            errors.append(f"Tax budget cannot be negative: ${max_tax_bill:,.0f}")
        
        # Check realized gains constraint if provided
        if realized_gains_constraint is not None:
            if realized_gains_constraint < 0:
                errors.append(f"Realized gains constraint cannot be negative: ${realized_gains_constraint:,.0f}")
        
        # ===== 4. FEASIBILITY CHECKS =====
        
        # Calculate portfolio value
        if 'Current Price' in self.portfolio.columns and 'Lot Quantity' in self.portfolio.columns:
            prices = self.portfolio['Current Price'].to_numpy()
            quantities = self.portfolio['Lot Quantity'].to_numpy()
            portfolio_value = float(np.sum(quantities * prices))
            
            if portfolio_value <= 0:
                errors.append(f"Portfolio value ${portfolio_value:,.2f} must be positive")
            else:
                logger.info(f"  Portfolio value: ${portfolio_value:,.2f}")
                
                # Check cash floor feasibility
                cash_floor = 0.0
                if self.cash_reserve is not None and self.cash_reserve > 0:
                    cash_floor = self.cash_reserve
                else:
                    cash_floor = portfolio_value * self.minimum_cash_percent
                cash_floor += self.carve_out
                
                if cash_floor > portfolio_value:
                    errors.append(
                        f"Cash floor ${cash_floor:,.2f} ({cash_floor/portfolio_value:.1%}) "
                        f"exceeds portfolio value ${portfolio_value:,.2f}"
                    )
                elif cash_floor > portfolio_value * 0.5:
                    warnings.append(
                        f"Cash floor ${cash_floor:,.2f} ({cash_floor/portfolio_value:.1%}) "
                        f"is high - limits rebalancing flexibility"
                    )
                else:
                    logger.info(f"  Cash floor: ${cash_floor:,.2f} ({cash_floor/portfolio_value:.1%})")
                
                # Check if tax budget is reasonable
                if 'Lot Cost Basis' in self.portfolio.columns:
                    costs = self.portfolio['Lot Cost Basis'].to_numpy()
                    unrealized_gains = np.maximum(0, (quantities * prices) - costs)
                    total_gains = float(np.sum(unrealized_gains))
                    
                    if total_gains > 0:
                        # Estimate minimum tax if we need to sell 10% of portfolio
                        min_turnover = portfolio_value * 0.10
                        avg_gain_pct = total_gains / portfolio_value
                        estimated_min_tax = min_turnover * avg_gain_pct * long_term_rate
                        
                        if max_tax_bill < estimated_min_tax * 0.5:
                            warnings.append(
                                f"Tax budget ${max_tax_bill:,.0f} may be too low. "
                                f"Estimated minimum for 10% rebalance: ${estimated_min_tax:,.0f}"
                            )
                        
                        logger.info(f"  Total unrealized gains: ${total_gains:,.2f}")
                        logger.info(f"  Tax budget: ${max_tax_bill:,.2f}")
                    
                    # Check if any position exceeds realized gains constraint
                    if realized_gains_constraint is not None:
                        if total_gains < realized_gains_constraint:
                            warnings.append(
                                f"Realized gains constraint ${realized_gains_constraint:,.0f} "
                                f"> total unrealized gains ${total_gains:,.0f}"
                            )
        
        # ===== 5. NUMERICAL STABILITY CHECKS =====
        
        if 'Current Price' in self.portfolio.columns:
            prices = self.portfolio['Current Price'].to_numpy()
            non_cash_prices = prices[self.portfolio['Symbol'].to_numpy() != 'CASH']
            
            if len(non_cash_prices) > 0:
                max_price = np.max(non_cash_prices)
                min_price = np.min(non_cash_prices[non_cash_prices > 0]) if np.any(non_cash_prices > 0) else 0
                
                # Check for extreme price ratios (can cause numerical issues)
                if min_price > 0 and max_price / min_price > 1e6:
                    warnings.append(
                        f"Large price range detected: ${min_price:.2f} to ${max_price:.2f}. "
                        f"May cause numerical precision issues."
                    )
        
        # ===== SUMMARY =====
        
        is_valid = len(errors) == 0
        
        if is_valid:
            logger.info(f"✅ Validation passed ({len(warnings)} warnings)")
        else:
            logger.error(f"❌ Validation failed ({len(errors)} errors, {len(warnings)} warnings)")
            for i, error in enumerate(errors, 1):
                logger.error(f"  {i}. {error}")
        
        if warnings:
            for i, warning in enumerate(warnings, 1):
                logger.warning(f"  {i}. {warning}")
        
        return is_valid, errors, warnings

    def _align_portfolio_with_target(self, excluded_securities=None, wash_sale=False):
        """Align portfolio with target allocation by adding missing symbols and metadata."""
        logger.debug(f"Aligning portfolio ({len(self.portfolio)} lots) with target allocation")
        self._stable_sort_inputs()
        
        self.portfolio = self.portfolio.with_columns(
            pl.col("Date").fill_null(datetime.date.today())
        )

        default_date = datetime.date.today()
        
        def _build_rows_matching_schema(base_data: dict, schema: dict, num_rows: int) -> dict:
            """Build row data matching portfolio schema with proper default values."""
            row_data = {}
            for col, dtype in schema.items():
                if col in base_data:
                    row_data[col] = base_data[col]
                elif dtype == pl.String or dtype == pl.Utf8:
                    row_data[col] = [None] * num_rows
                elif dtype in (pl.Float64, pl.Float32):
                    row_data[col] = [0.0] * num_rows
                elif dtype in (pl.Int64, pl.Int32):
                    row_data[col] = [0] * num_rows
                else:
                    row_data[col] = [None] * num_rows
            return row_data

        # --- Add Cash Positions
        if "CASH" not in set(self.portfolio["Symbol"].to_list()):
            qty = float(self.total_cash or 0.0)
            base_cash = {
                "Symbol": ["CASH"],
                "Lot Quantity": [qty],
                "Lot Cost Basis": [qty],
                "Date": [default_date],
            }
            cash_data = _build_rows_matching_schema(base_cash, self.portfolio.schema, 1)
            cash_row = pl.DataFrame(cash_data)
            self.portfolio = pl.concat([self.portfolio, cash_row], how="vertical")
        else:
            # If CASH exists but quantity is missing, fill it from total_cash if provided
            if self.total_cash is not None:
                self.portfolio = self.portfolio.with_columns(
                    pl.when(pl.col("Symbol") == "CASH")
                    .then(pl.lit(float(self.total_cash)))
                    .otherwise(pl.col("Lot Quantity"))
                    .alias("Lot Quantity")
                ).with_columns(
                    pl.when(pl.col("Symbol") == "CASH")
                    .then(pl.lit(float(self.total_cash)))
                    .otherwise(pl.col("Lot Cost Basis"))
                    .alias("Lot Cost Basis")
                )

        # Track excluded securities so we don't add buy lots for them
        excluded_set = set(excluded_securities) if excluded_securities else set()
        
        # Store excluded securities for constraint setup (don't filter them out!)
        self._excluded_securities = excluded_set
        wash_sale_proxy_map = {
            str(proxy or '').strip(): str(target or '').strip()
            for proxy, target in getattr(self, '_wash_sale_proxy_substitutions', {}).items()
            if str(proxy or '').strip() and str(target or '').strip()
        }
        active_wash_sale_proxy_map = {
            proxy: target
            for proxy, target in wash_sale_proxy_map.items()
            if wash_sale
        }
        logger.debug(
            "[WASH_SALE_DEBUG] align_input "
            f"wash_sale={wash_sale} "
            f"excluded_set={sorted(excluded_set)} "
            f"raw_proxy_map={wash_sale_proxy_map} "
            f"active_proxy_map={active_wash_sale_proxy_map}"
        )

        if active_wash_sale_proxy_map:
            required_substitution_cols = {
                "Substitution": pl.Utf8,
                "Original Symbol": pl.Utf8,
                "Target Symbol": pl.Utf8,
                "Substitution Category": pl.Utf8,
                "Original Security Name": pl.Utf8,
            }
            for col_name, dtype in required_substitution_cols.items():
                if col_name not in self.portfolio.columns:
                    self.portfolio = self.portfolio.with_columns(pl.lit(None, dtype=dtype).alias(col_name))

        portfolio_symbols = set(self.portfolio["Symbol"].to_list())
        target_symbols = set(self.target_allocation["Symbol"].to_list())

        # --- Add empty buy lots for symbols with target > 0% ---
        # This allows buying into positions we want to hold, whether new or existing
        # Get target weights as a dict
        target_weights = dict(zip(
            self.target_allocation["Symbol"].to_list(),
            self.target_allocation["Target Weight"].to_list()
        ))
        
        # Add buy lots for ALL symbols with positive targets (excluding CASH and excluded)
        # Even if they're already in portfolio, we need an empty lot to buy into
        # because Constraint 1b blocks buying into existing lots to preserve cost basis.
        symbols_with_target = {s for s, w in target_weights.items() if w > 0 and s != "CASH"}
        missing_buy_symbols = sorted(symbols_with_target - excluded_set)

        if missing_buy_symbols:
            base_data = {
                "Symbol": list(missing_buy_symbols),
                "Lot Quantity": [0] * len(missing_buy_symbols),
                "Lot Cost Basis": [0.0] * len(missing_buy_symbols),
                "Date": [default_date] * len(missing_buy_symbols)
            }
            new_rows_data = _build_rows_matching_schema(base_data, self.portfolio.schema, len(missing_buy_symbols))
            new_rows = pl.DataFrame(new_rows_data).cast(self.portfolio.schema)
            self.portfolio = pl.concat([self.portfolio, new_rows], how="vertical")
            logger.debug(
                "[WASH_SALE_DEBUG] align_target_buy_lots_added "
                f"symbols={missing_buy_symbols} "
                f"excluded_set={sorted(excluded_set)}"
            )

        # Wash-sale proxy buy lots: when a wash-sale target is blocked from buys,
        # the target itself cannot be bought. Add its account-substitute proxy as
        # a zero-quantity buy lot and map it back to the target for allocation.
        wash_sale_proxy_buy_symbols = sorted({
            proxy
            for proxy, target in active_wash_sale_proxy_map.items()
            if target_weights.get(target, 0.0) > 0 and proxy != "CASH"
        })
        missing_proxy_buy_symbols = [
            proxy for proxy in wash_sale_proxy_buy_symbols
            if proxy not in set(self.portfolio["Symbol"].to_list())
        ]
        if missing_proxy_buy_symbols:
            base_data = {
                "Symbol": missing_proxy_buy_symbols,
                "Lot Quantity": [0] * len(missing_proxy_buy_symbols),
                "Lot Cost Basis": [0.0] * len(missing_proxy_buy_symbols),
                "Date": [default_date] * len(missing_proxy_buy_symbols),
                "Substitution": [active_wash_sale_proxy_map[proxy] for proxy in missing_proxy_buy_symbols],
                "Original Symbol": [proxy for proxy in missing_proxy_buy_symbols],
                "Target Symbol": [active_wash_sale_proxy_map[proxy] for proxy in missing_proxy_buy_symbols],
            }
            new_rows_data = _build_rows_matching_schema(base_data, self.portfolio.schema, len(missing_proxy_buy_symbols))
            new_rows = pl.DataFrame(new_rows_data).cast(self.portfolio.schema)
            self.portfolio = pl.concat([self.portfolio, new_rows], how="vertical")
            logger.info(
                f"🧼 Added {len(missing_proxy_buy_symbols)} wash-sale proxy buy lot(s): "
                f"{ {proxy: active_wash_sale_proxy_map[proxy] for proxy in missing_proxy_buy_symbols} }"
            )
            logger.debug(
                "[WASH_SALE_DEBUG] align_proxy_buy_lots_added "
                f"proxy_to_target={ {proxy: active_wash_sale_proxy_map[proxy] for proxy in missing_proxy_buy_symbols} }"
            )

        if active_wash_sale_proxy_map and "Substitution" in self.portfolio.columns:
            proxy_expr = pl.col("Symbol")
            target_expr = pl.col("Symbol").replace(active_wash_sale_proxy_map, default=None)
            self.portfolio = self.portfolio.with_columns([
                pl.when(proxy_expr.is_in(list(active_wash_sale_proxy_map.keys())))
                .then(target_expr)
                .otherwise(pl.col("Substitution"))
                .alias("Substitution"),
                pl.when(proxy_expr.is_in(list(active_wash_sale_proxy_map.keys())))
                .then(pl.col("Symbol"))
                .otherwise(pl.col("Original Symbol"))
                .alias("Original Symbol"),
                pl.when(proxy_expr.is_in(list(active_wash_sale_proxy_map.keys())))
                .then(target_expr)
                .otherwise(pl.col("Target Symbol"))
                .alias("Target Symbol"),
            ])
            if _verbose_debug_logging_enabled():
                proxy_trace_cols = [
                    col for col in [
                        "Symbol", "Lot Quantity", "Substitution", "Original Symbol",
                        "Target Symbol", "Category", "Rebalance Category", "Unmanaged",
                    ] if col in self.portfolio.columns
                ]
                proxy_trace_symbols = sorted(set(active_wash_sale_proxy_map) | set(active_wash_sale_proxy_map.values()))
                proxy_rows = (
                    self.portfolio
                    .filter(pl.col("Symbol").is_in(proxy_trace_symbols))
                    .select(proxy_trace_cols)
                    .to_dicts()
                )
                logger.debug(
                    "[WASH_SALE_DEBUG] align_proxy_rows_after_substitution "
                    f"trace_symbols={proxy_trace_symbols} rows={proxy_rows}"
                )

        # --- Add 0% weight rows for symbols in portfolio but not in target ---
        missing_targets = sorted(portfolio_symbols - target_symbols)
        if missing_targets:
            extra_targets_data = {
                "Symbol": list(missing_targets),
                "Target Weight": [0.0] * len(missing_targets)
            }
            # Add any additional columns from target_allocation to match schema
            for col in self.target_allocation.columns:
                if col not in extra_targets_data:
                    # For Asset Class, try to get from portfolio_info
                    if col == "Asset Class" and self.portfolio_info is not None and "Asset Class" in self.portfolio_info.columns:
                        ac_map = dict(zip(
                            self.portfolio_info["Symbol"].to_list(),
                            self.portfolio_info["Asset Class"].to_list()
                        ))
                        extra_targets_data[col] = [ac_map.get(sym, "Unclassified") for sym in missing_targets]
                    else:
                        extra_targets_data[col] = [None] * len(missing_targets)
            extra_targets = pl.DataFrame(extra_targets_data)
            self.target_allocation = pl.concat([self.target_allocation, extra_targets], how="vertical")


        # --- Add additional Info
        # Preserve original Current Price and Original Security Name before join
        # (important for substituted securities)
        # After substitution, portfolio has:
        # - ITOT's price (not VTI's price)
        # - Original Security Name for display
        # We don't want the join to overwrite these with values from portfolio_info
        has_current_price = "Current Price" in self.portfolio.columns
        has_original_security_name = "Original Security Name" in self.portfolio.columns
        
        if has_current_price:
            self.portfolio = self.portfolio.rename({"Current Price": "Temp Original Current Price"})
        if has_original_security_name:
            self.portfolio = self.portfolio.rename({"Original Security Name": "Temp Original Security Name"})
        
        # Check if portfolio already has Category column (existing lots have it, empty lots don't)
        portfolio_has_category = "Category" in self.portfolio.columns
        
        # If portfolio has Category, rename it before join to avoid collision
        if portfolio_has_category:
            self.portfolio = self.portfolio.rename({"Category": "Original_Category"})
        
        self.portfolio = (
            self.portfolio.join(self.portfolio_info, on="Symbol", how="left")
        )

        # Buy lots are created from the existing portfolio schema, so metadata
        # columns can exist on the left side as nulls. After the portfolio_info
        # join, prefer those existing values only when populated; otherwise use
        # the explicit metadata returned by get_additional_security_info.
        metadata_cols = [
            "Asset Class",
            "Subsector",
            "Security Type",
            "Security Description",
            "Rebalance Category",
            "Account Rebalance Category",
            "Target Rebalance Category",
            "Security Info Rebalance Category",
            "Metadata Source",
            "Wash Sale Blocked",
            "Allows Fractional",
            "Unmanaged",
            "Volatility",
        ]
        coalesce_exprs = []
        drop_joined_cols = []
        rename_joined_cols = {}
        for col in metadata_cols:
            joined_col = f"{col}_right"
            has_col = col in self.portfolio.columns
            has_joined_col = joined_col in self.portfolio.columns
            if has_col and has_joined_col:
                coalesce_exprs.append(pl.coalesce([pl.col(col), pl.col(joined_col)]).alias(col))
                drop_joined_cols.append(joined_col)
            elif has_joined_col:
                rename_joined_cols[joined_col] = col

        if coalesce_exprs:
            self.portfolio = self.portfolio.with_columns(coalesce_exprs)
        if drop_joined_cols:
            self.portfolio = self.portfolio.drop(drop_joined_cols)
        if rename_joined_cols:
            self.portfolio = self.portfolio.rename(rename_joined_cols)

        self.portfolio = self.portfolio.with_columns([
            pl.col("Allows Fractional").fill_null("No"),
            pl.col("Wash Sale Blocked").fill_null('No'),
            pl.col("Unmanaged").fill_null("No")
        ])
        
        # Handle Category: prefer original value (for existing lots), then portfolio_info value, then symbol
        if portfolio_has_category:
            self.portfolio = self.portfolio.with_columns([
                pl.coalesce(["Original_Category", "Category", "Symbol"]).alias("Category")
            ]).drop("Original_Category")
        else:
            self.portfolio = self.portfolio.with_columns([
                pl.col("Category").fill_null(pl.col("Symbol"))
            ])

        # Restore original price if it existed (for substituted securities, use actual held security's price)
        if has_current_price:
            self.portfolio = self.portfolio.with_columns([
                pl.coalesce(["Temp Original Current Price", "Current Price"]).alias("Current Price")
            ]).drop("Temp Original Current Price")
        else:
            # No original price, fill with portfolio_info price
            self.portfolio = self.portfolio.with_columns([
                pl.col("Current Price").fill_null(0.0)
            ])
        
        # Restore original security name if it existed (for substituted securities display)
        if has_original_security_name:
            self.portfolio = self.portfolio.with_columns([
                pl.col("Temp Original Security Name").alias("Original Security Name")
            ]).drop("Temp Original Security Name")
        
        self.portfolio = self.portfolio.with_columns([
                pl.when(pl.col("Lot Quantity").cast(pl.Float64) % 1 != 0)
                .then(pl.lit("Yes"))
                .otherwise(pl.col("Allows Fractional"))
                .alias("Allows Fractional") 
            ])

        if active_wash_sale_proxy_map and "Rebalance Category" in self.portfolio.columns:
            target_rebalance_by_symbol = {}
            if (
                self.portfolio_info is not None
                and "Symbol" in self.portfolio_info.columns
                and "Rebalance Category" in self.portfolio_info.columns
            ):
                target_symbols_for_proxy = set(active_wash_sale_proxy_map.values())
                for row in (
                    self.portfolio_info
                    .filter(pl.col("Symbol").is_in(list(target_symbols_for_proxy)))
                    .select(["Symbol", "Rebalance Category"])
                    .iter_rows(named=True)
                ):
                    normalized = _normalize_rebalance_category_for_tolerance(row.get("Rebalance Category"))
                    if normalized:
                        target_rebalance_by_symbol[str(row.get("Symbol") or "").strip()] = row.get("Rebalance Category")

            proxy_rebalance_map = {
                proxy: target_rebalance_by_symbol[target]
                for proxy, target in active_wash_sale_proxy_map.items()
                if target in target_rebalance_by_symbol
            }
            if proxy_rebalance_map:
                missing_proxy_rebalance_expr = (
                    pl.col("Symbol").is_in(list(proxy_rebalance_map.keys()))
                    & (pl.col("Rebalance Category").cast(pl.Utf8).str.strip_chars().fill_null("") == "")
                )
                fill_exprs = [
                    pl.when(missing_proxy_rebalance_expr)
                    .then(pl.col("Symbol").replace(proxy_rebalance_map))
                    .otherwise(pl.col("Rebalance Category"))
                    .alias("Rebalance Category")
                ]
                if "Security Info Rebalance Category" in self.portfolio.columns:
                    fill_exprs.append(
                        pl.when(
                            pl.col("Symbol").is_in(list(proxy_rebalance_map.keys()))
                            & (pl.col("Security Info Rebalance Category").cast(pl.Utf8).str.strip_chars().fill_null("") == "")
                        )
                        .then(pl.col("Symbol").replace(proxy_rebalance_map))
                        .otherwise(pl.col("Security Info Rebalance Category"))
                        .alias("Security Info Rebalance Category")
                    )
                if "Metadata Source" in self.portfolio.columns:
                    fill_exprs.append(
                        pl.when(missing_proxy_rebalance_expr)
                        .then(pl.lit("Wash_Sale_Proxy_Target_Rebalance_Category"))
                        .otherwise(pl.col("Metadata Source"))
                        .alias("Metadata Source")
                    )
                self.portfolio = self.portfolio.with_columns(fill_exprs)
                if _verbose_debug_logging_enabled():
                    proxy_rebalance_rows = (
                        self.portfolio
                        .filter(pl.col("Symbol").is_in(list(proxy_rebalance_map.keys())))
                        .select([
                            col for col in [
                                "Symbol", "Substitution", "Target Symbol", "Rebalance Category",
                                "Security Info Rebalance Category", "Metadata Source", "Current Price",
                            ] if col in self.portfolio.columns
                        ])
                        .to_dicts()
                    )
                    logger.debug(
                        "[WASH_SALE_DEBUG] proxy_rebalance_category_hydration "
                        f"proxy_rebalance_map={proxy_rebalance_map} rows={proxy_rebalance_rows}"
                    )

        if _verbose_debug_logging_enabled() and "Symbol" in self.portfolio.columns:
            trace_cols = [
                col for col in [
                    "Symbol", "Lot Quantity", "Category", "Asset Class", "Security Type",
                    "Subsector", "Security Description", "Rebalance Category", "Account Rebalance Category",
                    "Target Rebalance Category", "Security Info Rebalance Category",
                    "Metadata Source", "Unmanaged", "Current Price",
                ] if col in self.portfolio.columns
            ]
            trace_symbols = {"BND"}
            trace_symbols.update(set(getattr(self, '_wash_sale_proxy_substitutions', {}) or {}))
            trace_symbols.update(set((getattr(self, '_wash_sale_proxy_substitutions', {}) or {}).values()))
            bnd_rows = (
                self.portfolio
                .with_columns(pl.col("Symbol").cast(pl.Utf8).str.strip_chars().str.to_uppercase().alias("_symbol_upper"))
                .filter(pl.col("_symbol_upper").is_in(sorted(trace_symbols)))
                .select(trace_cols)
                .to_dicts()
            )
            if bnd_rows:
                logger.debug(
                    "[MODEL_ASSIGNMENT_DEBUG] optimizer_after_security_info_join_trace "
                    f"trace_symbols={sorted(trace_symbols)} "
                    f"rows={bnd_rows}"
                )

        if "Unmanaged" in self.portfolio.columns and "Lot Quantity" in self.portfolio.columns:
            self.portfolio = self.portfolio.with_columns(
                pl.when(
                    (pl.col("Lot Quantity").cast(pl.Float64, strict=False).fill_null(0.0) == 0.0)
                    & (~pl.col("Symbol").is_in(list(excluded_set)))
                )
                .then(pl.lit("No"))
                .otherwise(pl.col("Unmanaged"))
                .alias("Unmanaged")
            )

        if "Rebalance Category" in self.portfolio.columns and "Lot Quantity" in self.portfolio.columns:
            missing_target_rebalance = (
                self.portfolio
                .with_columns([
                    pl.col("Symbol").cast(pl.Utf8).str.strip_chars().str.to_uppercase().alias("_symbol_upper"),
                    pl.col("Lot Quantity").cast(pl.Float64, strict=False).fill_null(0.0).alias("_lot_quantity"),
                    pl.col("Rebalance Category").cast(pl.Utf8).str.strip_chars().fill_null("").alias("_rebalance_category"),
                ])
                .filter(
                    (pl.col("_lot_quantity") == 0.0)
                    & pl.col("_symbol_upper").is_in(list(symbols_with_target))
                    & (pl.col("_rebalance_category") == "")
                )
                .get_column("Symbol")
                .unique()
                .to_list()
            )
            if missing_target_rebalance:
                logger.warning(
                    "⚠️ Target allocation securities missing Rebalance Category from get_additional_security_info; "
                    f"these symbols will be excluded from rebalance-category tolerance: {sorted(missing_target_rebalance)}"
                )
                logger.debug(
                    "[MODEL_ASSIGNMENT_DEBUG] optimizer_missing_target_rebalance_category "
                    f"symbols={sorted(missing_target_rebalance)}"
                )
        
        unmanaged_syms = sorted({
                *self.portfolio.filter(pl.col("Unmanaged") == "Yes")
                .get_column("Symbol")
                .to_list()
            })
        
        # Only filter out Unmanaged securities that are ALSO in the excluded set
        # If the user removed the trading exclusion for an Unmanaged security,
        # it should remain in the portfolio and be optimized normally
        unmanaged_still_excluded = [s for s in unmanaged_syms if s in excluded_set]
        unmanaged_user_included = [s for s in unmanaged_syms if s not in excluded_set]
        
        if unmanaged_user_included:
            logger.info(f"✅ User opted to include {len(unmanaged_user_included)} Unmanaged securities in optimization: {unmanaged_user_included}")
        
        if unmanaged_still_excluded:
            logger.info(f"🔒 Filtering out {len(unmanaged_still_excluded)} Unmanaged securities (user kept exclusion): {unmanaged_still_excluded}")
        
        # Capture excluded+unmanaged positions BEFORE filtering them out,
        # so they can appear as HOLD rows in results/exports
        self._excluded_unmanaged_positions = []
        if unmanaged_still_excluded:
            excluded_rows = self.portfolio.filter(
                pl.col("Unmanaged").eq("Yes") & pl.col("Symbol").is_in(unmanaged_still_excluded)
            )
            # Fixed income security types use bond-quoted prices (per $100 par)
            # Must normalize by /100 — same logic as _optimize_portfolio
            fixed_income_types = {"T-Bills", "CDs", "Fixed Income", "Mortgage-Backed"}

            # Aggregate by symbol (may have multiple lots)
            for sym in unmanaged_still_excluded:
                sym_rows = excluded_rows.filter(pl.col("Symbol") == sym)
                if len(sym_rows) > 0:
                    total_qty = sym_rows.select(pl.sum("Lot Quantity")).item() or 0
                    raw_price = sym_rows.select(pl.first("Current Price")).item() or 0
                    sec_type = sym_rows.select(pl.first("Security Type")).item() if "Security Type" in sym_rows.columns else ""
                    asset_class = sym_rows.select(pl.first("Asset Class")).item() or "Unclassified"
                    category = sym_rows.select(pl.first("Category")).item() or sym
                    sec_desc = sym_rows.select(pl.first("Security Description")).item() if "Security Description" in sym_rows.columns else sym
                    rebalance_category = sym_rows.select(pl.first("Rebalance Category")).item() if "Rebalance Category" in sym_rows.columns else None

                    # Normalize fixed income prices (quoted per $100 par → per $1 par)
                    if sec_type in fixed_income_types and raw_price > 1:
                        price = raw_price / 100.0
                    else:
                        price = float(raw_price or 0.0)

                    market_value = total_qty * price
                    self._excluded_unmanaged_positions.append({
                        'symbol': sym,
                        'security_description': sec_desc,
                        'asset_class': asset_class,
                        'category': category,
                        'rebalance_category': rebalance_category,
                        'shares': total_qty,
                        'market_value': market_value,
                        'price': price,
                    })
            logger.info(f"📦 Captured {len(self._excluded_unmanaged_positions)} excluded+unmanaged positions for results display")
        
        self.portfolio = self.portfolio.filter(
            ~(pl.col("Unmanaged").eq("Yes") & pl.col("Symbol").is_in(unmanaged_still_excluded)) | pl.col("Unmanaged").is_null()
        )
        self.target_allocation = self.target_allocation.filter(~pl.col("Symbol").is_in(unmanaged_still_excluded))
        self._stable_sort_inputs()
    

        return self.portfolio, self.target_allocation
    
        

    def _correct_overshoot(
        self,
        optimized_qty,
        shares_bought_val,
        shares_sold_val,
        lot_quantities,
        current_prices,
        max_total_value,
        cash_idxs=None
    ):
        total_value = float(np.sum(optimized_qty * current_prices))
        # Handle cash_idxs: can be None, empty list, or numpy array
        cash_set = set(cash_idxs.tolist() if hasattr(cash_idxs, 'tolist') else (cash_idxs or []))

        # -------- 1) Trim market-value overshoot (never trim CASH) --------
        while total_value > max_total_value + 1e-9:
            buy_indices = np.where(shares_bought_val >= 1)[0]
            if cash_set:
                buy_indices = np.array([i for i in buy_indices if i not in cash_set], dtype=int)

            if buy_indices.size == 0:
                logging.info("No more non-cash buys to reduce to meet budget.")
                break

            # reduce the most expensive buy first
            i = buy_indices[np.argmax(current_prices[buy_indices])]
            shares_bought_val[i] -= 1.0
            optimized_qty[i] = lot_quantities[i] + shares_bought_val[i] - shares_sold_val[i]

            total_value = float(np.sum(optimized_qty * current_prices))

        slack = max(max_total_value - total_value, 0.0)

        # -------- 2) Enforce CASH floor (post-trim) --------
        cash_floor = float(getattr(self, "_cash_floor_dollars", 0.0))
        # Check if cash_idxs is non-empty (handle numpy arrays properly)
        has_cash = len(cash_idxs) > 0 if hasattr(cash_idxs, '__len__') else bool(cash_idxs)
        if has_cash:
            current_cash = float(np.sum(optimized_qty[cash_idxs]))
            deficit = max(cash_floor - current_cash, 0.0)

            if deficit > 1e-9:
                noncash_buy_idxs = [i for i in np.where(shares_bought_val > 0)[0] if i not in cash_set and current_prices[i] > 0]
                noncash_buy_idxs.sort(key=lambda j: current_prices[j], reverse=True)

                c0 = cash_idxs[0]
                for i in noncash_buy_idxs:
                    if deficit <= 1e-9:
                        break
                    max_free = shares_bought_val[i] * current_prices[i]  
                    if max_free <= 0:
                        continue
                    take = min(max_free, deficit)
                    d_shares = take / current_prices[i]

                    shares_bought_val[i] -= d_shares
                    optimized_qty[i] = lot_quantities[i] + shares_bought_val[i] - shares_sold_val[i]
                    
                    shares_bought_val[c0] += take
                    optimized_qty[c0] = lot_quantities[c0] + shares_bought_val[c0] - shares_sold_val[c0]

                    deficit -= take

                if deficit > 1e-6:
                    logging.warning(f"Unable to fully satisfy cash floor; remaining deficit ${deficit:,.2f}")

        return optimized_qty, shares_bought_val, slack

            
    def _effective_target_allocation_with_cash(self, budget_value: float) -> pl.DataFrame:
        """
        Instance method wrapper that calls the standalone function and stores state.
        
        This method maintains backward compatibility with existing optimizer code
        while delegating the core logic to the shared utility function.
        """
        eff, cash_floor_dollars = calculate_effective_target_allocation_with_cash(
            target_allocation=self.target_allocation,
            budget_value=budget_value,
            cash_reserve=self.cash_reserve,
            carve_out=self.carve_out,
            minimum_cash_percent=self.minimum_cash_percent
        )
        
        # Store state for solver constraints (optimizer needs this)
        self._cash_floor_dollars = cash_floor_dollars
        
        # Update cash_reserve to actual calculated value if it was None
        if budget_value > 0:
            if self.cash_reserve is not None and self.cash_reserve > 0:
                reserve = max(0.0, float(self.cash_reserve))
            else:
                reserve = self.minimum_cash_percent * budget_value
            self.cash_reserve = reserve
        
        return eff

    def _target_rebalance_category_weights(self) -> Dict[str, float]:
        """Return normalized Equity/Fixed Income target weights from explicit metadata."""
        if self.target_allocation is None or self.target_allocation.is_empty():
            return {}

        symbol_to_rebalance_category: Dict[str, str] = {}
        metadata_sources = [self.portfolio_info, self.target_allocation]
        for source in metadata_sources:
            if source is None or "Symbol" not in source.columns or "Rebalance Category" not in source.columns:
                continue
            for row in source.select(["Symbol", "Rebalance Category"]).iter_rows(named=True):
                symbol = str(row.get("Symbol") or "").strip().upper()
                if not symbol or symbol in symbol_to_rebalance_category:
                    continue
                normalized = _normalize_rebalance_category_for_tolerance(row.get("Rebalance Category"))
                if normalized:
                    symbol_to_rebalance_category[symbol] = normalized

        weights: Dict[str, float] = {"equity": 0.0, "fixed income": 0.0}
        missing_rebalance_symbols = []
        for row in self.target_allocation.iter_rows(named=True):
            symbol = str(row.get("Symbol") or "").strip().upper()
            if not symbol or symbol == "CASH":
                continue

            try:
                weight = float(row.get("Target Weight") or 0.0)
            except (TypeError, ValueError):
                weight = 0.0
            if weight <= 0:
                continue

            normalized = _normalize_rebalance_category_for_tolerance(
                row.get("Rebalance Category") if "Rebalance Category" in self.target_allocation.columns else None
            ) or symbol_to_rebalance_category.get(symbol, "")

            if normalized:
                weights[normalized] += weight
            else:
                missing_rebalance_symbols.append(symbol)

        total_weight = weights["equity"] + weights["fixed income"]
        if missing_rebalance_symbols:
            logger.warning(
                "Target allocation securities missing Rebalance Category from get_additional_security_info; "
                f"excluded from optimizer rebalance-category corridor: {sorted(set(missing_rebalance_symbols))}"
            )
            logger.debug(
                "[MODEL_ASSIGNMENT_DEBUG] optimizer_target_missing_rebalance_category "
                f"symbols={sorted(set(missing_rebalance_symbols))}"
            )
        if total_weight <= 1e-12:
            return {}

        return {
            "equity": weights["equity"] / total_weight,
            "fixed income": weights["fixed income"] / total_weight,
        }

    def _net_cash_lots(self, bought_val, sold_val, lot_quantities, symbols):

        cash_idxs = [i for i, s in enumerate(symbols) if s == "CASH"]
        if not cash_idxs:
            return bought_val, sold_val

        # Net across all CASH lots
        net_total = float(np.sum(bought_val[cash_idxs]) - np.sum(sold_val[cash_idxs]))

        # Zero out all CASH buys/sells
        bought_val[cash_idxs] = 0.0
        sold_val[cash_idxs]   = 0.0

        if net_total >= 0:
            # Single net BUY goes on the first CASH lot
            bought_val[cash_idxs[0]] = net_total
        else:
            # Net SELL: distribute across CASH lots respecting lot-quantity caps
            need = -net_total
            for ci in cash_idxs:
                cap = float(lot_quantities[ci])  # cannot sell more than this lot's quantity
                take = min(need, cap)
                if take > 0:
                    sold_val[ci] = take
                    need -= take
                if need <= 1e-9:
                    break
            if need > 1e-9:
                logging.warning("Net CASH sell exceeds available CASH quantity by %.6f", need)

        return bought_val, sold_val

    def _balance_budget_via_cash(
        self,
        optimized_qty: np.ndarray,
        current_prices: np.ndarray,
        symbols: list,
        budget_value: float,
        cash_lower: float | None = None,
        cash_upper: float | None = None,
        tolerance: float = 0.01
    ) -> np.ndarray:
        """
        Adjust CASH position to ensure total optimized value equals budget value exactly.
        
        Due to rounding, solver tolerances, and numerical precision, the optimized
        portfolio value may not exactly match the starting budget. This function
        calculates the difference and adjusts the CASH position accordingly.
        
        Args:
            optimized_qty: Array of optimized quantities for each lot
            current_prices: Array of current prices for each lot (CASH price = 1.0)
            symbols: List of symbol names for each lot
            budget_value: The original portfolio value that must be preserved
            tolerance: Minimum difference to trigger adjustment (default $0.01)
        
        Returns:
            Adjusted optimized_qty array with CASH position modified
        """
        # Calculate current total value
        total_optimized_value = float(np.sum(optimized_qty * current_prices))
        
        # Calculate the difference
        difference = budget_value - total_optimized_value
        
        # If difference is within tolerance, no adjustment needed
        if abs(difference) < tolerance:
            logger.debug(f"[Budget Balance] No adjustment needed. Diff=${difference:.2f}")
            return optimized_qty
        
        # Find CASH lot indices
        cash_idxs = [i for i, s in enumerate(symbols) if s == "CASH"]
        
        if not cash_idxs:
            logger.warning(f"[Budget Balance] Cannot adjust - no CASH lots found. Diff=${difference:.2f}")
            return optimized_qty
        
        # Get current CASH quantity
        current_cash = float(np.sum(optimized_qty[cash_idxs]))
        new_cash = current_cash + difference

        # Respect the same monotonic cash bounds used in the main solve.
        if cash_lower is not None and new_cash < cash_lower:
            logger.warning(
                f"[Budget Balance] CASH adjustment would breach lower bound. "
                f"Clipping ${new_cash:.2f} to ${cash_lower:.2f}."
            )
            new_cash = cash_lower
        if cash_upper is not None and new_cash > cash_upper:
            logger.warning(
                f"[Budget Balance] CASH adjustment would breach upper bound. "
                f"Clipping ${new_cash:.2f} to ${cash_upper:.2f}."
            )
            new_cash = cash_upper

        difference = new_cash - current_cash
        
        # Log the adjustment
        if difference > 0:
            logger.info(f"[Budget Balance] Portfolio under by ${difference:.2f}. Increasing CASH: ${current_cash:.2f} → ${new_cash:.2f}")
        else:
            logger.info(f"[Budget Balance] Portfolio over by ${-difference:.2f}. Decreasing CASH: ${current_cash:.2f} → ${new_cash:.2f}")
        
        # Ensure we don't go negative on cash
        if new_cash < 0:
            logger.warning(f"[Budget Balance] Cannot reduce CASH below zero. Adjustment capped.")
            # Set cash to minimum (close to zero but not negative)
            adjustment = current_cash - 0.01
            difference = adjustment
            new_cash = 0.01
        
        # Apply the adjustment to the first CASH lot
        # (All CASH lots should have been netted by _net_cash_lots already)
        optimized_qty[cash_idxs[0]] += difference
        
        # Verify the adjustment
        new_total = float(np.sum(optimized_qty * current_prices))
        logger.debug(f"[Budget Balance] After adjustment: ${new_total:.2f} (target: ${budget_value:.2f}, diff: ${budget_value - new_total:.4f})")
        
        return optimized_qty

    def _to_array(self, var, n):
        if var.value is None:
            return np.zeros(n)
        arr = np.array(var.value, dtype=float).ravel()
        arr = np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)
        return arr
    
    def _solve_with_fallback(self, problem: cp.Problem, pass_name: str, **solve_opts) -> Tuple[str, str]:
        """
        Solve a CVXPY problem with automatic solver fallback.
        
        Tries solvers in order: OSQP → ECOS → CLARABEL → SCS
        - OSQP: Fast, handles most convex QPs (preferred)
        - ECOS: More robust, handles edge cases
        - CLARABEL: Modern interior-point solver
        - SCS: Most general, slower but very reliable
        
        Parameters:
        -----------
        problem: cp.Problem
            The CVXPY problem to solve
        pass_name: str
            Name of the optimization pass (for logging)
        **solve_opts:
            Additional solver options
        
        Returns:
        --------
        Tuple[str, str]:
            (solver_used, status)
            - solver_used: Name of solver that succeeded ("OSQP", "ECOS", "CLARABEL", "SCS")
            - status: CVXPY status string ("optimal", "infeasible", etc.)
        
        Raises:
        -------
        RuntimeError:
            If all solvers fail to find a solution
        """
        solver_candidates = [
            (cp.OSQP, "OSQP", "Fast quadratic programming solver (preferred)"),
            (cp.ECOS, "ECOS", "Robust conic solver (fallback #1)"),
            (cp.CLARABEL, "CLARABEL", "Modern interior-point solver (fallback #2)"),
            (cp.SCS, "SCS", "General convex solver (fallback #3)")
        ]
        installed_solver_names = set(cp.installed_solvers())
        solvers = [
            entry for entry in solver_candidates
            if entry[1] in installed_solver_names
        ]
        skipped_solver_names = [
            name for _, name, _ in solver_candidates
            if name not in installed_solver_names
        ]
        
        logger.info(f"{'='*80}")
        logger.info(f"SOLVER SELECTION: {pass_name}")
        logger.info(f"Available solvers: {' → '.join(name for _, name, _ in solvers)}")
        if skipped_solver_names:
            logger.info(f"Skipping uninstalled solvers: {', '.join(skipped_solver_names)}")
        logger.info(f"{'='*80}")
        if not solvers:
            raise RuntimeError(
                "No supported CVXPY solvers are installed. Install OSQP, CLARABEL, ECOS, or SCS."
            )

        compare_mode = _multi_solver_compare_enabled()
        if compare_mode:
            logger.info("[Solver Compare] Enabled: running all solvers and selecting best candidate")

        def _capture_variable_values() -> Dict[int, np.ndarray]:
            snapshot = {}
            for var in problem.variables():
                if var.value is not None:
                    snapshot[var.id] = np.array(var.value, dtype=float, copy=True)
            return snapshot

        def _restore_variable_values(snapshot: Dict[int, np.ndarray]) -> None:
            for var in problem.variables():
                if var.id in snapshot:
                    var.value = snapshot[var.id]

        def _max_constraint_violation() -> float:
            max_v = 0.0
            for c in problem.constraints:
                try:
                    v = c.violation()
                    if v is None:
                        continue
                    arr = np.array(v, dtype=float)
                    if arr.size == 0:
                        continue
                    cand = float(np.nanmax(np.abs(arr)))
                    if np.isfinite(cand):
                        max_v = max(max_v, cand)
                except Exception:
                    continue
            return max_v
        
        last_error = None
        infeasible_solver_count = 0
        candidates = []
        # Track best high-objective solution as fallback for near-infeasible problems
        best_high_obj_solver = None
        best_high_obj_value = float('inf')
        # If horribly misaligned (50% off), objective ~= (0.5*budget)^2 / budget = 0.25*budget.
        # Anything > 1M for a normal portfolio is clearly suspicious.
        MAX_REASONABLE_OBJECTIVE = 1e6
        
        for i, (solver, solver_name, description) in enumerate(solvers, 1):
            try:
                logger.info(f"Trying solver {i}/{len(solvers)}: {solver_name} - {description}")
                
                # Attempt to solve with solver-specific tuning
                if solver == cp.OSQP:
                    # OSQP-specific: Already configured in solve_opts with adaptive_rho and scaling
                    problem.solve(solver=solver, **solve_opts, warm_start=False)
                elif solver == cp.ECOS:
                    # ECOS-specific: Different options (no polish/adaptive_rho)
                    ecos_opts = {
                        'abstol': 1e-5,
                        'reltol': 1e-5,
                        'feastol': 1e-5,
                        'max_iters': 200,
                        'verbose': False
                    }
                    problem.solve(solver=solver, **ecos_opts)
                elif solver == cp.SCS:
                    # SCS-specific: Tighter tolerance settings
                    scs_opts = {
                        'eps_abs': 1e-6,  # Much tighter tolerance
                        'eps_rel': 1e-6,
                        'max_iters': 50000,  # More iterations
                        'verbose': False,
                        'normalize': True,
                        'scale': 5.0  # Better scaling
                    }
                    problem.solve(solver=solver, **scs_opts)
                elif solver == cp.CLARABEL:
                    # CLARABEL-specific: Modern interior point solver
                    clarabel_opts = {
                        'tol_gap_abs': 1e-7,
                        'tol_gap_rel': 1e-7,
                        'tol_feas': 1e-7,
                        'tol_infeas_abs': 1e-7,
                        'tol_infeas_rel': 1e-7,
                        'max_iter': 500,
                        'verbose': False
                    }
                    problem.solve(solver=solver, **clarabel_opts)
                else:
                    problem.solve(solver=solver, **solve_opts, warm_start=False)
                
                # Check if solution is acceptable
                if problem.status == cp.OPTIMAL:
                    # Sanity check: objective value should be reasonable for portfolio alignment
                    # A value > 1000x budget suggests numerical issues (e.g., cash_slack term blowing up).
                    if problem.value is not None and problem.value > MAX_REASONABLE_OBJECTIVE:
                        logger.warning(f"⚠ {solver_name} returned OPTIMAL but objective value is suspiciously high!")
                        logger.warning(f"  Objective value: {problem.value:,.2f} (threshold: {MAX_REASONABLE_OBJECTIVE:,.0f})")
                        logger.warning(f"  This suggests numerical issues or near-infeasibility - trying next solver...")
                        # Track this as a fallback option in case ALL solvers have high objectives
                        # (which indicates a genuinely difficult/infeasible problem)
                        if best_high_obj_solver is None or (problem.value is not None and problem.value < best_high_obj_value):
                            best_high_obj_solver = solver_name
                            best_high_obj_value = problem.value if problem.value is not None else float('inf')
                        last_error = f"{solver_name}: Unreasonably high objective ({problem.value:,.0f})"
                        continue
                    
                    logger.info(f"✓ {solver_name} succeeded!")
                    logger.info(f"  Status: {problem.status}")
                    logger.info(f"  Objective value: {problem.value:,.2f}" if problem.value is not None else "  Objective value: None")
                    if compare_mode:
                        candidates.append({
                            "solver": solver_name,
                            "status": problem.status,
                            "objective": float(problem.value) if problem.value is not None else float("inf"),
                            "violation": _max_constraint_violation(),
                            "snapshot": _capture_variable_values(),
                        })
                        continue
                    return solver_name, problem.status
                
                # OPTIMAL_INACCURATE: Solution found but may have numerical issues.
                # If the measured violation is within the post-processing
                # tolerance, keep it and avoid a second solver pass.
                elif problem.status == cp.OPTIMAL_INACCURATE:
                    violation = _max_constraint_violation()
                    acceptable_inaccurate_violation = 1.0
                    logger.warning(
                        f"⚠ {solver_name} returned OPTIMAL_INACCURATE "
                        f"(max violation={violation:.3e})"
                    )
                    if problem.value is not None:
                        logger.warning(f"  Objective value: {problem.value:,.2f}")
                    if (
                        not compare_mode
                        and violation <= acceptable_inaccurate_violation
                        and (
                            problem.value is None
                            or problem.value <= MAX_REASONABLE_OBJECTIVE
                        )
                    ):
                        logger.info(
                            f"✓ Accepting {solver_name} OPTIMAL_INACCURATE solution "
                            f"(violation <= {acceptable_inaccurate_violation:.3e})"
                        )
                        return solver_name, problem.status
                    candidates.append({
                        "solver": solver_name,
                        "status": problem.status,
                        "objective": float(problem.value) if problem.value is not None else float("inf"),
                        "violation": violation,
                        "snapshot": _capture_variable_values(),
                    })
                    last_error = f"{solver_name}: optimal_inaccurate"
                    logger.warning("  Trying next solver for better accuracy")
                    continue
                
                # USER_LIMIT: OSQP hit iteration limit - try next solver
                elif problem.status == "user_limit":
                    logger.warning(f"✗ {solver_name} hit iteration limit (user_limit)")
                    if problem.value is not None:
                        logger.warning(f"  Partial objective value: {problem.value:,.2f}")
                    logger.warning(f"  Solution may be inaccurate, trying next solver...")
                    candidates.append({
                        "solver": solver_name,
                        "status": problem.status,
                        "objective": float(problem.value) if problem.value is not None else float("inf"),
                        "violation": _max_constraint_violation(),
                        "snapshot": _capture_variable_values(),
                    })
                    last_error = f"{solver_name}: Hit iteration limit"
                    # Try next solver for better accuracy
                    continue
                
                elif problem.status == cp.INFEASIBLE:
                    logger.warning(f"✗ {solver_name} determined problem is INFEASIBLE")
                    logger.warning(f"  This means constraints cannot be satisfied simultaneously")
                    last_error = f"{solver_name}: Problem is infeasible"
                    infeasible_solver_count += 1
                    # Continue: some solvers can falsely report infeasible on
                    # numerically tight problems while others find a valid solution.
                    continue
                
                elif problem.status == cp.UNBOUNDED:
                    logger.warning(f"✗ {solver_name} determined problem is UNBOUNDED")
                    logger.warning(f"  This may be a numerical issue - trying next solver...")
                    last_error = f"{solver_name}: Problem is unbounded"
                    # Continue to next solver — different solvers have different
                    # numerical tolerances and one solver's "UNBOUNDED" may be
                    # another solver's "OPTIMAL" (e.g., CLARABEL vs SCS).
                    continue
                
                else:
                    logger.warning(f"✗ {solver_name} failed with status: {problem.status}")
                    if problem.value is not None:
                        logger.warning(f"  Objective value was: {problem.value:,.2f}")
                    last_error = f"{solver_name}: {problem.status}"
                    # Try next solver
                    continue
            
            except Exception as e:
                logger.warning(f"✗ {solver_name} raised exception: {str(e)}")
                last_error = f"{solver_name}: {str(e)}"
                # Try next solver
                continue
        
        # All solvers failed to get OPTIMAL - check if we have at least OPTIMAL_INACCURATE
        if candidates:
            status_rank = {
                cp.OPTIMAL: 3,
                cp.OPTIMAL_INACCURATE: 2,
                "user_limit": 1,
            }

            best = min(
                candidates,
                key=lambda c: (
                    -status_rank.get(c["status"], 0),
                    c["violation"],
                    c["objective"],
                ),
            )

            _restore_variable_values(best["snapshot"])
            logger.info(
                "[Solver Compare] Selected %s status=%s violation=%.3e objective=%.6g",
                best["solver"],
                best["status"],
                best["violation"],
                best["objective"],
            )

            if compare_mode:
                for c in candidates:
                    logger.info(
                        "[Solver Compare] candidate solver=%s status=%s violation=%.3e objective=%.6g",
                        c["solver"],
                        c["status"],
                        c["violation"],
                        c["objective"],
                    )

            return (
                f"{best['solver']}_CONSENSUS" if compare_mode else best["solver"],
                best["status"],
            )

        if problem.status == cp.OPTIMAL_INACCURATE:
            logger.warning(f"⚠ All solvers returned OPTIMAL_INACCURATE - proceeding with post-solve enforcement")
            return "LAST_RESORT", problem.status

        # If every attempted solver reported infeasible, treat as genuinely infeasible.
        if infeasible_solver_count == len(solvers):
            logger.error(f"All {len(solvers)} solvers reported INFEASIBLE for {pass_name}")
            return "INFEASIBLE", cp.INFEASIBLE
        
        # Check if all solvers returned OPTIMAL but with high objectives
        # This indicates near-infeasible or highly constrained problem - accept best available
        if best_high_obj_solver is not None:
            logger.warning(f"{'='*80}")
            logger.warning(f"ALL SOLVERS HAD HIGH OBJECTIVE VALUES FOR {pass_name}")
            logger.warning(f"Best available: {best_high_obj_solver} with objective {best_high_obj_value:,.2f}")
            logger.warning(f"This indicates a highly constrained or near-infeasible problem.")
            logger.warning(f"Proceeding with best available solution for post-processing.")
            logger.warning(f"{'='*80}")
            # Re-solve with the best high-objective solver to restore its solution
            for solver, solver_name, _ in solvers:
                if solver_name == best_high_obj_solver:
                    try:
                        if solver == cp.CLARABEL:
                            clarabel_opts = {'tol_gap_abs': 1e-6, 'tol_gap_rel': 1e-6, 'max_iter': 500, 'verbose': False}
                            problem.solve(solver=solver, **clarabel_opts)
                        elif solver == cp.SCS:
                            scs_opts = {'eps_abs': 1e-6, 'eps_rel': 1e-6, 'max_iters': 10000, 'verbose': False}
                            problem.solve(solver=solver, **scs_opts)
                        elif solver == cp.ECOS:
                            ecos_opts = {'abstol': 1e-5, 'reltol': 1e-5, 'feastol': 1e-5, 'max_iters': 200, 'verbose': False}
                            problem.solve(solver=solver, **ecos_opts)
                        else:
                            problem.solve(solver=solver, verbose=False)
                        return f"{best_high_obj_solver}_HIGH_OBJ", problem.status
                    except Exception as e:
                        logger.error(f"Failed to re-solve with {best_high_obj_solver}: {e}")
                        break
        
        # All solvers failed
        logger.error(f"{'='*80}")
        logger.error(f"ALL SOLVERS FAILED FOR {pass_name}")
        logger.error(f"Last error: {last_error}")
        logger.error(f"Problem status: {problem.status}")
        logger.error(f"{'='*80}")
        
        # Provide helpful error messages based on status
        if problem.status == cp.INFEASIBLE:
            # Return special status for infeasibility - will be handled by caller
            return "INFEASIBLE", problem.status
        elif problem.status == cp.UNBOUNDED:
            raise RuntimeError(
                f"Optimization is UNBOUNDED - objective can improve infinitely.\n"
                f"This indicates a problem formulation error (contact support)."
            )
        else:
            raise RuntimeError(
                f"All solvers failed to solve {pass_name}.\n"
                f"Last error: {last_error}\n"
                f"Status: {problem.status}"
            )

    def _calculate_minimum_required_budget(
        self,
        hard_constraints: list,
        budget_constraints: list,
        realized_gains,
        tax_liability,
        constraint_type: str,
        solve_opts: dict,
        mandatory_constraints: list | None = None,
    ) -> dict | None:
        """Calculate the minimum selected budget needed for mandatory constraints."""
        if constraint_type not in {"realized_gains", "tax_budget"}:
            return None

        if mandatory_constraints is not None:
            diagnostic_constraints = list(mandatory_constraints)
        else:
            budget_constraint_ids = {id(c) for c in budget_constraints if c is not None}
            diagnostic_constraints = [
                c for c in hard_constraints
                if id(c) not in budget_constraint_ids
            ]
        objective_expr = realized_gains if constraint_type == "realized_gains" else tax_liability
        diagnostic_problem = cp.Problem(cp.Minimize(objective_expr), diagnostic_constraints)

        try:
            solver_used, status = self._solve_with_fallback(
                diagnostic_problem,
                f"MINIMUM REQUIRED {constraint_type.upper()}",
                **solve_opts,
            )
        except Exception as exc:
            logger.warning(f"Minimum required budget diagnostic failed: {exc}")
            return None

        if status not in [cp.OPTIMAL, cp.OPTIMAL_INACCURATE, "optimal", "optimal_inaccurate"]:
            logger.warning(
                "Minimum required budget diagnostic did not solve optimally: "
                f"solver={solver_used}, status={status}"
            )
            return None

        value = diagnostic_problem.value
        if value is None:
            return None

        return {
            "constraint_type": constraint_type,
            "minimum_required_budget": max(float(value), 0.0),
            "solver": solver_used,
            "status": str(status),
        }

    def _build_minimum_budget_infeasibility_result(
        self,
        *,
        minimum_budget_result: dict,
        current_budget: float,
        budget_label: str,
        budget_value: float,
        current_cash: float,
        cash_floor: float,
    ) -> dict:
        minimum_required_budget = minimum_budget_result["minimum_required_budget"]
        summary = (
            f"The selected {budget_label} is below the minimum required "
            "for mandatory cash and liquidation trades"
        )
        cause = (
            f"The current {budget_label} is ${current_budget:,.0f}, "
            f"but mandatory trades require at least ${minimum_required_budget:,.0f}."
        )
        suggestion = (
            f"Increase the {budget_label} to at least ${minimum_required_budget:,.0f} "
            "to satisfy required cash and forced-liquidation trades."
        )

        details = "\n".join([
            f"Current portfolio: ${budget_value:,.0f}",
            f"Cash on hand: ${current_cash:,.0f}",
            f"Required cash floor: ${cash_floor:,.0f}",
            f"Current {budget_label}: ${current_budget:,.0f}",
            f"Minimum required {budget_label}: ${minimum_required_budget:,.0f}",
            "",
            "The optimization failed before asset-allocation tradeoffs were considered because mandatory trades exceed the selected budget.",
        ])

        return {
            "summary": summary,
            "details": details,
            "causes": [cause],
            "suggestions": [suggestion],
            "technical": {
                "analysis_method": "minimum_budget_diagnostic",
                "minimum_required_budget": minimum_budget_result,
                "total_sell_needed": 0.0,
                "total_buy_needed": 0.0,
                "estimated_tax": 0.0,
                "tax_headroom": current_budget - minimum_required_budget,
                "causes_found": ["MINIMUM_REQUIRED_BUDGET"],
            },
        }

    def _build_constrained_budget_infeasibility_result(
        self,
        *,
        constraint_type: str,
        current_budget: float,
        budget_value: float,
        current_cash: float,
        cash_floor: float,
        minimum_budget_result: dict | None = None,
        allocation_budget_result: dict | None = None,
    ) -> dict:
        if constraint_type == "realized_gains":
            budget_label = "realized gains limit"
        elif constraint_type == "tax_budget":
            budget_label = "tax budget"
        else:
            budget_label = "budget"

        minimum_required = (
            minimum_budget_result.get("minimum_required_budget")
            if minimum_budget_result
            else None
        )
        allocation_required = (
            allocation_budget_result.get("minimum_required_budget")
            if allocation_budget_result
            else None
        )

        if allocation_required is not None and allocation_required > current_budget + 1.0:
            causes = [
                (
                    f"The current {budget_label} is ${current_budget:,.0f}. "
                    f"Mandatory cash and liquidation trades may fit, but the remaining "
                    f"optimization constraints require at least ${allocation_required:,.0f} "
                    f"for an allocation improvement."
                )
            ]
            suggestions = [
                f"Increase the {budget_label} to at least ${allocation_required:,.0f}, "
                "or choose a target allocation closer to current holdings."
            ]
        else:
            causes = [
                (
                    f"The current {budget_label} is ${current_budget:,.0f}. "
                    "Mandatory cash and liquidation trades may fit, but the remaining "
                    "optimization constraints cannot find a feasible allocation improvement "
                    "within that budget."
                )
            ]
            suggestions = [
                f"Increase the {budget_label} or choose a target allocation closer to current holdings."
            ]

        details_parts = [
            f"Current portfolio: ${budget_value:,.0f}",
            f"Cash on hand: ${current_cash:,.0f}",
            f"Required cash floor: ${cash_floor:,.0f}",
            f"Current {budget_label}: ${current_budget:,.0f}",
        ]
        if minimum_required is not None:
            details_parts.append(f"Minimum mandatory {budget_label}: ${minimum_required:,.0f}")
        if allocation_required is not None:
            details_parts.append(f"Minimum allocation-improvement {budget_label}: ${allocation_required:,.0f}")
        details_parts.extend([
            "",
            "The full target-rebalance diagnostics are intentionally suppressed here because asset allocation is lower priority than the selected budget.",
        ])

        return {
            "summary": (
                f"The selected {budget_label} is too restrictive for any additional "
                "allocation improvement after mandatory trades"
            ),
            "details": "\n".join(details_parts),
            "causes": causes,
            "suggestions": suggestions,
            "technical": {
                "analysis_method": "constrained_budget_fallback",
                "minimum_required_budget": minimum_budget_result,
                "allocation_required_budget": allocation_budget_result,
                "total_sell_needed": 0.0,
                "total_buy_needed": 0.0,
                "estimated_tax": 0.0,
                "tax_headroom": (
                    None if minimum_required is None else current_budget - minimum_required
                ),
                "causes_found": ["CONSTRAINED_BUDGET_NO_FEASIBLE_ALLOCATION"],
            },
        }
     
    def _analyze_infeasibility(
        self,
        hard_constraints: list,
        objective,
        symbols: list,
        lot_quantities: np.ndarray,
        current_prices: np.ndarray,
        target_weight_map: dict,
        budget_value: float,
        substitutes_into: dict,
        max_tax_bill: float,
        cash_floor: float,
        cash_ceiling: float,
        current_cash: float,
        constraint_type: str = 'none'  # 'none', 'realized_gains', or 'tax_budget'
    ) -> dict:
        """
        OPTIMIZED infeasibility analysis - uses heuristics FIRST before solver diagnostics.
        
        Performance optimizations:
        1. Pre-compute position analysis (no solver calls)
        2. Heuristic cause detection based on math (no solver calls)
        3. Only run solver diagnostics if heuristics inconclusive
        4. Use fast solver settings with low iteration limits
        5. Early termination once a cause is found
        
        Returns a dictionary with:
        - 'summary': One-line summary of the problem
        - 'details': Detailed explanation
        - 'causes': List of identified causes
        - 'suggestions': List of actionable suggestions
        - 'technical': Technical details for debugging
        """
        import time
        start_time = time.time()
        
        result = {
            'summary': '',
            'details': '',
            'causes': [],
            'suggestions': [],
            'technical': {}
        }
        
        # =========================================================================
        # STEP 1: FAST Pre-compute position analysis (NO SOLVER CALLS)
        # =========================================================================
        symbol_to_indices = {}
        for i, sym in enumerate(symbols):
            if sym not in symbol_to_indices:
                symbol_to_indices[sym] = []
            symbol_to_indices[sym].append(i)
        
        # Calculate positions and gaps
        position_analysis = []
        total_sell_needed = 0.0
        total_buy_needed = 0.0
        total_gains_from_sells = 0.0
        
        for sym in set(symbols):
            if sym == "CASH":
                continue
            
            idxs = symbol_to_indices.get(sym, [])
            if not idxs:
                continue
                
            current_val = float(np.sum(lot_quantities[idxs] * current_prices[idxs]))
            total_cost = float(np.sum(lot_quantities[idxs]))  # Simplified - actual cost basis would be better
            
            # Calculate combined value (including substitutes)
            combined_val = current_val
            for sub_sym in substitutes_into.get(sym, []):
                sub_idxs = symbol_to_indices.get(sub_sym, [])
                if sub_idxs:
                    combined_val += float(np.sum(lot_quantities[sub_idxs] * current_prices[sub_idxs]))
            
            target_val = target_weight_map.get(sym, 0.0) * budget_value
            gap = target_val - combined_val
            
            if abs(gap) > 100:  # Only track meaningful gaps
                # Estimate unrealized gain (simplified: assume 50% of value is gain)
                unrealized_gain_pct = 0.5
                
                position_analysis.append({
                    'symbol': sym,
                    'current': current_val,
                    'combined': combined_val,
                    'target': target_val,
                    'gap': gap,
                    'direction': 'BUY' if gap > 0 else 'SELL',
                    'has_substitutes': len(substitutes_into.get(sym, [])) > 0,
                    'unrealized_gain_pct': unrealized_gain_pct
                })
                
                if gap > 0:
                    total_buy_needed += gap
                else:
                    sell_amount = abs(gap)
                    total_sell_needed += sell_amount
                    # Estimate gains from this sell
                    total_gains_from_sells += sell_amount * unrealized_gain_pct
        
        result['technical']['position_analysis'] = position_analysis
        result['technical']['total_sell_needed'] = total_sell_needed
        result['technical']['total_buy_needed'] = total_buy_needed
        
        # =========================================================================
        # STEP 2: FAST Heuristic cause detection (NO SOLVER CALLS)
        # =========================================================================
        causes_found = []
        
        # Estimate tax impact
        estimated_tax = total_gains_from_sells * 0.2  # Assume 20% blended rate
        tax_headroom = max_tax_bill - estimated_tax
        
        result['technical']['estimated_gains'] = total_gains_from_sells
        result['technical']['estimated_tax'] = estimated_tax
        result['technical']['tax_headroom'] = tax_headroom
        
        # HEURISTIC 1: Tax budget too low?
        # If estimated tax exceeds budget by more than 10%, tax is likely the issue
        if estimated_tax > max_tax_bill * 1.1:
            causes_found.append('TAX_BUDGET')
            logger.debug(f"[Infeasibility] Heuristic: TAX_BUDGET (est ${estimated_tax:,.0f} > budget ${max_tax_bill:,.0f})")
        
        # HEURISTIC 2: Cash balance check
        expected_cash = current_cash + total_sell_needed - total_buy_needed
        logger.warning(
            "[INFEASIBLE DEBUG] cash heuristic inputs "
            f"current_cash={current_cash:,.2f} "
            f"total_sell_needed={total_sell_needed:,.2f} "
            f"total_buy_needed={total_buy_needed:,.2f} "
            f"cash_floor={cash_floor:,.2f} "
            f"cash_ceiling={cash_ceiling if np.isfinite(cash_ceiling) else 'inf'}"
        )
        logger.warning(
            "[INFEASIBLE DEBUG] cash heuristic outputs "
            f"expected_cash={expected_cash:,.2f} "
            f"floor_gap={(expected_cash - cash_floor):,.2f}"
        )
        if expected_cash < cash_floor - 100:  # $100 tolerance
            causes_found.append('CASH_SHORTFALL')
            logger.debug(f"[Infeasibility] Heuristic: CASH_SHORTFALL (expected ${expected_cash:,.0f} < floor ${cash_floor:,.0f})")
            logger.warning(
                "[INFEASIBLE DEBUG] cash shortfall detected "
                f"expected_cash={expected_cash:,.2f} "
                f"cash_floor={cash_floor:,.2f} "
                f"shortfall={(cash_floor - expected_cash):,.2f}"
            )
        elif np.isfinite(cash_ceiling) and expected_cash > cash_ceiling + 100:
            causes_found.append('CASH_EXCESS')
            logger.debug(f"[Infeasibility] Heuristic: CASH_EXCESS (expected ${expected_cash:,.0f} > ceiling ${cash_ceiling:,.0f})")
            logger.warning(
                "[INFEASIBLE DEBUG] cash excess detected "
                f"expected_cash={expected_cash:,.2f} "
                f"cash_ceiling={cash_ceiling:,.2f} "
                f"excess={(expected_cash - cash_ceiling):,.2f}"
            )
        
        # HEURISTIC 3: Check for impossible rebalancing (need to buy but can't sell enough)
        if total_buy_needed > total_sell_needed + current_cash - cash_floor:
            available_for_buys = total_sell_needed + current_cash - cash_floor
            shortfall = total_buy_needed - available_for_buys
            logger.warning(
                "[INFEASIBLE DEBUG] liquidity check "
                f"available_for_buys={available_for_buys:,.2f} "
                f"total_buy_needed={total_buy_needed:,.2f} "
                f"liquidity_shortfall={shortfall:,.2f}"
            )
            if shortfall > 1000:  # More than $1000 shortfall
                causes_found.append('INSUFFICIENT_LIQUIDITY')
                logger.debug(f"[Infeasibility] Heuristic: INSUFFICIENT_LIQUIDITY (need ${total_buy_needed:,.0f}, have ${available_for_buys:,.0f})")
        
        result['technical']['causes_found'] = causes_found
        result['technical']['analysis_method'] = 'heuristic'
        
        # =========================================================================
        # STEP 3: ONLY run solver diagnostics if heuristics found nothing
        # =========================================================================
        if not causes_found:
            logger.debug("[Infeasibility] Heuristics inconclusive, running targeted solver diagnostics...")
            result['technical']['analysis_method'] = 'solver_diagnostic'
            
            # Use fast solver settings
            fast_solve_opts = dict(max_iter=2000, verbose=False)
            
            # Categorize constraints ONCE (reuse for all tests)
            n_constraints = len(hard_constraints)
            tax_constraint_indices = set()
            sub_bound_indices = set()
            
            for i, c in enumerate(hard_constraints):
                cstr = str(c)
                # Tax constraints have rate patterns
                if '0.2' in cstr and '0.2  0.2' in cstr:
                    tax_constraint_indices.add(i)
                # Substitution bounds have 'sum' and >= or <=
                elif ('sum' in cstr.lower() or 'Sum' in cstr) and ('>=' in cstr or '<=' in cstr) and i > 5:
                    sub_bound_indices.add(i)
            
            result['technical']['constraint_counts'] = {
                'total': n_constraints,
                'tax': len(tax_constraint_indices),
                'sub_bounds': len(sub_bound_indices)
            }
            
            # Test 1: Without TAX constraints (most common cause)
            if tax_constraint_indices:
                try:
                    non_tax = [c for i, c in enumerate(hard_constraints) if i not in tax_constraint_indices]
                    test_problem = cp.Problem(objective, non_tax)
                    test_problem.solve(solver=cp.OSQP, **fast_solve_opts)
                    if test_problem.status in [cp.OPTIMAL, cp.OPTIMAL_INACCURATE]:
                        causes_found.append('TAX_BUDGET')
                        logger.debug("[Infeasibility] Solver diagnostic: TAX_BUDGET confirmed")
                except Exception as e:
                    logger.debug(f"[Infeasibility] Tax test error: {e}")
            
            # Test 2: Without substitution bounds (only if tax wasn't the issue)
            if not causes_found and sub_bound_indices:
                try:
                    non_sub = [c for i, c in enumerate(hard_constraints) if i not in sub_bound_indices]
                    test_problem = cp.Problem(objective, non_sub)
                    test_problem.solve(solver=cp.OSQP, **fast_solve_opts)
                    if test_problem.status in [cp.OPTIMAL, cp.OPTIMAL_INACCURATE]:
                        causes_found.append('SUBSTITUTION_BOUNDS')
                        logger.debug("[Infeasibility] Solver diagnostic: SUBSTITUTION_BOUNDS confirmed")
                except Exception as e:
                    logger.debug(f"[Infeasibility] Sub bounds test error: {e}")
            
            result['technical']['causes_found'] = causes_found
        
        elapsed = time.time() - start_time
        result['technical']['analysis_time_ms'] = elapsed * 1000
        logger.debug(f"[Infeasibility] Analysis completed in {elapsed*1000:.1f}ms")
        
        # =========================================================================
        # STEP 4: Generate user-friendly explanation
        # =========================================================================
        
        # Determine user-friendly constraint name based on what the user entered
        if constraint_type == 'realized_gains':
            constraint_name = "Realized Gains Budget"
            constraint_field = "realized gains limit"
        elif constraint_type == 'tax_budget':
            constraint_name = "Tax Budget"
            constraint_field = "tax budget"
        else:
            constraint_name = "Tax Budget"  # Default fallback
            constraint_field = "tax budget"
        
        # Primary cause identification
        if 'TAX_BUDGET' in causes_found:
            result['summary'] = f"{constraint_name} is too low to complete the rebalancing"
            result['causes'].append(
                f"The ${max_tax_bill:,.0f} {constraint_field} is insufficient. "
                f"Selling ${total_sell_needed:,.0f} of positions may generate ~${estimated_tax:,.0f} in taxes."
            )
            logger.warning(
                "[INFEASIBILITY CAUSE] TAX_BUDGET "
                f"constraint_name={constraint_name} "
                f"max_budget={max_tax_bill:,.2f} "
                f"estimated_tax={estimated_tax:,.2f} "
                f"total_sell_needed={total_sell_needed:,.2f}"
            )
            result['suggestions'].append(
                f"Increase the {constraint_field} to at least ${estimated_tax * 1.2:,.0f} (with 20% buffer)"
            )
            result['suggestions'].append(
                "Alternatively, choose a target allocation closer to your current holdings"
            )
        
        if 'CASH_SHORTFALL' in causes_found:
            shortfall = cash_floor - expected_cash
            result['causes'].append(
                f"Cash shortfall: rebalancing would leave ${expected_cash:,.0f} but minimum is ${cash_floor:,.0f}"
            )
            logger.warning(
                "[INFEASIBILITY CAUSE] CASH_SHORTFALL "
                f"expected_cash={expected_cash:,.2f} "
                f"cash_floor={cash_floor:,.2f} "
                f"shortfall={shortfall:,.2f}"
            )
            result['suggestions'].append(
                f"Reduce cash reserve by ${shortfall:,.0f} or adjust target allocations"
            )
        
        if 'CASH_EXCESS' in causes_found:
            excess = expected_cash - cash_ceiling
            result['causes'].append(
                f"Too much cash after rebalancing: ${expected_cash:,.0f} exceeds ceiling ${cash_ceiling:,.0f}"
            )
            logger.warning(
                "[INFEASIBILITY CAUSE] CASH_EXCESS "
                f"expected_cash={expected_cash:,.2f} "
                f"cash_ceiling={cash_ceiling:,.2f} "
                f"excess={excess:,.2f}"
            )
            result['suggestions'].append(
                f"Increase buy targets or reduce sell targets by ${excess:,.0f}"
            )
        
        if 'INSUFFICIENT_LIQUIDITY' in causes_found:
            available = total_sell_needed + current_cash - cash_floor
            shortfall = total_buy_needed - available
            result['causes'].append(
                f"Not enough liquidity: need ${total_buy_needed:,.0f} to buy but only ${available:,.0f} available"
            )
            logger.warning(
                "[INFEASIBILITY CAUSE] INSUFFICIENT_LIQUIDITY "
                f"total_buy_needed={total_buy_needed:,.2f} "
                f"available_for_buys={available:,.2f} "
                f"shortfall={shortfall:,.2f}"
            )
            result['suggestions'].append(
                f"Reduce buy targets by ${shortfall:,.0f} or increase cash available"
            )
        
        if 'SUBSTITUTION_BOUNDS' in causes_found:
            overweight_subs = [p for p in position_analysis if p['gap'] < -5000 and p['has_substitutes']]
            if overweight_subs:
                pos_list = ", ".join([f"{p['symbol']} (${abs(p['gap']):,.0f} over)" for p in overweight_subs[:3]])
                result['causes'].append(
                    f"Cannot reduce overweight substitute positions enough: {pos_list}"
                )
            logger.warning(
                "[INFEASIBILITY CAUSE] SUBSTITUTION_BOUNDS "
                f"overweight_substitute_count={len(overweight_subs)}"
            )
            result['suggestions'].append(
                f"Increase {constraint_field} to allow more selling, or adjust target allocations"
            )
        
        # If no specific cause found, provide general guidance
        if not result['causes']:
            logger.warning(
                "[INFEASIBLE DEBUG] generic fallback triggered "
                f"causes_found={causes_found} "
                f"expected_cash={expected_cash:,.2f} "
                f"cash_floor={cash_floor:,.2f} "
                f"total_sell_needed={total_sell_needed:,.2f} "
                f"total_buy_needed={total_buy_needed:,.2f} "
                f"estimated_tax={estimated_tax:,.2f} "
                f"max_tax_bill={max_tax_bill:,.2f}"
            )
            result['summary'] = "The requested rebalancing cannot be achieved with current constraints"
            result['causes'].append(
                f"The combination of target allocation, {constraint_field}, and cash requirements creates "
                "conflicting constraints that cannot all be satisfied simultaneously."
            )
            logger.warning(
                "[INFEASIBILITY CAUSE] GENERIC_CONFLICT "
                f"constraint_type={constraint_type} "
                f"target_sell={total_sell_needed:,.2f} "
                f"target_buy={total_buy_needed:,.2f} "
                f"expected_cash={expected_cash:,.2f} "
                f"cash_floor={cash_floor:,.2f} "
                f"estimated_tax={estimated_tax:,.2f} "
                f"tax_budget={max_tax_bill:,.2f}"
            )
            result['suggestions'].append(f"Try increasing the {constraint_field}")
            result['suggestions'].append("Try reducing the cash reserve requirement")
            result['suggestions'].append("Try choosing a target allocation closer to current holdings")
        
        # Build detailed explanation
        if not result['summary']:
            result['summary'] = "; ".join(result['causes'][:2])
        
        details_parts = [
            f"Current portfolio: ${budget_value:,.0f}",
            f"Cash on hand: ${current_cash:,.0f}",
            f"{constraint_name}: ${max_tax_bill:,.0f}",
            f"",
            f"Rebalancing requires:",
            f"  • Selling ${total_sell_needed:,.0f} of overweight positions",
            f"  • Buying ${total_buy_needed:,.0f} of underweight positions",
            f"  • Estimated tax impact: ${estimated_tax:,.0f}",
            f"",
            "The optimization failed because these requirements conflict with the constraints."
        ]
        result['details'] = "\n".join(details_parts)

        logger.warning(
            "[INFEASIBILITY SUMMARY] "
            f"summary={result['summary']} "
            f"causes={result['causes']} "
            f"suggestions={result['suggestions']}"
        )
        
        return result

    def _optimize_portfolio(
            self,
            short_term_rate: float,
            long_term_rate: float,
            max_tax_bill: float,
            realized_gains_constraint: float | None,
            legacy_mode: bool,
            wash_sale: bool,
            trade_restrictions: dict | None = None,
            fractional: bool = True,   # kept for API compatibility; rounding behavior preserved
            constraint_type: str = 'none',  # 'none', 'realized_gains', or 'tax_budget'
        ):
        """
        Optimize portfolio allocation using single-pass convex optimization.
        
        OPTIMIZATION STRATEGY:
        ─────────────────────
        Single-Pass: Symbol-level alignment with anti-round-trip constraints
                - Minimizes deviation from target symbol allocations
                - Uses directionality constraints to prevent buying overweight and
                  selling underweight positions (anti-round-trip)
                - Achieves exact target matches within solver tolerance
        
        CONSTRAINT CATEGORIES:
        ──────────────────────
        1. Lot-level: Preserve tax lot integrity (no buying into existing lots)
        2. Budget: Total portfolio value remains constant
        3. Cash: Maintain minimum cash floor with upper bound
        4. Tax: Limit realized gains and tax liability
        5. Anti-round-trip: Prevent buying overweight / selling underweight securities
        6. Wash sale: Block trading of flagged lots
        
        PARAMETERS:
        ───────────
        short_term_rate: Tax rate for short-term gains
        long_term_rate: Tax rate for long-term gains
        max_tax_bill: Maximum total tax liability allowed
        realized_gains_constraint: Maximum total realized gains (optional)
        legacy_mode: If True, use category-level steering; if False, use symbol-level
        wash_sale: If True, block trading of wash sale flagged lots
        constraint_type: 'none', 'realized_gains', or 'tax_budget' - used for error messages
        
        RETURNS:
        ────────
        Tuple of (optimized_portfolio, tax_metrics, tracking_error, adjusted_allocation)
        """
        
        perf_start = time.perf_counter()

        # ========== VALIDATION: Pre-flight checks ==========
        logger.info("=" * 80)
        logger.info("VALIDATION: Running pre-optimization input validation")
        logger.info("=" * 80)
        
        is_valid, validation_errors, validation_warnings = self._validate_optimization_inputs(
            short_term_rate=short_term_rate,
            long_term_rate=long_term_rate,
            max_tax_bill=max_tax_bill,
            realized_gains_constraint=realized_gains_constraint
        )
        
        # Log warnings
        for warning in validation_warnings:
            logger.warning(f"VALIDATION WARNING: {warning}")
        
        # If validation failed, raise exception with all errors
        if not is_valid:
            error_msg = "Optimization input validation failed:\n" + "\n".join(f"  - {err}" for err in validation_errors)
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        logger.info("✓ All validation checks passed")
        logger.info("=" * 80)

        DEFAULT_CAT = "Uncategorized"
        trade_restrictions = trade_restrictions or {}

        _diagnostic_print(
            "[Optimizer Debug] start "
            f"constraint_type={constraint_type} "
            f"legacy_mode={legacy_mode} "
            f"wash_sale={wash_sale} "
            f"max_tax_bill={float(max_tax_bill):,.2f} "
            f"realized_gains_constraint="
            f"{'None' if realized_gains_constraint is None else f'{float(realized_gains_constraint):,.2f}'} "
            f"portfolio_rows={len(self.portfolio)} "
            f"target_rows={len(self.target_allocation)}"
        )
        if trade_restrictions:
            _diagnostic_print(f"[Optimizer Debug] trade_restrictions={trade_restrictions}")
        if getattr(self, "_excluded_securities", None):
            _diagnostic_print(f"[Optimizer Debug] excluded_securities={sorted(self._excluded_securities)}")
        
        # Check Substitution column status
        has_substitution_col = 'Substitution' in self.portfolio.columns
        logger.debug(f"Portfolio columns: {self.portfolio.columns}")
        if has_substitution_col:
            substitution_values = self.portfolio.get_column("Substitution").to_list()
            non_null_subs = [s for s in substitution_values if s is not None]
            logger.debug(f"Substitution mappings active: {len(non_null_subs)}")

        # ---------- Pull inputs ----------
        symbols = self.portfolio["Symbol"].to_list()
        lot_quantities = self.portfolio["Lot Quantity"].to_numpy()
        lot_costs = self.portfolio["Lot Cost Basis"].to_numpy()
        lot_dates = self.portfolio["Date"].to_list()
        wash_flags = self.portfolio.get_column("Wash Sale Blocked").to_list()
        asset_classes_raw = self.portfolio.get_column("Asset Class").to_list()
        categories = self.portfolio["Category"].fill_null(DEFAULT_CAT).to_list()

        n = len(symbols)
        idx = np.arange(n)
        is_cash = (np.array(symbols, dtype=object) == "CASH")

        # Terms
        today = datetime.datetime.today().date()
        holding_days = np.array([(today - d).days for d in lot_dates])
        is_long_term = holding_days > 365

        # ---------- Prices (force CASH=1.0) ----------
        # Normalize FI prices (price/100) only when needed
        price_df = self.portfolio.select(["Symbol", "Current Price", "Security Type"]).unique(subset=["Symbol"])
        fixed_income = {"T-Bills", "CDs", "Fixed Income", "Mortgage-Backed"}
        price_map = {}
        for sym, px, sec in price_df.iter_rows():
            if sym == "CASH":
                price_map[sym] = 1.0
            else:
                price_map[sym] = float((px / 100.0) if (sec in fixed_income and px > 1) else px or 0.0)

        current_prices = np.array([1.0 if s == "CASH" else price_map.get(s, 0.0) for s in symbols], dtype=float)

        # ---------- Portfolio dollars ----------
        budget_value = float(np.sum(lot_quantities * current_prices))

        # ---------- Identify frozen excluded / unsellable securities ----------
        # Excluded (non-wash-sale) securities are frozen (no buy/sell). We also
        # freeze Buy Only names whose effective target is 0% because those names
        # cannot be sold, so treating 0% as a required destination makes the
        # optimization infeasible. For those names, we keep their current weight
        # and rescale the rest of the target to the remaining sleeve.
        excluded_set = getattr(self, '_excluded_securities', set())
        frozen_managed_value = 0.0
        frozen_security_values = {}  # {symbol: market_value}
        if excluded_set and not wash_sale:
            # No wash sale mode: ALL excluded securities are fully frozen
            for i, sym in enumerate(symbols):
                if sym in excluded_set:
                    val = float(lot_quantities[i] * current_prices[i])
                    frozen_managed_value += val
                    frozen_security_values[sym] = frozen_security_values.get(sym, 0.0) + val
        elif excluded_set:
            # Wash sale mode: only freeze non-wash-sale excluded securities
            wash_sale_syms = {
                symbols[i] for i, flag in enumerate(wash_flags)
                if flag == "Yes" and symbols[i] != "CASH"
            }
            for i, sym in enumerate(symbols):
                if sym in excluded_set and sym not in wash_sale_syms:
                    val = float(lot_quantities[i] * current_prices[i])
                    frozen_managed_value += val
                    frozen_security_values[sym] = frozen_security_values.get(sym, 0.0) + val

        # Also note excluded unmanaged securities (already removed from portfolio)
        excluded_unmanaged_value = sum(
            p.get('market_value', 0) for p in getattr(self, '_excluded_unmanaged_positions', [])
        )

        logger.info(f"📊 Budget: total=${budget_value:,.2f}, frozen_managed=${frozen_managed_value:,.2f}, "
                     f"excluded_unmanaged=${excluded_unmanaged_value:,.2f}")

        # ---------- Targets (include CASH) ----------
        # NOTE: Use budget_value (full portfolio) for cash floor/ceiling computation,
        # so cash constraints remain relative to the total portfolio.
        self.adjusted_target_allocation = self._effective_target_allocation_with_cash(budget_value)
        target_weight_map = dict(zip(
            self.adjusted_target_allocation["Symbol"],
            self.adjusted_target_allocation["Target Weight"])
        )
        
        # Check if we have substituted securities (indicated by Substitution column)
        # If substitutions exist, we need to use Substitution for target allocation matching
        has_substitutions = 'Substitution' in self.portfolio.columns
        
        # IMPORTANT: Remove substitute securities from target_weight_map
        # Substitutes (e.g., HTRB→BND) should NOT have their own target weight.
        # Their value flows into their substitution target (BND).
        # If they appear in target allocation, it's likely a data error or
        # the original target before substitution mapping was applied.
        # NOTE: A symbol that maps to ITSELF (e.g., VTI→VTI) is the TARGET,
        # not a substitute — do NOT remove it.
        if has_substitutions:
            substitution_col = self.portfolio.get_column("Substitution").to_list()
            symbols_list = self.portfolio["Symbol"].to_list()
            substitute_symbols = set()
            for sym, sub in zip(symbols_list, substitution_col):
                if sub and sub != sym:  # Only true substitutes (maps to a DIFFERENT symbol)
                    substitute_symbols.add(sym)
            
            # Remove substitute symbols from target_weight_map
            for sub_sym in substitute_symbols:
                if sub_sym in target_weight_map:
                    logger.info(f"Removing substitute '{sub_sym}' from target_weight_map (weight was {target_weight_map[sub_sym]:.4f})")
                    del target_weight_map[sub_sym]

        # Restriction-aware frozen targets:
        # - Hold: both sides blocked, so freeze at current weight
        # - Buy Only: sells blocked, so if target needs a sell-down, freeze
        # - Sell Only: buys blocked, so if target needs a buy-up, freeze
        #
        # This keeps the restriction semantics intact while preventing the
        # optimizer from treating an impossible target as mandatory.
        buy_only_symbols = set(trade_restrictions.get("Buy", []))
        sell_only_symbols = set(trade_restrictions.get("Sell", []))
        hold_only_symbols = set(trade_restrictions.get("Hold", []))
        if (buy_only_symbols or sell_only_symbols or hold_only_symbols) and budget_value > 0:
            symbol_current_values = {}
            for i, sym in enumerate(symbols):
                if sym == "CASH":
                    continue
                symbol_current_values[sym] = symbol_current_values.get(sym, 0.0) + float(lot_quantities[i] * current_prices[i])

            frozen_buy_only = {}
            frozen_sell_only = {}
            frozen_hold_only = {}

            all_restricted_symbols = sorted(buy_only_symbols | sell_only_symbols | hold_only_symbols)
            for sym in all_restricted_symbols:
                current_val = float(symbol_current_values.get(sym, 0.0))
                if current_val <= 1e-9:
                    continue

                target_val = float(target_weight_map.get(sym, 0.0) or 0.0) * budget_value
                should_freeze = False
                bucket = None

                if sym in hold_only_symbols:
                    should_freeze = True
                    bucket = frozen_hold_only
                elif sym in buy_only_symbols and target_val < current_val - 1.0:
                    should_freeze = True
                    bucket = frozen_buy_only
                elif sym in sell_only_symbols and target_val > current_val + 1.0:
                    should_freeze = True
                    bucket = frozen_sell_only

                if not should_freeze:
                    continue

                frozen_managed_value += current_val
                frozen_security_values[sym] = current_val
                bucket[sym] = current_val

            if frozen_buy_only:
                logger.info(
                    "🔒 Freezing Buy Only symbols that would require sells: "
                    f"{ {sym: round(val, 2) for sym, val in sorted(frozen_buy_only.items())} }"
                )
                _diagnostic_print(
                    "[Optimizer Diagnostic] frozen_buy_only_conflicts="
                    f"{ {sym: round(val, 2) for sym, val in sorted(frozen_buy_only.items())} }"
                )

            if frozen_sell_only:
                logger.info(
                    "🔒 Freezing Sell Only symbols that would require buys: "
                    f"{ {sym: round(val, 2) for sym, val in sorted(frozen_sell_only.items())} }"
                )
                _diagnostic_print(
                    "[Optimizer Diagnostic] frozen_sell_only_conflicts="
                    f"{ {sym: round(val, 2) for sym, val in sorted(frozen_sell_only.items())} }"
                )

            if frozen_hold_only:
                logger.info(
                    "🔒 Freezing Hold symbols at current weight: "
                    f"{ {sym: round(val, 2) for sym, val in sorted(frozen_hold_only.items())} }"
                )
                _diagnostic_print(
                    "[Optimizer Diagnostic] frozen_hold_conflicts="
                    f"{ {sym: round(val, 2) for sym, val in sorted(frozen_hold_only.items())} }"
                )

        # ---------- Rescale target weights for excluded securities ----------
        # Excluded (frozen) securities can't change. Set their target weight to
        # their actual frozen weight (so tracking error = 0 for them). Redistribute
        # the freed/consumed weight proportionally among non-excluded non-cash
        # securities, making targets achievable with available funds.
        if frozen_security_values and budget_value > 0:
            cash_weight = target_weight_map.get("CASH", 0.0)
            
            # Compute weight freed by replacing model targets with actual frozen weights
            weight_freed = 0.0
            for sym, frozen_val in frozen_security_values.items():
                actual_weight = frozen_val / budget_value
                model_weight = target_weight_map.get(sym, 0.0)
                weight_freed += (model_weight - actual_weight)
                target_weight_map[sym] = actual_weight
                logger.info(f"   🔒 {sym}: target {model_weight:.4f} → frozen {actual_weight:.4f} "
                            f"(freed {model_weight - actual_weight:+.4f})")
            
            # Redistribute freed weight to non-excluded non-cash securities
            non_excluded_non_cash = {
                s: w for s, w in target_weight_map.items()
                if s != "CASH" and s not in frozen_security_values
            }
            non_excluded_sum = sum(non_excluded_non_cash.values())
            
            if non_excluded_sum > 1e-9 and abs(weight_freed) > 1e-9:
                scale_factor = (non_excluded_sum + weight_freed) / non_excluded_sum
                for sym in non_excluded_non_cash:
                    old_w = target_weight_map[sym]
                    target_weight_map[sym] = old_w * scale_factor
                    logger.debug(f"   📐 {sym}: target {old_w:.4f} → {target_weight_map[sym]:.4f} "
                                 f"(×{scale_factor:.4f})")
                
                logger.info(f"   📐 Rescaled {len(non_excluded_non_cash)} non-excluded securities "
                            f"(freed weight={weight_freed:+.4f}, scale={scale_factor:.4f})")
            
            # Update adjusted_target_allocation DataFrame to reflect rescaled weights
            rescaled_rows = [(sym, target_weight_map.get(sym, 0.0)) 
                             for sym in self.adjusted_target_allocation["Symbol"]]
            self.adjusted_target_allocation = pl.DataFrame(
                rescaled_rows, schema=["Symbol", "Target Weight"], orient="row"
            )

        # Initialize category_target_map (will be populated if legacy_mode is True)
        category_target_map = {}
        category_current_values = {}
        self.category_target_map = {}  # Store for external access
        
        # For legacy mode, we need category-based target weights
        # Aggregate target allocation by category
        if legacy_mode:
            logger.info("Legacy mode: Building category-based target weight map")
            
            # Join target allocation with portfolio_info to get categories
            target_with_cat = self.adjusted_target_allocation.join(
                self.portfolio_info.select(["Symbol", "Category"]),
                on="Symbol",
                how="left"
            ).with_columns([
                pl.col("Category").fill_null(pl.col("Symbol"))  # Use symbol if no category
            ])
            
            # Aggregate by category
            category_target_map = {}
            for cat, wt_group in target_with_cat.group_by("Category"):
                category_name = cat[0] if isinstance(cat, tuple) else cat
                total_weight = float(wt_group["Target Weight"].sum())
                category_target_map[category_name] = total_weight
            
            logger.info(f"Category target weights: {category_target_map}")
            self.category_target_map = category_target_map  # Expose for template rendering

            # Current category values are used later by legacy target mapping
            # and the legacy objective, including runs that also use substitutions.
            categories_arr = np.array(categories)
            unique_cats = set(c for c in categories if c and c != "CASH")
            for cat in unique_cats:
                cat_mask = (categories_arr == cat) & (lot_quantities > 1e-9)
                category_current_values[cat] = float(np.sum(lot_quantities[cat_mask] * current_prices[cat_mask]))
        
        # Determine allocation strategy based on mode and substitutions
        if has_substitutions:
            # WITH SUBSTITUTIONS (Standard or Legacy): Use Substitution symbol for grouping
            # ITOT→VTI and IUSG→VTI both map to VTI's target
            # This creates "virtual categories" based on substitution target
            logger.info("Substitution mode: Using Substitution column for target allocation matching")
            
            substitution_col = self.portfolio.get_column("Substitution").to_list()
            
            # For each lot, use Substitution if present, otherwise use Symbol (or Category in legacy mode)
            # ITOT lots: Substitution='VTI', so use VTI's target weight
            # IUSG lots: Substitution='VTI', so use VTI's target weight  
            # VTI lots: Substitution=None, so use VTI's target weight (Symbol='VTI')
            # Both ITOT and IUSG count toward VTI's target (NOT "Equity - US Large Cap" category)
            target_values_static = {}
            if legacy_mode:
                # Legacy mode: fallback to category if no substitution
                for s, sub, cat in zip(symbols, substitution_col, categories):
                    allocation_key = sub if sub else cat  # Use substitution first, else category
                    # Look up in target_weight_map (symbols) or category_target_map (categories)
                    target_values_static[s] = target_weight_map.get(allocation_key, 0.0) * budget_value
                    if target_values_static[s] == 0.0 and allocation_key in category_target_map:
                        target_values_static[s] = category_target_map.get(allocation_key, 0.0) * budget_value
            else:
                # Standard mode: fallback to symbol if no substitution
                for s, sub in zip(symbols, substitution_col):
                    allocation_key = sub if sub else s  # Use substitution if present, else symbol
                    target_values_static[s] = target_weight_map.get(allocation_key, 0.0) * budget_value
                
        elif legacy_mode:
            # LEGACY MODE without substitutions: Use Category for allocation
            logger.info("Legacy mode: Using Category for target allocation matching")
            target_values_static = {}
            for s, cat in zip(symbols, categories):
                target_values_static[s] = category_target_map.get(cat, 0.0) * budget_value
        else:
            # STANDARD MODE without substitutions: Use Symbol for allocation
            # Normal mode: Match Symbol to target allocation Symbol
            target_values_static = {s: target_weight_map.get(s, 0.0) * budget_value for s in symbols}

        # ============================================================================
        # DECISION VARIABLES
        # ============================================================================
        q = cp.Variable(n)                     # Final quantity for each lot
        sold = cp.Variable(n, nonneg=True)     # Shares sold from each lot
        bought = cp.Variable(n, nonneg=True)   # Shares bought into each lot
        
        
        # ============================================================================
        # CONSTRAINT COLLECTION
        # ============================================================================
        hard_constraints = []
        minimum_budget_constraints = []
        
        
        # ────────────────────────────────────────────────────────────────────────────
        # CONSTRAINT 1: LOT INTEGRITY
        # ────────────────────────────────────────────────────────────────────────────
        # - Block wash sale lots from trading
        # - Block buying into existing lots (preserve cost basis)
        # - Inventory flow: final_qty = start_qty + bought - sold
        # ────────────────────────────────────────────────────────────────────────────
        
        # 1a. Wash sale restrictions
        # Block BUYS on wash-sale-flagged securities. Sells remain allowed.
        # If the optimizer needs to add exposure, it must buy the account
        # substitute proxy instead of the wash-sale security itself.
        if wash_sale:
            excluded_set = getattr(self, '_excluded_securities', set())
            wash_block_idx = [
                i for i, flag in enumerate(wash_flags)
                if flag == "Yes" and symbols[i] != "CASH"
            ]
            if wash_block_idx:
                wash_buy_block = bought[wash_block_idx] == 0
                hard_constraints += [wash_buy_block]
                minimum_budget_constraints += [wash_buy_block]
                wash_symbols = sorted(set(symbols[i] for i in wash_block_idx))
                logger.info(f"[Constraint 1a] Wash sale: Blocked BUYS on {len(wash_block_idx)} lots ({wash_symbols}), sells allowed")
                wash_lot_rows = [
                    {
                        "idx": int(i),
                        "symbol": symbols[i],
                        "lot_quantity": float(lot_quantities[i]),
                        "current_price": float(current_prices[i]),
                        "current_value": float(lot_quantities[i] * current_prices[i]),
                        "excluded": symbols[i] in excluded_set,
                    }
                    for i in wash_block_idx
                ]
                logger.debug(
                    "[WASH_SALE_DEBUG] constraint_1a_buy_block "
                    f"wash_symbols={wash_symbols} blocked_lots={wash_lot_rows}"
                )

        # 1b. Block buying into existing lots
        existing_idx = idx[(lot_quantities > 0) & (~is_cash)]
        if existing_idx.size:
            existing_buy_block = bought[existing_idx] == 0
            hard_constraints += [existing_buy_block]
            minimum_budget_constraints += [existing_buy_block]
            logger.info(f"[Constraint 1b] Lot integrity: Blocked buying into {existing_idx.size} existing lots")

        # 1c. Inventory flow equations
        inventory_constraints = [
            q == lot_quantities + bought - sold,  # Inventory flow
            sold <= lot_quantities,               # Can't oversell
            q >= 0                                # No negative positions
        ]
        hard_constraints += inventory_constraints
        minimum_budget_constraints += inventory_constraints

        if wash_sale and getattr(self, '_wash_sale_proxy_substitutions', None):
            wash_sale_proxy_map = {
                str(proxy or '').strip(): str(target or '').strip()
                for proxy, target in getattr(self, '_wash_sale_proxy_substitutions', {}).items()
                if str(proxy or '').strip() and str(target or '').strip()
            }
            proceeds_cap_rows = []
            for proxy_symbol, target_symbol in wash_sale_proxy_map.items():
                proxy_idx = np.array(
                    [i for i, sym in enumerate(symbols) if sym == proxy_symbol],
                    dtype=int,
                )
                target_idx = np.array(
                    [
                        i for i, (sym, flag) in enumerate(zip(symbols, wash_flags))
                        if sym == target_symbol and flag == "Yes"
                    ],
                    dtype=int,
                )
                if proxy_idx.size == 0 or target_idx.size == 0:
                    proceeds_cap_rows.append({
                        "proxy": proxy_symbol,
                        "target": target_symbol,
                        "proxy_lots": int(proxy_idx.size),
                        "target_wash_lots": int(target_idx.size),
                        "action": "skipped_missing_lots",
                    })
                    continue

                proxy_cap_constraints = [
                    cp.sum(cp.multiply(current_prices[proxy_idx], bought[proxy_idx]))
                    <= cp.sum(cp.multiply(current_prices[target_idx], sold[target_idx]))
                ]
                hard_constraints += proxy_cap_constraints
                minimum_budget_constraints += proxy_cap_constraints
                proceeds_cap_rows.append({
                    "proxy": proxy_symbol,
                    "target": target_symbol,
                    "proxy_lots": int(proxy_idx.size),
                    "target_wash_lots": int(target_idx.size),
                    "proxy_price": float(current_prices[proxy_idx[0]]) if proxy_idx.size else 0.0,
                    "target_current_value": float(np.sum(lot_quantities[target_idx] * current_prices[target_idx])),
                    "action": "buy_value_capped_by_target_sale_proceeds",
                })
            if proceeds_cap_rows:
                logger.info(
                    f"[Constraint 1e] Wash-sale proxy buys capped by sale proceeds: {proceeds_cap_rows}"
                )
                logger.debug(
                    "[WASH_SALE_DEBUG] constraint_1e_proxy_proceeds_cap "
                    f"rows={proceeds_cap_rows}"
                )

        # 1d. Directional trading restrictions
        # Keep Buy/Sell/Hold names in the managed sleeve; only restrict how they trade.
        direction_rule_sets = [
            ("Hold", trade_restrictions.get("Hold", []), True, True, "no buys or sells"),
            ("Buy", trade_restrictions.get("Buy", []), False, True, "sells blocked; buys allowed"),
            ("Sell", trade_restrictions.get("Sell", []), True, False, "buys blocked; sells allowed"),
        ]
        for label, restricted_symbols, block_buys, block_sells, note in direction_rule_sets:
            active_symbols = sorted({sym for sym in restricted_symbols if sym and sym != "CASH"})
            if not active_symbols:
                continue

            restricted_idx = np.array([i for i, sym in enumerate(symbols) if sym in active_symbols], dtype=int)
            if restricted_idx.size == 0:
                continue

            if block_buys:
                restricted_buy_block = bought[restricted_idx] == 0
                hard_constraints += [restricted_buy_block]
                minimum_budget_constraints += [restricted_buy_block]
            if block_sells:
                restricted_sell_block = sold[restricted_idx] == 0
                hard_constraints += [restricted_sell_block]
                minimum_budget_constraints += [restricted_sell_block]

            logger.info(
                f"[Constraint 1d] {label} restriction: {note} on {restricted_idx.size} lots ({active_symbols})"
            )

        # 1f. Forced liquidation of off-model individual stocks.
        subsectors_raw = (
            self.portfolio.get_column("Subsector").to_list()
            if "Subsector" in self.portfolio.columns
            else [None] * n
        )
        forced_liquidation_result = find_off_model_individual_stock_lots(
            symbols=symbols,
            quantities=lot_quantities,
            asset_classes=asset_classes_raw,
            subsectors=subsectors_raw,
            original_target_symbols=getattr(self, "_original_target_symbols", set()),
            excluded_symbols=excluded_set,
            sell_blocked_symbols=set(trade_restrictions.get("Hold", [])) | set(trade_restrictions.get("Buy", [])),
        )
        forced_liquidation_lot_indices = set(forced_liquidation_result.lot_indices)
        self._forced_individual_stock_liquidation_lots = forced_liquidation_result.lot_indices

        if forced_liquidation_result.lot_indices:
            forced_idx = np.array(forced_liquidation_result.lot_indices, dtype=int)
            forced_liquidation_constraints = [
                sold[forced_idx] == lot_quantities[forced_idx],
                bought[forced_idx] == 0,
            ]
            hard_constraints += forced_liquidation_constraints
            minimum_budget_constraints += forced_liquidation_constraints
            logger.info(
                "[Constraint 1f] Forced full sell for off-model individual stocks: "
                f"symbols={list(forced_liquidation_result.symbols)} "
                f"lots={len(forced_liquidation_result.lot_indices)}"
            )
        if forced_liquidation_result.skipped_symbols:
            logger.info(
                "[Constraint 1f] Skipped off-model individual stocks with explicit sell blocks: "
                f"{list(forced_liquidation_result.skipped_symbols)}"
            )
        
        
        # 1g. Legacy bucket: force-sell non-model holdings whose asset category
        # is not one the target model allocates to. In legacy mode a non-model
        # fund/ETF may only be held when it belongs to an asset category the
        # model targets; anything in a different asset category (e.g. a utility
        # ETF against an equity/fixed-income model) is recommended for sale
        # unless the user applies a Trading exclusion. The allowed categories are
        # data-driven: exactly the categories present in the target model
        # (``category_target_map``).
        if legacy_mode:
            substitution_col_for_rule = (
                self.portfolio.get_column("Substitution").to_list()
                if "Substitution" in self.portfolio.columns
                else [None] * n
            )
            # Allowed categories are those the model actually allocates to. The
            # target map also carries synthetic zero-weight rows for held
            # symbols, so a category only counts when its target weight is
            # positive (otherwise a held off-model fund would appear to belong
            # to a "targeted" category and escape the rule).
            allowed_legacy_categories = {
                cat for cat, wt in category_target_map.items() if wt > 1e-9
            }
            off_category_result = find_off_category_legacy_lots(
                symbols=symbols,
                quantities=lot_quantities,
                categories=categories,
                allowed_categories=allowed_legacy_categories,
                substitutions=substitution_col_for_rule,
                target_symbols=getattr(self, "_original_target_symbols", set()),
                excluded_symbols=excluded_set,
                sell_blocked_symbols=set(trade_restrictions.get("Hold", [])) | set(trade_restrictions.get("Buy", [])),
            )
            new_off_category_lots = [
                i for i in off_category_result.lot_indices
                if i not in forced_liquidation_lot_indices
            ]
            if new_off_category_lots:
                off_idx = np.array(new_off_category_lots, dtype=int)
                off_category_constraints = [
                    sold[off_idx] == lot_quantities[off_idx],
                    bought[off_idx] == 0,
                ]
                hard_constraints += off_category_constraints
                minimum_budget_constraints += off_category_constraints
                forced_liquidation_lot_indices.update(new_off_category_lots)
                logger.info(
                    "[Constraint 1g] Legacy bucket: forced full sell for off-category "
                    f"non-model holdings symbols={sorted({symbols[i] for i in new_off_category_lots})} "
                    f"lots={len(new_off_category_lots)}"
                )
            if off_category_result.skipped_symbols:
                logger.info(
                    "[Constraint 1g] Legacy bucket: kept off-category holdings with "
                    f"Trading exclusion / sell block: {list(off_category_result.skipped_symbols)}"
                )
        
        
        # ────────────────────────────────────────────────────────────────────────────
        # CONSTRAINT 2: BUY RESTRICTIONS (Legacy Mode)
        # ────────────────────────────────────────────────────────────────────────────
        # In legacy mode, only allow buying securities that are IN the target allocation
        # Non-target securities can only be SOLD (for tax-loss harvesting)
        # ────────────────────────────────────────────────────────────────────────────
        
        target_symbols_set = {sym for sym, wt in target_weight_map.items() if wt > 0 and sym != "CASH"}
        wash_sale_proxy_symbols = set(getattr(self, '_wash_sale_proxy_substitutions', {}) or {})
        # Lot-level direction blocks added by model logic. Post-solve cleanup
        # must obey these just like explicit user restrictions.
        lots_buy_blocked = set()
        lots_sell_blocked = set()
        
        # ────────────────────────────────────────────────────────────────────────────
        # CONSTRAINT 2: BUY ONLY TARGET SECURITIES (or their substitutes)
        # ────────────────────────────────────────────────────────────────────────────
        # Only allow buying securities that are IN the target allocation
        # OR are substitutes for a target security
        # Non-target securities can only be SOLD (for rebalancing/tax-loss harvesting)
        # Block ALL lots of non-target securities from buying (not just empty lots)
        # ────────────────────────────────────────────────────────────────────────────
        
        logger.info(f"[Constraint 2] Only buying target securities (or substitutes)")
        logger.info(f"   Target symbols: {sorted(target_symbols_set)}")
        
        # Build a set of symbols that can be bought (targets + substitutes of targets)
        buyable_symbols = set(target_symbols_set)
        if has_substitutions:
            substitution_col = self.portfolio.get_column("Substitution").to_list()
            for i, (sym, sub) in enumerate(zip(symbols, substitution_col)):
                # If this symbol substitutes for a target, allow buying it
                if sub and sub in target_symbols_set:
                    buyable_symbols.add(sym)
                    logger.debug(f"   {sym}: SUBSTITUTE for {sub} (target) - buying allowed")
        logger.debug(
            "[WASH_SALE_DEBUG] buyable_symbols "
            f"target_symbols={sorted(target_symbols_set)} "
            f"substitution_enabled={has_substitutions} "
            f"wash_sale_proxy_symbols={sorted(set(getattr(self, '_wash_sale_proxy_substitutions', {}) or {}))} "
            f"buyable_symbols={sorted(buyable_symbols)}"
        )
        
        non_target_buy_indices = []
        for i, sym in enumerate(symbols):
            if sym == "CASH":
                continue
            # Block ALL buys for NON-target and NON-substitute symbols
            if sym not in buyable_symbols:
                non_target_buy_indices.append(i)
        
        if non_target_buy_indices:
            ntb_idx = np.array(non_target_buy_indices, dtype=int)
            non_target_buy_block = bought[ntb_idx] == 0
            hard_constraints += [non_target_buy_block]
            minimum_budget_constraints += [non_target_buy_block]
            logger.info(f"   Blocked buying {len(non_target_buy_indices)} lots of non-target/non-substitute securities")
        
        # ────────────────────────────────────────────────────────────────────────────
        # CONSTRAINT 2b: EXCLUDED SECURITIES (no trading allowed)
        # ────────────────────────────────────────────────────────────────────────────
        # Securities in the excluded list cannot be bought OR sold.
        # EXCEPTION: Wash-sale-flagged excluded securities only block BUYS.
        # The buy block for wash sale securities is handled by Constraint 1a.
        # ────────────────────────────────────────────────────────────────────────────
        
        excluded_set = getattr(self, '_excluded_securities', set())
        # Build set of wash sale symbols for quick lookup
        wash_sale_symbols = set()
        if wash_sale:
            wash_sale_symbols = {
                symbols[i] for i, flag in enumerate(wash_flags)
                if flag == "Yes" and symbols[i] != "CASH"
            }
        
        if excluded_set:
            logger.info(f"[Constraint 2b] Excluded securities: {sorted(excluded_set)}")
            logger.debug(
                "[WASH_SALE_DEBUG] constraint_2b_exclusions "
                f"excluded_set={sorted(excluded_set)} wash_sale={wash_sale} "
                f"wash_sale_symbols={sorted(wash_sale_symbols)}"
            )
            freeze_buy_indices = []
            freeze_sell_indices = []
            wash_sale_excluded_lots = 0
            for i, sym in enumerate(symbols):
                if sym in excluded_set:
                    if sym in wash_sale_symbols:
                        # Wash sale excluded: buys already blocked by 1a;
                        # sells remain allowed.
                        wash_sale_excluded_lots += 1
                    else:
                        # Normal excluded: freeze completely (no buys, no sells)
                        freeze_buy_indices.append(i)
                        freeze_sell_indices.append(i)
                        logger.debug(f"   {sym}: EXCLUDED - no trading allowed")
            if freeze_buy_indices:
                fb_idx = np.array(freeze_buy_indices, dtype=int)
                excluded_buy_block = bought[fb_idx] == 0
                hard_constraints += [excluded_buy_block]
                minimum_budget_constraints += [excluded_buy_block]
            if freeze_sell_indices:
                fs_idx = np.array(freeze_sell_indices, dtype=int)
                excluded_sell_block = sold[fs_idx] == 0
                hard_constraints += [excluded_sell_block]
                minimum_budget_constraints += [excluded_sell_block]
            excluded_lots_blocked = len(freeze_sell_indices)
            if excluded_lots_blocked > 0:
                logger.info(f"   Blocked all trading on {excluded_lots_blocked} lots of excluded securities")
            if wash_sale_excluded_lots > 0:
                logger.info(f"   Wash sale excluded: {wash_sale_excluded_lots} lots (buys blocked by 1a, sells allowed)")
            logger.debug(
                "[WASH_SALE_DEBUG] constraint_2b_result "
                f"freeze_buy_indices={freeze_buy_indices} "
                f"freeze_sell_indices={freeze_sell_indices} "
                f"wash_sale_excluded_lots={wash_sale_excluded_lots}"
            )
        
        
        # ────────────────────────────────────────────────────────────────────────────
        # CONSTRAINT 3: SUBSTITUTION PROTECTION (if substitutions exist)
        # ────────────────────────────────────────────────────────────────────────────
        # Apply substitute-group direction rules using the same intent as legacy:
        # - If group is underweight: buy target, freeze sells of existing holdings
        # - If group is overweight: prefer selling substitute/non-target holdings;
        #   only sell the target security if it is itself above target
        # Example: ITOT substitutes for VTI → protect ITOT if ITOT+VTI < target
        # ────────────────────────────────────────────────────────────────────────────
        
        if has_substitutions:
            substitution_col = self.portfolio.get_column("Substitution").to_list()
            
            # Calculate combined value for each substitution target
            substitution_current_values = {}
            for sub_target in set(sub for sub in substitution_col if sub):
                sub_lots = [j for j, (sub, qty) in enumerate(zip(substitution_col, lot_quantities))
                           if sub == sub_target and qty > 1e-9 and symbols[j] not in wash_sale_proxy_symbols]
                target_lots = [j for j, (sym, sub, qty) in enumerate(zip(symbols, substitution_col, lot_quantities))
                              if sym == sub_target and not sub and qty > 1e-9]
                all_idx = sub_lots + target_lots
                substitution_current_values[sub_target] = float(np.sum(lot_quantities[all_idx] * current_prices[all_idx])) if all_idx else 0.0
            
            logger.info(f"[Constraint 3] Substitution protection active")
            
            TOLERANCE = 0.995  # Protect if < 99.5% of target
            sub_targets_with_substitutes = {
                sub for sym, sub in zip(symbols, substitution_col)
                if sub and sym not in wash_sale_proxy_symbols
            }

            # Per-symbol own market value (excluding substitutes), precomputed
            # once so the target-protection branch below is O(n) instead of
            # rescanning all symbols for every lot (previously O(n^2)).
            symbol_own_value = {}
            for j, sym_j in enumerate(symbols):
                symbol_own_value[sym_j] = (
                    symbol_own_value.get(sym_j, 0.0)
                    + float(lot_quantities[j] * current_prices[j])
                )

            # Collect sell-protection lots and append as single vector constraints.
            sub_sell_block_idx = []
            for i, (sym, sub, qty) in enumerate(zip(symbols, substitution_col, lot_quantities)):
                if sym == "CASH" or qty < 1e-9:
                    continue
                if sym in wash_sale_proxy_symbols:
                    continue
                
                if sub and sub != sym:
                    # SUBSTITUTE security (maps to a DIFFERENT symbol):
                    # freeze sells if the combined group is underweight, otherwise
                    # allow sells so the substitute can be unwound first.
                    target_value = target_weight_map.get(sub, 0.0) * budget_value
                    current_value = substitution_current_values.get(sub, 0.0)
                    if current_value < target_value * TOLERANCE:
                        sub_sell_block_idx.append(i)
                        logger.debug(f"   {sym} (→{sub}): PROTECTED (combined ${current_value:,.0f} < ${target_value * TOLERANCE:,.0f})")
                    else:
                        logger.debug(f"   {sym} (→{sub}): CAN SELL (combined ${current_value:,.0f} >= ${target_value * TOLERANCE:,.0f})")
                
                elif sym in sub_targets_with_substitutes:
                    # TARGET security with substitutes:
                    # - protect if the combined group is underweight
                    # - in overweight groups, protect target sells unless the target
                    #   security itself is above its own model target
                    target_value = target_weight_map.get(sym, 0.0) * budget_value
                    current_value = substitution_current_values.get(sym, 0.0)
                    own_value = symbol_own_value.get(sym, 0.0)
                    if current_value < target_value * TOLERANCE:
                        sub_sell_block_idx.append(i)
                        logger.debug(f"   {sym} (TARGET): PROTECTED (combined ${current_value:,.0f} < ${target_value * TOLERANCE:,.0f})")
                    elif own_value <= target_value + (budget_value * 0.001):
                        sub_sell_block_idx.append(i)
                        logger.debug(f"   {sym} (TARGET): KEEPING TARGET (own ${own_value:,.0f} <= target ${target_value:,.0f}; sell substitutes first)")
                    else:
                        logger.debug(f"   {sym} (TARGET): CAN SELL (combined ${current_value:,.0f} >= ${target_value * TOLERANCE:,.0f})")

            if sub_sell_block_idx:
                hard_constraints += [sold[np.array(sub_sell_block_idx, dtype=int)] == 0]
                lots_sell_blocked.update(sub_sell_block_idx)

            # Block buying MORE substitutes (buy the target instead)
            sub_buy_block_idx = [
                i for i, (sym, sub, qty) in enumerate(zip(symbols, substitution_col, lot_quantities))
                if sub and qty < 1e-9 and sym not in wash_sale_proxy_symbols
            ]
            if sub_buy_block_idx:
                hard_constraints += [bought[np.array(sub_buy_block_idx, dtype=int)] == 0]
                lots_buy_blocked.update(sub_buy_block_idx)
        
        
        # NOTE: Legacy category underweight protection (formerly "Constraint 4",
        # for legacy mode without substitutions) has been merged into Constraint 5.
        # Constraint 5's legacy UNDERWEIGHT branch already freezes all existing
        # sells in underweight categories for both substitution and
        # non-substitution legacy runs, so a separate pass is redundant.
        
        
        # ────────────────────────────────────────────────────────────────────────────
        # HELPER: Build mappings (used by Constraint 5 and objective function)
        # ────────────────────────────────────────────────────────────────────────────
        from collections import defaultdict
        
        # Symbol → list of lot indices
        symbol_to_indices = defaultdict(list)
        for i, s in enumerate(symbols):
            symbol_to_indices[s].append(i)
        
        # Category → list of lot indices
        category_of = {s: (c if c is not None else DEFAULT_CAT) for s, c in zip(symbols, categories)}
        cat_indices = defaultdict(list)
        for i, s in enumerate(symbols):
            cat_indices[category_of[s]].append(i)
        
        
        # ────────────────────────────────────────────────────────────────────────────
        # LEGACY SECURITY TARGET MAP
        # ────────────────────────────────────────────────────────────────────────────
        # In legacy mode, we still optimize primarily at the category level, but
        # we want underweight categories to keep buying target securities even
        # when legacy names are sell-protected.
        #
        # Effective per-security targets:
        # - Target securities always keep their model target.
        # - Non-target legacy securities in UNDERWEIGHT categories target their
        #   current frozen weight (they are intentionally being held in place).
        # - Non-target legacy securities in AT-TARGET / OVERWEIGHT categories
        #   target 0 so the optimizer can sell them down when allowed.
        # ────────────────────────────────────────────────────────────────────────────
        
        legacy_security_target_map = None
        if legacy_mode:
            legacy_security_target_map = dict(target_weight_map)  # start from model targets
            
            for cat in set(category_of.values()):
                if cat == "CASH" or cat is None:
                    continue
                
                cat_target_wt = category_target_map.get(cat, 0.0)
                if cat_target_wt < 1e-9:
                    continue
                
                # Classify securities in this category
                cat_syms = [
                    s for s in symbol_to_indices
                    if category_of.get(s) == cat and s != "CASH" and s not in excluded_set
                ]
                target_in_cat = [s for s in cat_syms if s in target_symbols_set]
                legacy_in_cat = [s for s in cat_syms if s not in target_symbols_set]
                
                cat_current_val = category_current_values.get(cat, 0.0)
                underweight_threshold = cat_target_wt * budget_value * 0.995
                is_underweight_cat = cat_current_val < underweight_threshold

                for s in target_in_cat:
                    legacy_security_target_map[s] = target_weight_map.get(s, 0.0)

                for s in legacy_in_cat:
                    idxs = np.array(symbol_to_indices[s], dtype=int)
                    legacy_val = float(np.sum(lot_quantities[idxs] * current_prices[idxs]))
                    if is_underweight_cat:
                        legacy_security_target_map[s] = legacy_val / budget_value if budget_value > 0 else 0.0
                    else:
                        legacy_security_target_map[s] = 0.0
            
            logger.info("[Legacy] Security targets adjusted for legacy holdings:")
            for s in sorted(legacy_security_target_map):
                orig = target_weight_map.get(s, 0.0)
                adj = legacy_security_target_map[s]
                if abs(adj - orig) > 1e-6 and s not in excluded_set and s != "CASH":
                    logger.info(f"   {s}: model {orig*100:.2f}% → legacy {adj*100:.2f}%")
        
        
        # ────────────────────────────────────────────────────────────────────────────
        # CONSTRAINT 5: DIRECTION CONSTRAINTS (ROUND-TRIP PREVENTION)
        # ────────────────────────────────────────────────────────────────────────────
        # LEGACY MODE: Category-level direction (applies with or without substitutions;
        #   also subsumes the former Constraint 4 underweight sell protection)
        #   - If category underweight: Buy target securities, freeze selling existing securities
        #   - If category overweight: Prefer selling non-target securities; only sell
        #     target securities when they are themselves above target
        #
        # STANDARD MODE: Security-level direction
        #   - If security underweight: Block sells, allow buys
        #   - If security overweight: Block buys, allow sells
        # ────────────────────────────────────────────────────────────────────────────
        
        logger.info(f"[Constraint 5] Direction constraints ({'LEGACY: category-level' if legacy_mode else 'STANDARD: security-level'})")
        round_trip_constraints = []
        
        if legacy_mode:
            # ══════════════════════════════════════════════════════════════════════
            # LEGACY MODE: Category-Level Direction Constraints
            # ══════════════════════════════════════════════════════════════════════
            # For each category, compare current vs target value and block the
            # opposite direction for its securities:
            #   UNDERWEIGHT → freeze sells, allow only target buys
            #   OVERWEIGHT  → block all buys, protect target names at/below target
            #   AT TARGET   → freeze category (block all buys, protect target sells)
            # Cash is handled exclusively by Constraint 7.
            # ══════════════════════════════════════════════════════════════════════

            # Per-symbol current market value (for overweight target-sell
            # protection), precomputed once to avoid an O(n^2) rescan per lot.
            symbol_current_value = defaultdict(float)
            for j, sym_j in enumerate(symbols):
                symbol_current_value[sym_j] += float(lot_quantities[j] * current_prices[j])

            def _block_buys(idxs):
                if idxs:
                    round_trip_constraints.append(bought[np.array(idxs, dtype=int)] == 0)
                    lots_buy_blocked.update(idxs)

            def _block_sells(idxs):
                if idxs:
                    round_trip_constraints.append(cp.sum(sold[np.array(idxs, dtype=int)]) == 0)
                    lots_sell_blocked.update(idxs)

            threshold = budget_value * 0.005  # 0.5% category-level band
            tgt_tol = budget_value * 0.001

            for cat, cat_lot_indices in cat_indices.items():
                if cat == "CASH":
                    continue
                # Cash-only categories (label may be "Cash", not "CASH") are
                # governed exclusively by Constraint 7; never block the cash lot.
                if cat_lot_indices and all(symbols[i] == "CASH" for i in cat_lot_indices):
                    continue

                cat_current_value = sum(
                    float(lot_quantities[i] * current_prices[i])
                    for i in cat_lot_indices if lot_quantities[i] > 1e-9
                )
                cat_target_value = category_target_map.get(cat, 0.0) * budget_value
                net_change = cat_target_value - cat_current_value

                empty_in_cat = [i for i in cat_lot_indices if lot_quantities[i] < 1e-9]
                existing_in_cat = [
                    i for i in cat_lot_indices
                    if lot_quantities[i] >= 1e-9 and i not in forced_liquidation_lot_indices
                ]

                if net_change > threshold:
                    # UNDERWEIGHT: keep everything; only buy target names to fill the gap.
                    _block_sells(existing_in_cat)
                    _block_buys([el for el in empty_in_cat if symbols[el] not in target_symbols_set])
                    logger.info(f"   {cat}: UNDERWEIGHT (need +${net_change:,.0f}) → protecting ALL sells, allowing target buys")

                elif net_change < -threshold:
                    # OVERWEIGHT: sell down (non-target first); block all buys and
                    # protect target names already at/below their own target.
                    _block_buys(empty_in_cat + existing_in_cat)
                    _block_sells([
                        el for el in existing_in_cat
                        if symbols[el] in target_symbols_set
                        and symbol_current_value[symbols[el]]
                        <= target_weight_map.get(symbols[el], 0.0) * budget_value + tgt_tol
                    ])
                    logger.info(f"   {cat}: OVERWEIGHT (need ${net_change:,.0f}) → blocking ALL buys ({len(empty_in_cat) + len(existing_in_cat)} lots)")

                else:
                    # AT TARGET: freeze the category so legacy → target swaps (which
                    # leave the weight unchanged but realize tax) can't happen. Block
                    # all buys and protect target sells; non-target sells stay
                    # available only for the minimal cash raise (bounded by C7).
                    _block_buys(empty_in_cat + existing_in_cat)
                    _block_sells([el for el in existing_in_cat if symbols[el] in target_symbols_set])
                    logger.info(f"   {cat}: AT TARGET (${cat_current_value:,.0f} ≈ ${cat_target_value:,.0f}) → freezing category (block all buys, protect target sells)")

        else:
            # ══════════════════════════════════════════════════════════════════════
            # STANDARD MODE: Direction constraints handled by Constraint 10
            # ══════════════════════════════════════════════════════════════════════
            # Constraint 10 (Anti-round-trip) handles all direction locking for
            # standard mode using combined values with substitutes. No additional
            # constraints needed here to avoid conflicts.
            # ══════════════════════════════════════════════════════════════════════
            logger.info("   Standard mode: Direction constraints deferred to Constraint 10")
        
        hard_constraints += round_trip_constraints
        logger.info(f"   Added {len(round_trip_constraints)} directional constraints")
        
        
        # ────────────────────────────────────────────────────────────────────────────
        # CONSTRAINT 5b: SECURITY-LEVEL BOUNDING (Both Modes)
        # ────────────────────────────────────────────────────────────────────────────
        # Bound each security's optimized value between its current value and its
        # target value so it can only move TOWARD the target, never past it.
        # This prevents overshooting in both legacy mode (where category-level
        # alignment can push individual securities past their target) and standard
        # mode (where integer share rounding or solver tolerance can cause small
        # overshoots).
        #
        #   current < target  →  current ≤ optimized ≤ target   (buy toward target)
        #   current > target  →  target  ≤ optimized ≤ current  (sell toward target)
        #   current ≈ target  →  no constraint (already at target)
        # ────────────────────────────────────────────────────────────────────────────
        
        mode_label = "Legacy" if legacy_mode else "Standard"
        logger.info(f"[Constraint 5b] {mode_label} mode: Security-level bounding (current ↔ target)")
        bounded_count = 0
        
        # Build map of frozen substitute values per target symbol.
        # If VTI has substitute SPTM frozen at $19.5K, VTI's effective target
        # must account for SPTM's value (so VTI's own target = group_target - frozen_sub_value).
        frozen_sub_value_per_target = defaultdict(float)
        if has_substitutions:
            sub_col = self.portfolio.get_column("Substitution").to_list()
            for sym2, lot_idxs2 in symbol_to_indices.items():
                if sym2 in excluded_set and lot_idxs2:
                    sub_target = sub_col[lot_idxs2[0]] if sub_col[lot_idxs2[0]] else None
                    if sub_target and sub_target != sym2:
                        sub_idxs2 = np.array(lot_idxs2, dtype=int)
                        frozen_val = float(np.sum(lot_quantities[sub_idxs2] * current_prices[sub_idxs2]))
                        frozen_sub_value_per_target[sub_target] += frozen_val
                        logger.debug(f"   {sub_target}: Frozen substitute {sym2} = ${frozen_val:,.0f}")
        
        for sym, lot_indices in symbol_to_indices.items():
            if sym == "CASH" or sym in excluded_set:
                continue
            
            idxs = np.array(lot_indices, dtype=int)
            sym_current_value = float(np.sum(lot_quantities[idxs] * current_prices[idxs]))
            
            # In legacy mode, use legacy_security_target_map for PURE LEGACY targets
            # (securities without substitutes).  For targets WITH substitutes,
            # always use model targets since the combined substitution group
            # is compared against the full model target.
            # In standard mode, use model targets.
            sym_has_subs = has_substitutions and sym in substitution_current_values
            if sym_has_subs:
                # Target with substitutes: use model target (combined group target)
                sym_target_value = target_weight_map.get(sym, 0.0) * budget_value
            elif legacy_security_target_map:
                # Pure legacy target: use legacy-adjusted target
                sym_target_value = legacy_security_target_map.get(sym, 0.0) * budget_value
            else:
                sym_target_value = target_weight_map.get(sym, 0.0) * budget_value
            
            # Adjust target for frozen substitute value.
            # If SPTM ($19.5K) is frozen and substitutes for VTI (target $20.55K),
            # VTI's effective target becomes max(0, $20.55K - $19.5K) = $1.05K.
            if sym in frozen_sub_value_per_target:
                frozen_val = frozen_sub_value_per_target[sym]
                adjusted_target = max(0.0, sym_target_value - frozen_val)
                logger.debug(f"   {sym}: Target ${sym_target_value:,.0f} adjusted to ${adjusted_target:,.0f} (frozen subs: ${frozen_val:,.0f})")
                sym_target_value = adjusted_target
            
            lower = min(sym_current_value, sym_target_value)
            upper = max(sym_current_value, sym_target_value)
            
            # Skip if bounds are essentially the same (already at target)
            if abs(upper - lower) < 1.0:
                continue
            
            sym_optimized_value = cp.sum(cp.multiply(current_prices[idxs], q[idxs]))
            hard_constraints += [sym_optimized_value >= lower]
            hard_constraints += [sym_optimized_value <= upper]
            bounded_count += 1
        
        logger.info(f"   Bounded {bounded_count} securities between current and target values")
        
        
        # ────────────────────────────────────────────────────────────────────────────
        # CONSTRAINT 5c: TARGET MARKET VALUE PROXIMITY
        # ────────────────────────────────────────────────────────────────────────────
        # Force positive-target positions/groups to land reasonably close to their
        # target market values. Use slack so hard blockers (tax, exclusions,
        # legacy freezes, etc.) degrade gracefully instead of making the solve
        # infeasible.
        # ────────────────────────────────────────────────────────────────────────────
        target_proximity_count = 0
        target_proximity_band_pct = 0.05  # 5% band around positive target values
        target_proximity_min_band = 1000.0  # at least $1k tolerance for small targets
        zero_target_liquidation_band = 1000.0  # unrestricted runs: zero-target names must get near zero
        proximity_requires_unrestricted = constraint_type == 'none'
        substitution_adjusted_targets = {}
        hold_symbols = set(trade_restrictions.get("Hold", []))
        buy_only_symbols = set(trade_restrictions.get("Buy", []))
        sell_only_symbols = set(trade_restrictions.get("Sell", []))

        def _is_buy_blocked(sym: str) -> bool:
            if wash_sale and sym in wash_sale_symbols:
                return True
            if sym in excluded_set:
                return True
            if sym in hold_symbols or sym in sell_only_symbols:
                return True
            return False

        def _is_sell_blocked(sym: str) -> bool:
            if sym in excluded_set and sym not in wash_sale_symbols:
                return True
            if sym in hold_symbols or sym in buy_only_symbols:
                return True
            return False

        blocked_zero_target_symbols = []
        blocked_positive_target_symbols = []
        blocked_substitution_groups = []
        if has_substitutions:
            logger.info("[Constraint 5c] Hard target market value proximity on substitution groups")
            substitution_targets_for_proximity = {
                sub_target: target_weight_map.get(sub_target, 0.0) * budget_value
                for sub_target in {
                    sub for sym, sub in zip(symbols, substitution_col)
                    if sub and sym not in wash_sale_proxy_symbols
                }
            }

            for sub_target, tgt in substitution_targets_for_proximity.items():
                if sub_target == "CASH":
                    continue

                sub_all_idx = [
                    j for j, (sym, sub) in enumerate(zip(symbols, substitution_col))
                    if (
                        (sub == sub_target and sym not in wash_sale_proxy_symbols)
                        or (sym == sub_target and not sub)
                    )
                ]
                if not sub_all_idx:
                    continue

                group_value = cp.sum(cp.multiply(current_prices[sub_all_idx], q[sub_all_idx]))
                current_group_value = float(np.sum(lot_quantities[sub_all_idx] * current_prices[sub_all_idx]))
                move_requires_buys = current_group_value < tgt - 1.0
                move_requires_sells = current_group_value > tgt + 1.0

                group_symbols = {symbols[j] for j in sub_all_idx if symbols[j] != "CASH"}
                group_has_wash_sale_proxy_buy = any(
                    symbols[j] in wash_sale_proxy_symbols
                    and substitution_col[j] == sub_target
                    for j in sub_all_idx
                )
                group_buy_blocked = (
                    move_requires_buys
                    and sub_target != "CASH"
                    and _is_buy_blocked(sub_target)
                    and not group_has_wash_sale_proxy_buy
                )
                group_sell_blocked = (
                    move_requires_sells
                    and all(_is_sell_blocked(sym) for sym in group_symbols)
                )

                if group_buy_blocked or group_sell_blocked:
                    blocked_substitution_groups.append({
                        "sub_target": sub_target,
                        "current": current_group_value,
                        "target": float(tgt),
                        "buy_blocked": bool(group_buy_blocked),
                        "sell_blocked": bool(group_sell_blocked),
                        "symbols": sorted(group_symbols),
                    })
                    logger.debug(
                        "[WASH_SALE_DEBUG] proximity_group_skipped "
                        f"sub_target={sub_target!r} current={current_group_value:.2f} "
                        f"target={float(tgt):.2f} move_requires_buys={move_requires_buys} "
                        f"move_requires_sells={move_requires_sells} "
                        f"group_has_wash_sale_proxy_buy={group_has_wash_sale_proxy_buy} "
                        f"group_buy_blocked={group_buy_blocked} group_sell_blocked={group_sell_blocked} "
                        f"symbols={sorted(group_symbols)}"
                    )
                    logger.info(
                        f"   {sub_target}: skipping proximity bound "
                        f"(current=${current_group_value:,.0f}, target=${tgt:,.0f}, "
                        f"buy_blocked={group_buy_blocked}, sell_blocked={group_sell_blocked})"
                    )
                    continue

                if tgt <= 1.0:
                    if not proximity_requires_unrestricted:
                        continue
                    hard_constraints += [group_value <= zero_target_liquidation_band]
                else:
                    if not proximity_requires_unrestricted:
                        logger.info(
                            f"   {sub_target}: skipping hard positive-target proximity "
                            f"(constraint_type={constraint_type})"
                        )
                        continue
                    band = max(target_proximity_min_band, target_proximity_band_pct * float(tgt))
                    hard_constraints += [group_value >= float(tgt) - band]
                    hard_constraints += [group_value <= float(tgt) + band]
                target_proximity_count += 1
        elif not legacy_mode:
            logger.info("[Constraint 5c] Hard target market value proximity on target securities")
            for sym, idxs_list in symbol_to_indices.items():
                if sym == "CASH":
                    continue

                idxs = np.array(idxs_list, dtype=int)
                if not idxs.size:
                    continue

                tgt = float(target_weight_map.get(sym, 0.0)) * budget_value
                current_sym_value = float(np.sum(lot_quantities[idxs] * current_prices[idxs]))
                move_requires_buys = current_sym_value < tgt - 1.0
                move_requires_sells = current_sym_value > tgt + 1.0

                if move_requires_buys and _is_buy_blocked(sym):
                    blocked_positive_target_symbols.append({
                        "symbol": sym,
                        "current": current_sym_value,
                        "target": float(tgt),
                        "blocked_side": "buy",
                    })
                    logger.debug(
                        "[WASH_SALE_DEBUG] proximity_symbol_skipped "
                        f"symbol={sym!r} current={current_sym_value:.2f} target={float(tgt):.2f} "
                        f"blocked_side='buy' excluded={sym in excluded_set} "
                        f"wash_sale_symbol={sym in wash_sale_symbols}"
                    )
                    logger.info(
                        f"   {sym}: skipping proximity bound "
                        f"(current=${current_sym_value:,.0f}, target=${tgt:,.0f}, buys blocked)"
                    )
                    continue
                if move_requires_sells and _is_sell_blocked(sym):
                    if tgt <= 1.0:
                        blocked_zero_target_symbols.append({
                            "symbol": sym,
                            "current": current_sym_value,
                            "target": float(tgt),
                            "blocked_side": "sell",
                        })
                    else:
                        blocked_positive_target_symbols.append({
                            "symbol": sym,
                            "current": current_sym_value,
                            "target": float(tgt),
                            "blocked_side": "sell",
                        })
                    logger.debug(
                        "[WASH_SALE_DEBUG] proximity_symbol_skipped "
                        f"symbol={sym!r} current={current_sym_value:.2f} target={float(tgt):.2f} "
                        f"blocked_side='sell' excluded={sym in excluded_set} "
                        f"wash_sale_symbol={sym in wash_sale_symbols}"
                    )
                    logger.info(
                        f"   {sym}: skipping proximity bound "
                        f"(current=${current_sym_value:,.0f}, target=${tgt:,.0f}, sells blocked)"
                    )
                    continue

                sym_value = cp.sum(cp.multiply(current_prices[idxs], q[idxs]))
                if tgt <= 1.0:
                    if not proximity_requires_unrestricted:
                        continue
                    hard_constraints += [sym_value <= zero_target_liquidation_band]
                else:
                    if not proximity_requires_unrestricted:
                        logger.info(
                            f"   {sym}: skipping hard positive-target proximity "
                            f"(constraint_type={constraint_type})"
                        )
                        continue
                    band = max(target_proximity_min_band, target_proximity_band_pct * tgt)
                    hard_constraints += [sym_value >= tgt - band]
                    hard_constraints += [sym_value <= tgt + band]
                target_proximity_count += 1
        else:
            logger.info("[Constraint 5c] Skipped in legacy mode (category-first legacy rules take precedence)")

        target_proximity_penalty = 0.0
        logger.info(f"   Added hard proximity bounds for {target_proximity_count} target positions/groups")

        # ────────────────────────────────────────────────────────────────────────────
        # CONSTRAINT 5d: REBALANCE-CATEGORY MODEL ASSIGNMENT CORRIDOR
        # ────────────────────────────────────────────────────────────────────────────
        # The Salesforce/model-assignment routing check evaluates Equity and Fixed
        # Income on managed holdings only, using explicit Rebalance Category values.
        # Mirror that denominator here so the optimizer does not pass symbol-level
        # constraints while still landing outside the post-optimization model check.
        # ────────────────────────────────────────────────────────────────────────────
        target_rebalance_weights = self._target_rebalance_category_weights()
        rebalance_indices = {"equity": [], "fixed income": []}
        skipped_rebalance_symbols = set()
        if target_rebalance_weights:
            rebalance_category_values = (
                self.portfolio.get_column("Rebalance Category").to_list()
                if "Rebalance Category" in self.portfolio.columns
                else [""] * n
            )
            unmanaged_values = (
                self.portfolio.get_column("Unmanaged").to_list()
                if "Unmanaged" in self.portfolio.columns
                else [""] * n
            )

            for i, (sym, rebalance_category, unmanaged_flag) in enumerate(
                zip(symbols, rebalance_category_values, unmanaged_values)
            ):
                normalized_symbol = str(sym or "").strip().upper()
                if not normalized_symbol or normalized_symbol == "CASH":
                    continue
                if normalized_symbol in excluded_set:
                    continue
                if str(unmanaged_flag or "").strip().lower() == "yes":
                    continue

                normalized_rebalance_category = _normalize_rebalance_category_for_tolerance(rebalance_category)
                if normalized_rebalance_category:
                    rebalance_indices[normalized_rebalance_category].append(i)
                else:
                    skipped_rebalance_symbols.add(normalized_symbol)

            managed_rebalance_indices = rebalance_indices["equity"] + rebalance_indices["fixed income"]
            if constraint_type != 'none':
                logger.info(
                    "[Constraint 5d] Skipped hard Rebalance Category corridor "
                    f"because {constraint_type} makes asset allocation a soft objective"
                )
            elif managed_rebalance_indices:
                tolerance = 0.05
                optimized_values = cp.multiply(current_prices, q)
                managed_rebalance_value = cp.sum(optimized_values[np.array(managed_rebalance_indices, dtype=int)])
                added_rebalance_corridors = 0

                for bucket, target_weight in target_rebalance_weights.items():
                    bucket_indices = rebalance_indices.get(bucket) or []
                    if bucket_indices:
                        bucket_value = cp.sum(optimized_values[np.array(bucket_indices, dtype=int)])
                    else:
                        bucket_value = cp.Constant(0.0)

                    lower_weight = max(0.0, float(target_weight) - tolerance)
                    upper_weight = min(1.0, float(target_weight) + tolerance)
                    hard_constraints += [
                        bucket_value >= lower_weight * managed_rebalance_value,
                        bucket_value <= upper_weight * managed_rebalance_value,
                    ]
                    added_rebalance_corridors += 2

                logger.info(
                    "[Constraint 5d] Rebalance Category model corridor: "
                    f"target={target_rebalance_weights}, tolerance={tolerance:.1%}, "
                    f"equity_lots={len(rebalance_indices['equity'])}, "
                    f"fixed_income_lots={len(rebalance_indices['fixed income'])}, "
                    f"skipped_symbols={sorted(skipped_rebalance_symbols)}"
                )
                logger.debug(
                    "[MODEL_ASSIGNMENT_DEBUG] optimizer_rebalance_category_corridor "
                    f"target={target_rebalance_weights} tolerance={tolerance:.4f} "
                    f"equity_lots={len(rebalance_indices['equity'])} "
                    f"fixed_income_lots={len(rebalance_indices['fixed income'])} "
                    f"skipped_symbols={sorted(skipped_rebalance_symbols)}"
                )
                logger.info(f"   Added {added_rebalance_corridors} rebalance-category corridor constraints")
            else:
                logger.warning(
                    "[Constraint 5d] Skipped Rebalance Category corridor: no managed Equity/Fixed Income lots"
                )
        else:
            logger.warning(
                "[Constraint 5d] Skipped Rebalance Category corridor: target Rebalance Category weights unavailable"
            )

        # ────────────────────────────────────────────────────────────────────────────
        # CONSTRAINT 6: BUDGET CONSERVATION
        # ────────────────────────────────────────────────────────────────────────────
        # Portfolio value must stay constant (no cash in/out)
        # ────────────────────────────────────────────────────────────────────────────
        
        final_value = current_prices @ q
        budget_constraint = final_value == budget_value
        hard_constraints += [budget_constraint]
        minimum_budget_constraints += [budget_constraint]
        logger.info(f"[Constraint 6] Budget: Portfolio value = ${budget_value:,.2f}")
        
        
        # ────────────────────────────────────────────────────────────────────────────
        # CONSTRAINT 7: CASH MANAGEMENT
        # ────────────────────────────────────────────────────────────────────────────
        # Keep cash monotonic between current cash and target cash floor:
        # current <= optimized <= target or current >= optimized >= target
        # ────────────────────────────────────────────────────────────────────────────
        
        cash_idxs = np.array(symbol_to_indices.get("CASH", []), dtype=int)
        start_cash = float(np.sum(lot_quantities[cash_idxs])) if cash_idxs.size else 0.0
        cash_floor = float(getattr(self, "_cash_floor_dollars", 0.0))

        if cash_idxs.size:
            cash_total = cp.sum(q[cash_idxs])

            # Cash floor: minimum required cash (carve-out + reserve/raise).
            cash_floor_constraint = cash_total >= cash_floor
            hard_constraints += [cash_floor_constraint]
            minimum_budget_constraints += [cash_floor_constraint]

            # Cash ceiling: prevent the optimizer from hoarding cash to avoid
            # tax.  Buffer is 0.5% of managed (non-cash) value so the solver
            # has numerical breathing room without meaningfully distorting the
            # target allocation.
            managed_value = max(budget_value - cash_floor, 0.0)
            cash_buffer = 0.005 * managed_value  # 0.5% of managed value
            cash_ceiling = max(start_cash, cash_floor) + cash_buffer
            cash_ceiling_constraint = cash_total <= cash_ceiling
            hard_constraints += [cash_ceiling_constraint]
            minimum_budget_constraints += [cash_ceiling_constraint]
            self._cash_ceiling_dollars = cash_ceiling

            logger.info(
                f"[Constraint 7] Cash range enforced: "
                f"${cash_floor:,.2f} <= CASH <= ${cash_ceiling:,.2f} "
                f"(buffer=${cash_buffer:,.2f}, 0.5% of managed=${managed_value:,.2f})"
            )

            _diagnostic_print(
                "[Optimizer Debug] cash_target "
                f"start_cash={start_cash:,.2f} "
                f"cash_floor={cash_floor:,.2f} "
                f"cash_ceiling={cash_ceiling:,.2f} "
                f"cash_buffer={cash_buffer:,.2f}"
            )
        
        
        # ────────────────────────────────────────────────────────────────────────────
        # CONSTRAINT 8: TAX LIMITS
        # ────────────────────────────────────────────────────────────────────────────
        # Limit realized gains and total tax liability
        # ────────────────────────────────────────────────────────────────────────────
        
        # Cost basis per share (avoid div by zero for empty lots)
        unit_cost = np.divide(lot_costs, np.where(lot_quantities != 0, lot_quantities, 1.0))
        gains_per_share = current_prices - unit_cost
        gains_per_share[is_cash] = 0.0
        
        # Realized gains and tax liability
        realized_gains = gains_per_share @ sold
        rate_vec = np.where(is_long_term, long_term_rate, short_term_rate)
        tax_liability = cp.sum(cp.multiply(rate_vec, cp.multiply(gains_per_share, sold)))
        realized_gains_budget_constraint = None
        tax_budget_constraint = None

        if realized_gains_constraint is not None:
            realized_gains_budget_constraint = realized_gains <= realized_gains_constraint
            hard_constraints += [realized_gains_budget_constraint]
            logger.info(f"[Constraint 8a] Realized gains ≤ ${realized_gains_constraint:,.2f}")
            _diagnostic_print(f"[Optimizer Debug] realized_gains_limit={float(realized_gains_constraint):,.2f}")

        enforce_tax_budget = constraint_type == "tax_budget"
        if enforce_tax_budget:
            tax_budget_constraint = tax_liability <= max_tax_bill
            hard_constraints += [tax_budget_constraint]
            logger.info(f"[Constraint 8b] Tax liability ≤ ${max_tax_bill:,.2f}")
            _diagnostic_print(f"[Optimizer Debug] tax_budget_limit={float(max_tax_bill):,.2f}")
        else:
            logger.info(f"[Constraint 8b] Skipped hard tax budget bound (constraint_type={constraint_type})")
            _diagnostic_print(f"[Optimizer Debug] tax_budget_limit=SKIPPED constraint_type={constraint_type}")
        
        logger.info(f"   ST rate: {short_term_rate*100:.1f}%, LT rate: {long_term_rate*100:.1f}%")
        logger.info(f"Long-term rate: {long_term_rate * 100:.1f}%")
        
        
        # ============================================================================
        # CONSTRAINT 9: SUBSTITUTION GROUP MONOTONIC BOUNDS (if applicable)
        # ============================================================================
        
        if has_substitutions:
            logger.info("[Constraint 9] Substitution group monotonic bounds (current ↔ target)")
            
            # Calculate current and target values for each substitution target
            sub_target_val = {}
            sub_curr_val = {}
            
            normal_sub_targets = {
                sub for sym, sub in zip(symbols, substitution_col)
                if sub and sym not in wash_sale_proxy_symbols
            }
            for sub_target in normal_sub_targets:
                sub_target_val[sub_target] = target_weight_map.get(sub_target, 0.0) * budget_value
                
                # Current value: sum of substituted lots + real holdings
                all_idx = [
                    j for j, (sym, sub, qty) in enumerate(zip(symbols, substitution_col, lot_quantities))
                    if (
                        (sub == sub_target and sym not in wash_sale_proxy_symbols)
                        or (sym == sub_target and not sub)
                    )
                    and qty > 1e-9
                ]
                sub_curr_val[sub_target] = float(np.sum(lot_quantities[all_idx] * current_prices[all_idx])) if all_idx else 0.0
            
            for sub_target, tgt in sub_target_val.items():
                curr = sub_curr_val[sub_target]
                
                # Get all lots contributing to this substitution target
                sub_all_idx = [
                    j for j, (sym, sub) in enumerate(zip(symbols, substitution_col))
                    if (
                        (sub == sub_target and sym not in wash_sale_proxy_symbols)
                        or (sym == sub_target and not sub)
                    )
                ]
                
                if sub_all_idx:
                    total_value = cp.sum(cp.multiply(current_prices[sub_all_idx], q[sub_all_idx]))
                    
                    # Identify which lots are substitutes vs target
                    sub_lots = [
                        j for j in sub_all_idx
                        if substitution_col[j] == sub_target and symbols[j] not in wash_sale_proxy_symbols
                    ]
                    target_lots = [j for j in sub_all_idx if symbols[j] == sub_target and not substitution_col[j]]
                    sub_value = float(np.sum(lot_quantities[sub_lots] * current_prices[sub_lots])) if sub_lots else 0.0
                    target_value = float(np.sum(lot_quantities[target_lots] * current_prices[target_lots])) if target_lots else 0.0
                    
                    logger.debug(f"   {sub_target}: curr=${curr:,.0f} (target_sym=${target_value:,.0f}, subs=${sub_value:,.0f})")
                    logger.debug(f"      Target=${tgt:,.0f}")

                    lower = min(curr, tgt)
                    upper = max(curr, tgt)
                    if abs(upper - lower) >= 1.0:
                        hard_constraints.append(total_value >= lower)
                        hard_constraints.append(total_value <= upper)
                        logger.debug(f"      BOUNDED → ${lower:,.0f} <= optimized <= ${upper:,.0f}")
                    else:
                        logger.debug(f"      AT TARGET → no additional hard bound")

                    substitution_adjusted_targets[sub_target] = tgt
                    
                    logger.info(f"   {sub_target}: current=${curr:,.0f}, target=${tgt:,.0f}")

        
        # ────────────────────────────────────────────────────────────────────────────
        # CONSTRAINT 10: ANTI-ROUND-TRIP (Per-security direction lock)
        # ────────────────────────────────────────────────────────────────────────────
        # For EVERY security, enforce ONE direction only based on whether the
        # combined value (including substitutes that flow INTO it) is over/under target.
        #
        # For target symbols (e.g., BND): include current value of all substitutes
        # that flow INTO it (e.g., HTRB→BND means BND's "effective current" includes HTRB)
        #
        # For substitute symbols (e.g., HTRB): they should only SELL (target=0)
        # ────────────────────────────────────────────────────────────────────────────
        
        logger.info("[Constraint 10] Anti-round-trip (per-security direction lock)")
        logger.debug(f"   has_substitutions flag: {has_substitutions}")
        anti_roundtrip_count = 0
        
        # Get substitution column if it exists
        substitution_col = None
        if has_substitutions:
            substitution_col = self.portfolio.get_column("Substitution").to_list()
            logger.debug(f"   substitution_col loaded: {len(substitution_col)} entries")
        
        # Build a map of target_symbol → list of substitute symbols that flow into it
        # e.g., {"BND": ["HTRB"], "VO": ["MDY", "SDY"]}
        # NOTE: Self-references (VTI→VTI) are excluded — only true substitutes
        substitutes_into = defaultdict(list)
        if has_substitutions and substitution_col:
            for sym, lot_indices in symbol_to_indices.items():
                if lot_indices:
                    sym_sub = substitution_col[lot_indices[0]]
                    if (
                        sym_sub
                        and sym_sub != sym
                        and sym not in wash_sale_proxy_symbols
                    ):  # Only true substitutes, not self-references
                        substitutes_into[sym_sub].append(sym)
        
        logger.debug(f"   Substitution flows: {dict(substitutes_into)}")
        logger.debug(f"   target_weight_map keys: {list(target_weight_map.keys())}")
        logger.debug(f"   Budget value: ${budget_value:,.0f}")
        
        if legacy_mode:
            logger.info("   Legacy mode: anti-round-trip decisions handled by category/substitution rules")
        else:
            # Track which symbols we've already handled (to avoid double-processing)
            handled_symbols = set()
            
            for sym, lot_indices in symbol_to_indices.items():
                if sym == "CASH" or sym in handled_symbols:
                    continue
                
                idxs = np.array(lot_indices, dtype=int)
                if idxs.size == 0:
                    continue
                
                # Check if this symbol is a SUBSTITUTE (has a substitution target)
                # A symbol that maps to ITSELF (e.g., VTI→VTI) is the TARGET, not a substitute
                sym_sub = None
                if has_substitutions and substitution_col and lot_indices:
                    raw_sub = substitution_col[lot_indices[0]]
                    if raw_sub and raw_sub != sym:  # Only treat as substitute if it maps to a DIFFERENT symbol
                        sym_sub = raw_sub
                
                if sym_sub and sym in wash_sale_proxy_symbols:
                    handled_symbols.add(sym)
                    logger.debug(
                        f"   {sym}: WASH-SALE PROXY (→{sym_sub}) "
                        "skips normal substitution anti-round-trip; proceeds cap controls buys"
                    )
                    continue

                if sym_sub:
                    current_val = float(np.sum(lot_quantities[idxs] * current_prices[idxs]))
                    is_wash_sale_proxy = sym in wash_sale_proxy_symbols
                    if not is_wash_sale_proxy:
                        hard_constraints.append(bought[idxs] == 0)
                        lots_buy_blocked.update(lot_indices)
                    
                    target_idxs = np.array(symbol_to_indices.get(sym_sub, []), dtype=int)
                    target_current = float(np.sum(lot_quantities[target_idxs] * current_prices[target_idxs])) if target_idxs.size > 0 else 0.0
                    combined_for_target = target_current + current_val
                    
                    for other_sub in substitutes_into.get(sym_sub, []):
                        if other_sub != sym:
                            other_idxs = np.array(symbol_to_indices.get(other_sub, []), dtype=int)
                            if other_idxs.size > 0:
                                combined_for_target += float(np.sum(lot_quantities[other_idxs] * current_prices[other_idxs]))
                    
                    target_val = target_weight_map.get(sym_sub, 0.0) * budget_value
                    
                    threshold = budget_value * 0.001
                    if combined_for_target < target_val - threshold:
                        hard_constraints.append(sold[idxs] == 0)
                        lots_sell_blocked.update(lot_indices)
                        anti_roundtrip_count += len(lot_indices)
                        buy_note = "buys allowed as wash-sale proxy" if is_wash_sale_proxy else "block buys"
                        logger.debug(f"   {sym}: SUBSTITUTE (→{sym_sub}) UNDERWEIGHT group ${combined_for_target:,.0f} < ${target_val:,.0f} → block sells, {buy_note}")
                    else:
                        anti_roundtrip_count += len(lot_indices)
                        buy_note = "buys allowed as wash-sale proxy" if is_wash_sale_proxy else "block buys only"
                        logger.debug(f"   {sym}: SUBSTITUTE (→{sym_sub}) ${current_val:,.0f} → {buy_note} (sells allowed)")
                    handled_symbols.add(sym)
                    
                else:
                    current_val = float(np.sum(lot_quantities[idxs] * current_prices[idxs]))
                    combined_val = current_val
                    
                    has_subs_into = len(substitutes_into.get(sym, [])) > 0
                    
                    for sub_sym in substitutes_into.get(sym, []):
                        sub_idxs = np.array(symbol_to_indices.get(sub_sym, []), dtype=int)
                        if sub_idxs.size > 0:
                            sub_val = float(np.sum(lot_quantities[sub_idxs] * current_prices[sub_idxs]))
                            combined_val += sub_val
                            logger.debug(f"   {sym}: Adding {sub_sym} value ${sub_val:,.0f} to combined")
                    
                    target_val = target_weight_map.get(sym, 0.0) * budget_value
                    
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug(f"   {sym} DEBUG: lot_indices={lot_indices}")
                        logger.debug(f"   {sym} DEBUG: current_val=${current_val:,.0f}, combined_val=${combined_val:,.0f}")
                        model_target = target_weight_map.get(sym, 0.0) * budget_value
                        logger.debug(f"   {sym} DEBUG: model_target=${model_target:,.0f}, effective_target=${target_val:,.0f}")
                        logger.debug(f"   {sym} DEBUG: threshold=${budget_value * 0.001:,.0f}")
                    
                    threshold = budget_value * 0.001  # 0.1% threshold
                    subs_label = f" (includes subs: {substitutes_into.get(sym, [])})" if has_subs_into else ""
                    
                    if combined_val > target_val + threshold:
                        hard_constraints.append(bought[idxs] == 0)
                        lots_buy_blocked.update(lot_indices)
                        anti_roundtrip_count += len(lot_indices)
                        handled_symbols.add(sym)
                        logger.debug(f"   {sym}: OVERWEIGHT{subs_label} (combined ${combined_val:,.0f} > ${target_val:,.0f}) → block buys on {len(lot_indices)} lots")
                            
                    elif combined_val < target_val - threshold:
                        hard_constraints.append(sold[idxs] == 0)
                        lots_sell_blocked.update(lot_indices)
                        anti_roundtrip_count += len(lot_indices)
                        handled_symbols.add(sym)
                        logger.debug(f"   {sym}: UNDERWEIGHT{subs_label} (combined ${combined_val:,.0f} < ${target_val:,.0f}) → block sells on {len(lot_indices)} lots")
                            
                    else:
                        hard_constraints.append(sold[idxs] == 0)
                        hard_constraints.append(bought[idxs] == 0)
                        lots_buy_blocked.update(lot_indices)
                        lots_sell_blocked.update(lot_indices)
                        anti_roundtrip_count += 2 * len(lot_indices)
                        handled_symbols.add(sym)
                        logger.debug(f"   {sym}: AT TARGET{subs_label} (combined ${combined_val:,.0f} ≈ ${target_val:,.0f}) → block all on {len(lot_indices)} lots")
        
        logger.info(f"   Added {anti_roundtrip_count} anti-round-trip constraints")

        
        # ────────────────────────────────────────────────────────────────────────────
        # CONSTRAINT 11: ASSET CLASS DIRECTION (Move toward target, not away)
        # ────────────────────────────────────────────────────────────────────────────
        # Ensure that the optimized asset class allocation moves TOWARD the target
        # allocation, not AWAY from it.
        #
        # For each asset class:
        # - If current > target: optimized <= current (should decrease or stay same)
        # - If current < target: optimized >= current (should increase or stay same)
        #
        # This prevents the optimizer from selling bonds to buy stocks when the
        # target wants LESS stocks and MORE bonds.
        # ────────────────────────────────────────────────────────────────────────────
        
        logger.info("[Constraint 11] Asset class direction (move toward target)")
        asset_class_constraints = []
        
        # First, build a symbol -> asset class lookup from all available sources
        symbol_to_asset_class = {}
        
        # Source 1: portfolio_info (authoritative source for asset class)
        if self.portfolio_info is not None and "Asset Class" in self.portfolio_info.columns:
            for row in self.portfolio_info.select(["Symbol", "Asset Class"]).iter_rows():
                sym, ac = row
                if ac:
                    symbol_to_asset_class[sym] = ac
        
        # Source 2: target_allocation (for symbols not in portfolio_info)
        if self.target_allocation is not None and "Asset Class" in self.target_allocation.columns:
            for row in self.target_allocation.select(["Symbol", "Asset Class"]).iter_rows():
                sym, ac = row
                if ac and sym not in symbol_to_asset_class:
                    symbol_to_asset_class[sym] = ac
        
        # Build asset class to lot indices mapping
        # Use portfolio's Asset Class column, but fall back to lookup for None values
        asset_class_indices = defaultdict(list)
        symbols = self.portfolio.get_column("Symbol").to_list()
        
        if "Asset Class" in self.portfolio.columns:
            asset_class_col = self.portfolio.get_column("Asset Class").to_list()
            for i, (sym, ac) in enumerate(zip(symbols, asset_class_col)):
                # Use existing asset class or look up from mapping
                effective_ac = ac if ac else symbol_to_asset_class.get(sym)
                if effective_ac and effective_ac != "Cash":
                    asset_class_indices[effective_ac].append(i)
        else:
            # No Asset Class column, use lookup
            for i, sym in enumerate(symbols):
                ac = symbol_to_asset_class.get(sym)
                if ac and ac != "Cash":
                    asset_class_indices[ac].append(i)
        
        # Calculate current and target asset class weights
        # For target: Sum up target weights for each asset class
        # IMPORTANT: Use adjusted_target_allocation (the original, unmodified
        # target) rather than target_weight_map.  target_weight_map has
        # substitute symbols removed, which can accidentally drop the target
        # symbol when it also appears in the Substitution column (e.g. VTI
        # substitutes to itself → VTI removed from map → Equity target = 0%).
        target_asset_class_weights = defaultdict(float)
        
        logger.debug(f"   Asset class mapping for symbols: {symbol_to_asset_class}")
        
        # Build target asset class weights from the original target allocation
        for row in self.adjusted_target_allocation.iter_rows(named=True):
            sym = row["Symbol"]
            weight = row["Target Weight"]
            if sym == "CASH":
                continue
            ac = symbol_to_asset_class.get(sym)
            if ac and ac != "Cash":
                target_asset_class_weights[ac] += weight
            elif sym != "CASH":
                logger.warning(f"   No asset class for target symbol: {sym}")
        
        logger.info(f"   Target asset class weights: {dict(target_asset_class_weights)}")
        
        # For each asset class, add direction constraint
        asset_class_direction_count = 0
        for ac, lot_indices in asset_class_indices.items():
            if not lot_indices:
                continue
            
            idxs = np.array(lot_indices, dtype=int)
            
            # Current value for this asset class
            current_ac_value = float(np.sum(lot_quantities[idxs] * current_prices[idxs]))
            current_ac_weight = current_ac_value / budget_value if budget_value > 0 else 0
            
            # Target weight for this asset class
            target_ac_weight = target_asset_class_weights.get(ac, 0.0)
            
            # Calculate direction threshold (1% of portfolio to avoid overly tight constraints)
            threshold = 0.01  # 1% threshold
            
            # Optimized value for this asset class = sum of (price * quantity) for all lots
            optimized_ac_value = cp.sum(cp.multiply(current_prices[idxs], q[idxs]))
            
            # One-sided direction constraint: ensure the optimizer moves
            # TOWARD the target, not AWAY from it.
            #
            # - Overweight asset class → must not INCREASE (can decrease or stay)
            # - Underweight asset class → must not DECREASE (can increase or stay)
            #
            # We intentionally use one-sided constraints (not corridors) to
            # avoid over-constraining the solver.  Constraint 5 already handles
            # category-level direction locking; Constraint 11 acts as a
            # coarser asset-class guard.
            slack_pct = 0.02  # 2% slack to avoid infeasibility

            if current_ac_weight > target_ac_weight + threshold:
                # Asset class is OVERWEIGHT: should DECREASE or stay same
                max_value = current_ac_value * (1 + slack_pct)
                asset_class_constraints.append(optimized_ac_value <= max_value)
                asset_class_direction_count += 1
                logger.info(f"   {ac}: OVERWEIGHT ({current_ac_weight*100:.1f}% > {target_ac_weight*100:.1f}%) → must not exceed ${max_value:,.0f}")

            elif current_ac_weight < target_ac_weight - threshold:
                # Asset class is UNDERWEIGHT: should INCREASE or stay same
                min_value = current_ac_value * (1 - slack_pct)
                asset_class_constraints.append(optimized_ac_value >= min_value)
                asset_class_direction_count += 1
                logger.info(f"   {ac}: UNDERWEIGHT ({current_ac_weight*100:.1f}% < {target_ac_weight*100:.1f}%) → must be at least ${min_value:,.0f}")
            else:
                logger.debug(f"   {ac}: AT TARGET ({current_ac_weight*100:.1f}% ≈ {target_ac_weight*100:.1f}%) → no constraint")
        
        hard_constraints += asset_class_constraints
        logger.info(f"   Added {asset_class_direction_count} asset class direction constraints")

        
        # ============================================================================
        # PRE-SOLVE FEASIBILITY ANALYSIS
        # ============================================================================
        logger.info("=== PRE-SOLVE FEASIBILITY ANALYSIS ===")

        if blocked_zero_target_symbols:
            _diagnostic_print("[Optimizer Diagnostic] zero_target_sell_blocked_symbols:")
            for item in sorted(blocked_zero_target_symbols, key=lambda x: (-x["current"], x["symbol"])):
                _diagnostic_print(
                    "  - "
                    f"{item['symbol']}: current=${item['current']:,.2f}, "
                    f"target=${item['target']:,.2f}, blocked_side={item['blocked_side']}"
                )

        if blocked_positive_target_symbols:
            _diagnostic_print("[Optimizer Diagnostic] positive_target_blocked_symbols:")
            for item in sorted(blocked_positive_target_symbols, key=lambda x: (-abs(x["target"] - x["current"]), x["symbol"])):
                _diagnostic_print(
                    "  - "
                    f"{item['symbol']}: current=${item['current']:,.2f}, "
                    f"target=${item['target']:,.2f}, blocked_side={item['blocked_side']}"
                )

        if blocked_substitution_groups:
            _diagnostic_print("[Optimizer Diagnostic] blocked_substitution_groups:")
            for item in sorted(blocked_substitution_groups, key=lambda x: (-abs(x["target"] - x["current"]), x["sub_target"])):
                _diagnostic_print(
                    "  - "
                    f"{item['sub_target']}: current=${item['current']:,.2f}, "
                    f"target=${item['target']:,.2f}, "
                    f"buy_blocked={item['buy_blocked']}, sell_blocked={item['sell_blocked']}, "
                    f"symbols={item['symbols']}"
                )
        
        # Analyze at the TARGET level (combined: target + all substitutes)
        total_sell_needed = 0.0
        total_buy_needed = 0.0
        sell_blocked_value = 0.0
        buy_blocked_value = 0.0
        
        logger.debug("[Feasibility] Analyzing COMBINED position changes (target + substitutes):")
        
        # Process each TARGET symbol (not substitutes)
        processed_targets = set()
        for sym in set(symbols):
            if sym == "CASH":
                continue
            
            idxs = np.array(symbol_to_indices.get(sym, []), dtype=int)
            if idxs.size == 0:
                continue
            
            # Check if this is a substitute (skip - we'll handle it with its target)
            sym_sub = None
            if substitution_col:  # Check if substitution_col exists
                for idx in idxs:
                    if substitution_col[idx]:
                        sym_sub = substitution_col[idx]
                        break
            
            if sym_sub:
                # This is a substitute - skip, will be counted with target
                continue
            
            if sym in processed_targets:
                continue
            processed_targets.add(sym)
            
            # This is a TARGET symbol
            # Calculate COMBINED value: target + all substitutes
            current_val = float(np.sum(lot_quantities[idxs] * current_prices[idxs]))
            combined_val = current_val
            
            substitute_values = {}
            for sub_sym in substitutes_into.get(sym, []):
                sub_idxs = np.array(symbol_to_indices.get(sub_sym, []), dtype=int)
                if sub_idxs.size > 0:
                    sub_val = float(np.sum(lot_quantities[sub_idxs] * current_prices[sub_idxs]))
                    combined_val += sub_val
                    substitute_values[sub_sym] = sub_val
            
            target_val = target_weight_map.get(sym, 0.0) * budget_value
            diff = combined_val - target_val
            
            if diff > 0:
                # COMBINED is OVERWEIGHT - need to reduce
                total_sell_needed += diff
                # Can we sell? Check if any sells are blocked
                # For overweight targets: target itself can sell, substitutes can sell
                # No sells should be blocked for overweight combined positions
                if substitute_values:
                    logger.debug(f"   {sym}: COMBINED ${combined_val:,.0f} (target ${current_val:,.0f} + subs {substitute_values}) > target ${target_val:,.0f} → need to sell ${diff:,.0f}")
                else:
                    logger.debug(f"   {sym}: ${combined_val:,.0f} > target ${target_val:,.0f} → need to sell ${diff:,.0f}")
                    
            elif diff < 0:
                # COMBINED is UNDERWEIGHT - need to increase
                total_buy_needed += abs(diff)
                # Can we buy? Only the TARGET can buy (substitutes always block buys)
                # Check if target buys are blocked (they shouldn't be for underweight)
                if substitute_values:
                    logger.debug(f"   {sym}: COMBINED ${combined_val:,.0f} (target ${current_val:,.0f} + subs {substitute_values}) < target ${target_val:,.0f} → need to buy ${abs(diff):,.0f} of {sym}")
                else:
                    logger.debug(f"   {sym}: ${combined_val:,.0f} < target ${target_val:,.0f} → need to buy ${abs(diff):,.0f}")
        
        # Also track "orphan" substitutes (substitutes whose targets don't exist in portfolio)
        for sym in set(symbols):
            if sym == "CASH":
                continue
            idxs = np.array(symbol_to_indices.get(sym, []), dtype=int)
            if idxs.size == 0:
                continue
            
            sym_sub = None
            if substitution_col:  # Check if substitution_col exists
                for idx in idxs:
                    if substitution_col[idx]:
                        sym_sub = substitution_col[idx]
                        break
            
            if sym_sub and sym_sub not in symbol_to_indices:
                # Orphan substitute - target not in portfolio
                current_val = float(np.sum(lot_quantities[idxs] * current_prices[idxs]))
                target_val = target_weight_map.get(sym_sub, 0.0) * budget_value
                logger.warning(f"   {sym}: ORPHAN SUBSTITUTE (→{sym_sub}) ${current_val:,.0f}, target {sym_sub} not in portfolio! Need target=${target_val:,.0f}")
        
        # NOTE: Substitutes are NO LONGER locked - they can always sell
        # Constraint 9 (Substitution Bounds) protects the combined minimum
        locked_substitute_value = 0.0
        locked_subs = []
        
        # Get current CASH position
        current_cash = float(np.sum(lot_quantities[cash_idxs])) if cash_idxs.size else 0.0
        
        # Adjust for locked substitutes
        adjusted_sell = total_sell_needed - locked_substitute_value
        cash_diff = adjusted_sell - total_buy_needed
        expected_final_cash = current_cash + cash_diff
        
        logger.debug(f"[Feasibility] Summary:")
        logger.debug(f"   Total sell needed (raw):     ${total_sell_needed:,.0f}")
        if locked_subs:
            logger.debug(f"   LOCKED substitutes (can't sell):")
            for sub_sym, sub_val, target in locked_subs:
                logger.debug(f"      - {sub_sym} (→{target}): ${sub_val:,.0f}")
            logger.debug(f"   Total locked:                ${locked_substitute_value:,.0f}")
            logger.debug(f"   Adjusted sell available:     ${adjusted_sell:,.0f}")
        logger.debug(f"   Total buy needed:            ${total_buy_needed:,.0f}")
        logger.debug(f"   Net cash change:             ${cash_diff:,.0f} ({'increase' if cash_diff >= 0 else 'decrease'})")
        logger.debug(f"   Current CASH:                ${current_cash:,.0f}")
        logger.debug(f"   Expected final CASH:         ${expected_final_cash:,.0f}")
        cash_lower = min(current_cash, cash_floor)
        cash_upper = max(current_cash, cash_floor)
        logger.debug(f"   Cash lower bound:            ${cash_lower:,.0f}")
        logger.debug(f"   Cash upper bound:            ${cash_upper:,.0f}")
        _diagnostic_print(
            "[Optimizer Diagnostic] cash_math "
            f"total_sell_needed={total_sell_needed:,.2f} "
            f"total_buy_needed={total_buy_needed:,.2f} "
            f"adjusted_sell={adjusted_sell:,.2f} "
            f"cash_diff={cash_diff:,.2f} "
            f"current_cash={current_cash:,.2f} "
            f"expected_final_cash={expected_final_cash:,.2f} "
            f"cash_lower={cash_lower:,.2f} "
            f"cash_upper={cash_upper:,.2f}"
        )
        
        tolerance = 1.0  # $1 tolerance for floating point comparisons
        if expected_final_cash < cash_lower - tolerance:
            shortfall = cash_lower - expected_final_cash
            logger.warning(f"   INFEASIBILITY: Expected cash ${expected_final_cash:,.0f} < lower bound ${cash_lower:,.0f}!")
            logger.warning(f"      Shortfall: ${shortfall:,.0f}")
            if locked_subs:
                logger.warning(f"      ROOT CAUSE: ${locked_substitute_value:,.0f} in substitutes is LOCKED (can't sell)")
                logger.warning(f"      The optimizer cannot sell locked substitutes to generate cash!")
                logger.warning(f"      SOLUTION: Either:")
                logger.warning(f"        1. Reduce buy targets to free up ${shortfall:,.0f}")
                logger.warning(f"        2. Allow selling locked substitutes (change substitution logic)")
                logger.warning(f"        3. Increase starting cash by ${shortfall:,.0f}")
        elif expected_final_cash > cash_upper + tolerance:
            logger.warning(f"   INFEASIBILITY: Expected cash ${expected_final_cash:,.0f} > upper bound ${cash_upper:,.0f}!")
            logger.warning(f"      Need ${expected_final_cash - cash_upper:,.0f} more buys OR less sells")
        else:
            logger.debug(f"   Cash balance looks feasible")
        
        logger.debug(f"   Max tax bill:                ${max_tax_bill:,.0f}")
        
        # 2. Check tax budget feasibility
        # Estimate tax from selling overweight positions
        total_estimated_tax = 0.0
        for sym in set(symbols):
            if sym == "CASH":
                continue
            idxs = np.array(symbol_to_indices.get(sym, []), dtype=int)
            if idxs.size == 0:
                continue
            
            # Check substitution
            sym_sub = None
            if substitution_col:  # Check if substitution_col exists
                for idx in idxs:
                    if substitution_col[idx]:
                        sym_sub = substitution_col[idx]
                        break
            
            current_val = float(np.sum(lot_quantities[idxs] * current_prices[idxs]))
            if sym_sub:
                target_val = 0  # Substitutes should be liquidated
            else:
                target_val = target_weight_map.get(sym, 0.0) * budget_value
            
            if current_val > target_val:
                # Need to sell - estimate tax
                sell_amount = current_val - target_val
                # Simplified: assume proportional gain realization
                total_cost = float(np.sum(lot_costs[idxs]))
                if current_val > 0:
                    avg_gain_rate = (current_val - total_cost) / current_val
                    if avg_gain_rate > 0:  # Only if there are gains
                        # Assume long-term rate for simplicity
                        estimated_tax = sell_amount * avg_gain_rate * long_term_rate
                        total_estimated_tax += estimated_tax
        
        logger.debug(f"   Est. tax from rebalance: ${total_estimated_tax:,.0f}")
        if enforce_tax_budget and total_estimated_tax > max_tax_bill:
            logger.warning(f"   WARNING: Estimated tax ${total_estimated_tax:,.0f} > max tax bill ${max_tax_bill:,.0f}")
            logger.warning(f"              This may cause INFEASIBILITY!")
        
        logger.info("=== END FEASIBILITY ANALYSIS ===")
        
        # Validation
        logger.info(f"[Constraints] Total: {len(hard_constraints)}")
        assert len(hard_constraints) > 0, "ERROR: No constraints defined!"

        # ============================================================================
        # OBJECTIVE FUNCTION: ALIGNMENT TERMS
        # ============================================================================


        align_terms = []
        relative_target_fit_terms = []
        
        if legacy_mode:
            # LEGACY MODE objective is intentionally ordered for explainability:
            # 1. Hit the category target first.
            # 2. Within that category, prefer target-model securities.
            # 3. When a category is no longer underweight, unwind residual
            #    non-target legacy names.
            logger.info(f"[Objective] Legacy mode: category fit -> target security fit -> legacy unwind")
            
            # Build category target weights
            target_by_cat_w = defaultdict(float)
            for s, w in target_weight_map.items():
                target_by_cat_w[category_of.get(s, DEFAULT_CAT)] += float(w)

            # Group lots by category (handle substitutions if present)
            if has_substitutions:
                substitution_col = self.portfolio.get_column("Substitution").to_list()
                cat_lot_indices = defaultdict(list)
                for i, (sym, sub) in enumerate(zip(symbols, substitution_col)):
                    target_cat = category_of.get(sub, DEFAULT_CAT) if sub else category_of.get(sym, DEFAULT_CAT)
                    cat_lot_indices[target_cat].append(i)
            else:
                cat_lot_indices = cat_indices
            
            # Category-level deviation (primary)
            all_cats = sorted(set(cat_lot_indices.keys()) | set(target_by_cat_w.keys()))
            for cat in all_cats:
                idxs_cat = np.array(cat_lot_indices.get(cat, []), dtype=int)
                actual = cp.sum(cp.multiply(current_prices[idxs_cat], q[idxs_cat])) if idxs_cat.size else 0.0
                target = float(target_by_cat_w.get(cat, 0.0)) * budget_value
                align_terms.append(cp.square(actual - target))
            
            # Secondary: fit target-model securities to their model targets.
            # We only score actual target securities here so the explanation is
            # simple: once the category is in place, fill the intended names.
            security_dev_terms = []
            for sym, lot_indices in symbol_to_indices.items():
                if sym == "CASH" or sym not in target_symbols_set:
                    continue
                idxs = np.array(lot_indices, dtype=int)
                actual_sym = cp.sum(cp.multiply(current_prices[idxs], q[idxs])) if idxs.size else 0.0
                target_sym = target_weight_map.get(sym, 0.0) * budget_value
                security_dev_terms.append(cp.square(actual_sym - target_sym))
            
            if security_dev_terms:
                align_terms.append(0.1 * cp.sum(security_dev_terms))
                for sym, lot_indices in symbol_to_indices.items():
                    if sym == "CASH" or sym not in target_symbols_set:
                        continue
                    target_sym = target_weight_map.get(sym, 0.0) * budget_value
                    if target_sym <= 1.0:
                        continue
                    idxs = np.array(lot_indices, dtype=int)
                    actual_sym = cp.sum(cp.multiply(current_prices[idxs], q[idxs])) if idxs.size else 0.0
                    relative_target_fit_terms.append(cp.square((actual_sym - target_sym) / max(target_sym, 1.0)))

            # Tertiary: once a category is no longer underweight, prefer
            # shrinking residual non-target legacy holdings toward zero.
            #
            # Only unwind when the freed value has somewhere useful to go, i.e.
            # some non-cash category is still underweight. If the only thing
            # "underweight" is the cash reserve, category deviation already
            # raises exactly the required cash; unwinding further would just
            # churn legacy names into excess cash (up to the cash ceiling).
            cash_categories = {
                category_of.get(s) for s in symbol_to_indices if s == "CASH"
            }
            has_noncash_underweight = any(
                c not in cash_categories
                and category_current_values.get(c, 0.0)
                < category_target_map.get(c, 0.0) * budget_value * 0.995
                for c in category_target_map
            )

            legacy_unwind_terms = []
            for sym, lot_indices in symbol_to_indices.items():
                if sym == "CASH" or sym in target_symbols_set:
                    continue

                cat = category_of.get(sym)
                if not cat or cat == "CASH":
                    continue

                cat_current_val = category_current_values.get(cat, 0.0)
                cat_target_val = category_target_map.get(cat, 0.0) * budget_value
                if cat_current_val <= cat_target_val * 1.005:
                    continue  # only unwind legacy in clearly OVERWEIGHT categories;
                              # keep underweight- and at-target-category holdings frozen
                if not has_noncash_underweight:
                    continue  # nothing but cash to fund; avoid churning into excess cash

                idxs = np.array(lot_indices, dtype=int)
                actual_sym = cp.sum(cp.multiply(current_prices[idxs], q[idxs])) if idxs.size else 0.0
                legacy_unwind_terms.append(cp.square(actual_sym))

            if legacy_unwind_terms:
                align_terms.append(0.05 * cp.sum(legacy_unwind_terms))

            logger.info(f"   {len(all_cats)} categories, {len(security_dev_terms)} securities")
            
                    
        else:
            # STANDARD MODE: Symbol-level alignment
            logger.info(f"[Objective] Standard mode: symbol alignment")
            
            if has_substitutions:
                # Group lots by substitution target symbol
                substitution_col = self.portfolio.get_column("Substitution").to_list()
                sub_target_indices = defaultdict(list)
                for i, (sym, sub) in enumerate(zip(symbols, substitution_col)):
                    if sub:
                        sub_target_indices[sub].append(i)
                    elif sym in target_weight_map and target_weight_map[sym] > 0:
                        sub_target_indices[sym].append(i)
                
                # Deviation from substitution target totals
                for sub_target, idxs in sub_target_indices.items():
                    idxs_arr = np.array(idxs, dtype=int)
                    actual = cp.sum(cp.multiply(current_prices[idxs_arr], q[idxs_arr])) if idxs_arr.size else 0.0
                    target = float(substitution_adjusted_targets.get(sub_target, target_weight_map.get(sub_target, 0.0) * budget_value))
                    align_terms.append(cp.square(actual - target))
                    if sub_target != "CASH" and target > 1.0:
                        relative_target_fit_terms.append(cp.square((actual - target) / max(target, 1.0)))
                
                # Add penalties for target symbols with no holdings
                for s in target_weight_map.keys():
                    if s not in sub_target_indices:
                        idxs_arr = np.array(symbol_to_indices.get(s, []), dtype=int)
                        actual = cp.sum(cp.multiply(current_prices[idxs_arr], q[idxs_arr])) if idxs_arr.size else 0.0
                        target = float(target_weight_map.get(s, 0.0)) * budget_value
                        align_terms.append(cp.square(actual - target))
                        if s != "CASH" and target > 1.0:
                            relative_target_fit_terms.append(cp.square((actual - target) / max(target, 1.0)))
                
                logger.info(f"   {len(sub_target_indices)} substitution targets")
            else:
                # Simple symbol-level alignment
                for s, idxs_s in symbol_to_indices.items():
                    idxs_arr = np.array(idxs_s, dtype=int)
                    actual = cp.sum(cp.multiply(current_prices[idxs_arr], q[idxs_arr])) if idxs_arr.size else 0.0
                    target = float(target_weight_map.get(s, 0.0)) * budget_value
                    align_terms.append(cp.square(actual - target))
                    if s != "CASH" and target > 1.0:
                        relative_target_fit_terms.append(cp.square((actual - target) / max(target, 1.0)))
                
                logger.info(f"   {len(symbol_to_indices)} symbols")

        # Combine alignment terms
        align_dev_sq = cp.hstack(align_terms) if align_terms else cp.Constant([0.0])
        relative_target_fit = cp.hstack(relative_target_fit_terms) if relative_target_fit_terms else cp.Constant([0.0])
        inv_val_safe = max(1e-9, budget_value)
        
        # ============================================================================
        # PRE-SOLVE CONSTRAINT DETAILED ANALYSIS
        # ============================================================================
        logger.debug(f"{'='*80}")
        logger.debug(f"CONSTRAINT DETAILED ANALYSIS")
        logger.debug(f"{'='*80}")
        
        # Build per-symbol constraint counts from the tracking sets
        symbol_buy_blocked = defaultdict(list)
        symbol_sell_blocked = defaultdict(list)
        
        for lot_idx in lots_buy_blocked:
            sym = symbols[lot_idx]
            symbol_buy_blocked[sym].append(lot_idx)
        
        for lot_idx in lots_sell_blocked:
            sym = symbols[lot_idx]
            symbol_sell_blocked[sym].append(lot_idx)
        
        logger.debug(f"[Per-Symbol Constraint Summary]")
        logger.debug(f"{'Symbol':<10} {'Buy Blocked':<15} {'Sell Blocked':<15} {'Current $':<15} {'Target $':<15} {'Notes'}")
        logger.debug(f"{'-'*80}")
        
        for sym in sorted(set(symbols)):
            if sym == "CASH":
                continue
            
            idxs = symbol_to_indices.get(sym, [])
            current_val = float(np.sum(lot_quantities[idxs] * current_prices[idxs])) if idxs else 0.0
            target_val = target_weight_map.get(sym, 0.0) * budget_value
            
            # Calculate COMBINED value (include substitutes flowing INTO this symbol)
            combined_val = current_val
            for sub_sym in substitutes_into.get(sym, []):
                sub_idxs = np.array(symbol_to_indices.get(sub_sym, []), dtype=int)
                if sub_idxs.size > 0:
                    combined_val += float(np.sum(lot_quantities[sub_idxs] * current_prices[sub_idxs]))
            
            buy_blocked = len(symbol_buy_blocked.get(sym, []))
            sell_blocked = len(symbol_sell_blocked.get(sym, []))
            
            # Determine note based on COMBINED value (not just current_val)
            note = ""
            if combined_val > target_val and sell_blocked > 0:
                note = "⚠ OVERWEIGHT but sells blocked!"
            elif combined_val < target_val and buy_blocked > 0 and buy_blocked == len(idxs):
                note = "⚠ UNDERWEIGHT but all buys blocked!"
            
            # Show combined value if different from current
            display_val = combined_val if combined_val != current_val else current_val
            combined_note = f" (comb)" if combined_val != current_val else ""
            
            if buy_blocked > 0 or sell_blocked > 0 or note:
                logger.debug(f"{sym:<10} {buy_blocked:<15} {sell_blocked:<15} ${display_val:>12,.0f}{combined_note:<6} ${target_val:>12,.0f} {note}")
        
        # Generic detailed analysis for substitutes (if any exist)
        # Dynamically analyze any substitutes that have constraints
        if has_substitutions:
            logger.debug(f"[Substitute Securities Detailed Analysis]")
            sub_col = self.portfolio.get_column("Substitution").to_list()
            analyzed_subs = set()
            
            for sym in sorted(set(symbols)):
                if sym == "CASH" or sym in analyzed_subs:
                    continue
                    
                sym_idxs = symbol_to_indices.get(sym, [])
                if not sym_idxs:
                    continue
                    
                # Check if this is a substitute
                sym_sub_target = sub_col[sym_idxs[0]] if sym_idxs else None
                if not sym_sub_target:
                    continue
                    
                analyzed_subs.add(sym)
                sym_val = float(np.sum(lot_quantities[sym_idxs] * current_prices[sym_idxs]))
                sym_target = target_weight_map.get(sym, 0.0) * budget_value
                sym_buy_blocked = len(symbol_buy_blocked.get(sym, []))
                sym_sell_blocked = len(symbol_sell_blocked.get(sym, []))
                
                logger.debug(f"   {sym} (substitute -> {sym_sub_target}):")
                logger.debug(f"      lots: {sym_idxs}")
                logger.debug(f"      value: ${sym_val:,.0f}")
                logger.debug(f"      direct target: ${sym_target:,.0f}")
                logger.debug(f"      buys blocked: {sym_buy_blocked}")
                logger.debug(f"      sells blocked: {sym_sell_blocked}")
                
                # Show combined value with target
                target_idxs = symbol_to_indices.get(sym_sub_target, [])
                target_val_current = float(np.sum(lot_quantities[target_idxs] * current_prices[target_idxs])) if target_idxs else 0.0
                target_target = target_weight_map.get(sym_sub_target, 0.0) * budget_value
                combined = target_val_current + sym_val
                
                logger.debug(f"      {sym_sub_target} value: ${target_val_current:,.0f}")
                logger.debug(f"      {sym_sub_target} target: ${target_target:,.0f}")
                logger.debug(f"      Combined ({sym_sub_target}+{sym}): ${combined:,.0f}")
                logger.debug(f"      Gap to target: ${target_target - combined:,.0f}")
                
                if combined < target_target and sym_sell_blocked > 0:
                    logger.warning(f"      CONFLICT: Combined underweight but {sym} sells blocked!")
                    logger.warning(f"      This means we CANNOT reach the target for {sym_sub_target}!")
        
        # Generic detailed analysis for target symbols with conflicts
        logger.debug(f"[Target Securities With Conflicts Analysis]")
        for sym in sorted(set(symbols)):
            if sym == "CASH":
                continue
                
            sym_idxs = symbol_to_indices.get(sym, [])
            if not sym_idxs:
                continue
                
            # Skip substitutes (already handled above)
            if has_substitutions:
                sub_col_check = self.portfolio.get_column("Substitution").to_list()
                if sub_col_check[sym_idxs[0]]:
                    continue
            
            sym_val = float(np.sum(lot_quantities[sym_idxs] * current_prices[sym_idxs]))
            sym_target = target_weight_map.get(sym, 0.0) * budget_value
            sym_buy_blocked = len(symbol_buy_blocked.get(sym, []))
            sym_sell_blocked = len(symbol_sell_blocked.get(sym, []))
            
            # Only log if there's a conflict
            if sym_val < sym_target and sym_buy_blocked > 0 and sym_buy_blocked == len(sym_idxs):
                logger.warning(f"   {sym}: CONFLICT - underweight but ALL buys blocked!")
                logger.debug(f"      lots: {sym_idxs}")
                logger.debug(f"      value: ${sym_val:,.0f}")
                logger.debug(f"      target: ${sym_target:,.0f}")
                logger.debug(f"      buys blocked: {sym_buy_blocked}")
                logger.debug(f"      sells blocked: {sym_sell_blocked}")
            elif sym_val > sym_target and sym_sell_blocked > 0 and sym_sell_blocked == len(sym_idxs):
                logger.warning(f"   {sym}: CONFLICT - overweight but ALL sells blocked!")
                logger.debug(f"      lots: {sym_idxs}")
                logger.debug(f"      value: ${sym_val:,.0f}")
                logger.debug(f"      target: ${sym_target:,.0f}")
                logger.debug(f"      buys blocked: {sym_buy_blocked}")
                logger.debug(f"      sells blocked: {sym_sell_blocked}")
        
        logger.debug(f"{'='*80}")
        
        # ============================================================================
        # COMPREHENSIVE PRE-SOLVE SUMMARY
        # ============================================================================
        logger.debug(f"{'='*80}")
        logger.debug(f"COMPREHENSIVE PRE-SOLVE SUMMARY")
        logger.debug(f"{'='*80}")
        
        # 1. INITIAL POSITIONS
        logger.debug(f"[1] INITIAL POSITIONS (Current Holdings)")
        logger.debug(f"{'Symbol':<10} {'Lots':<6} {'Quantity':<12} {'Price':<10} {'Value':<15} {'Sub→':<8}")
        logger.debug(f"{'-'*70}")
        
        total_holdings = 0.0
        for sym in sorted(set(symbols)):
            idxs = symbol_to_indices.get(sym, [])
            if not idxs:
                continue
            total_qty = float(np.sum(lot_quantities[idxs]))
            avg_price = float(np.mean(current_prices[idxs])) if idxs else 0
            value = float(np.sum(lot_quantities[idxs] * current_prices[idxs]))
            total_holdings += value
            
            # Get substitution target
            sub_target = ""
            if has_substitutions and substitution_col:
                sub_target = substitution_col[idxs[0]] or ""
            
            if value > 0:
                logger.debug(f"{sym:<10} {len(idxs):<6} {total_qty:<12.2f} ${avg_price:<9.2f} ${value:>12,.0f} {sub_target:<8}")
        
        logger.debug(f"{'-'*70}")
        logger.debug(f"{'TOTAL':<10} {'':<6} {'':<12} {'':<10} ${total_holdings:>12,.0f}")
        
        # 2. TARGET POSITIONS
        logger.debug(f"[2] TARGET POSITIONS")
        logger.debug(f"{'Symbol':<10} {'Weight':<10} {'Target $':<15} {'Current $':<15} {'Gap $':<15} {'Direction':<10}")
        logger.debug(f"{'-'*80}")
        
        for sym in sorted(target_weight_map.keys()):
            if sym == "CASH":
                continue
            weight = target_weight_map.get(sym, 0.0)
            target_val = weight * budget_value
            
            idxs = symbol_to_indices.get(sym, [])
            current_val = float(np.sum(lot_quantities[idxs] * current_prices[idxs])) if idxs else 0.0
            
            # Include substitutes for combined value
            combined_val = current_val
            for sub_sym in substitutes_into.get(sym, []):
                sub_idxs = np.array(symbol_to_indices.get(sub_sym, []), dtype=int)
                if sub_idxs.size > 0:
                    combined_val += float(np.sum(lot_quantities[sub_idxs] * current_prices[sub_idxs]))
            
            gap = target_val - combined_val
            direction = "BUY" if gap > 500 else ("SELL" if gap < -500 else "HOLD")
            
            # Show combined value if different
            current_str = f"${combined_val:>12,.0f}" if combined_val != current_val else f"${current_val:>12,.0f}"
            if combined_val != current_val:
                current_str += " (c)"
            
            logger.debug(f"{sym:<10} {weight*100:>8.2f}% ${target_val:>12,.0f} {current_str:<15} ${gap:>12,.0f} {direction:<10}")
        
        # 3. ALL CONSTRAINTS WITH DESCRIPTIONS
        logger.debug(f"[3] ALL CONSTRAINTS ({len(hard_constraints)} total)")
        logger.debug(f"{'Idx':<5} {'Type':<25} {'Description':<50}")
        logger.debug(f"{'-'*80}")
        
        # Track constraint indices for reference
        constraint_descriptions = []
        for i, c in enumerate(hard_constraints):
            cstr = str(c)
            
            # Categorize constraint
            if i == 0:
                desc = "Cash slack non-negative"
                ctype = "BASIC"
            elif 'sum' in cstr.lower() and '>=' in cstr:
                desc = "Cash/sum lower bound"
                ctype = "CASH"
            elif 'sum' in cstr.lower() and '<=' in cstr:
                desc = "Cash/sum upper bound"
                ctype = "CASH"
            elif '>= 0' in cstr:
                desc = "Non-negativity constraint"
                ctype = "NON-NEG"
            elif '== 0' in cstr:
                # Anti-roundtrip
                if 'bought' in cstr.lower() or any(f'var{j}' in cstr for j in range(200)):
                    desc = "Anti-roundtrip: block buys"
                else:
                    desc = "Anti-roundtrip: block sells"
                ctype = "ANTI-RT"
            elif '>=' in cstr:
                desc = "Substitution lower bound"
                ctype = "SUB-BOUND"
            elif '<=' in cstr:
                desc = "Substitution upper bound"
                ctype = "SUB-BOUND"
            else:
                desc = "Other constraint"
                ctype = "OTHER"
            
            constraint_descriptions.append((ctype, desc))
            
            # Only print first 20 and last 20 to avoid too much output
            if i < 20 or i >= len(hard_constraints) - 20:
                logger.debug(f"{i:<5} {ctype:<25} {desc:<50}")
            elif i == 20:
                logger.debug(f"  ... ({len(hard_constraints) - 40} constraints omitted) ...")
        
        # Summary by type
        type_counts = {}
        for ctype, _ in constraint_descriptions:
            type_counts[ctype] = type_counts.get(ctype, 0) + 1
        
        logger.debug(f"   Constraint summary by type:")
        for ctype, count in sorted(type_counts.items()):
            logger.debug(f"      {ctype}: {count}")
        
        logger.debug(f"{'='*80}")
        
        # ============================================================================
        # SOLVE OPTIMIZATION
        # ============================================================================
        constraint_build_elapsed = time.perf_counter() - perf_start
        solve_opts = dict(
            eps_abs=1e-5, eps_rel=1e-5, max_iter=200000,
            adaptive_rho=False, polish=True, scaling=10, verbose=False
        )
        
        # Objective: minimize alignment deviation + regularization + tax efficiency
        ridge = 1e-12 * (cp.sum_squares(sold) + cp.sum_squares(bought))
        
        # Tax efficiency penalty: prefer selling LT lots over ST lots
        # The rate difference between ST (37%) and LT (20%) is significant
        # We add a penalty for ST sales to guide the optimizer towards LT when possible
        #
        # SCALING:
        # - When tax constraints are active: scale=1.0 to meaningfully steer
        #   toward LT lot selection and respect the tax budget.
        # - When NO tax constraints (full rebalance): scale is near-zero
        #   so tracking error minimization dominates.  The user wants the
        #   portfolio to reach target allocation as closely as possible.
        is_full_rebalance = (constraint_type == 'none')
        tax_efficiency_scale = 1e-6 if is_full_rebalance else 1.0
        # Calculate cost basis per share, handling zero quantities safely
        # Use np.divide with out parameter to avoid division by zero
        safe_quantities = np.where(lot_quantities > 1e-9, lot_quantities, 1.0)
        cost_per_share = np.where(lot_quantities > 1e-9, lot_costs / safe_quantities, current_prices)
        gain_per_share = np.maximum(0, current_prices - cost_per_share)  # Only penalize gains
        st_penalty_rates = np.where(is_long_term, 0.0, short_term_rate - long_term_rate)  # ST gets higher penalty
        tax_efficiency_penalty = tax_efficiency_scale * cp.sum(cp.multiply(st_penalty_rates * gain_per_share, sold))
        
        # Deterministic tie-breaker: small turnover penalty to prefer less trading
        # when multiple equivalent solutions exist. Scale is tiny (~1e-8) so it
        # only affects tie-breaking, not the primary alignment objective.
        turnover_penalty = 1e-8 * (cp.sum(cp.multiply(current_prices, sold)) + cp.sum(cp.multiply(current_prices, bought)))
        zero_gains_loss_harvest_bonus = 0.0
        if (
            constraint_type == 'realized_gains'
            and realized_gains_constraint is not None
            and abs(float(realized_gains_constraint)) < 1e-9
        ):
            # When the user explicitly asks for zero realized gains, prefer
            # harvesting losses if the optimizer can do so while meeting the
            # other hard constraints.
            zero_gains_loss_harvest_bonus = 1e-4 * realized_gains
        
        relative_target_fit_penalty = 5.0 * cp.sum(relative_target_fit)

        objective = cp.Minimize(
            cp.sum(align_dev_sq) / inv_val_safe
            + relative_target_fit_penalty
            + target_proximity_penalty
            + ridge
            + tax_efficiency_penalty
            + turnover_penalty
            + zero_gains_loss_harvest_bonus
        )
        
        problem = cp.Problem(objective, hard_constraints)
        mode_name = "LEGACY" if legacy_mode else "STANDARD"
        
        try:
            solve_start = time.perf_counter()
            solver_used, status = self._solve_with_fallback(problem, f"{mode_name}: SINGLE-PASS", **solve_opts)
            solve_elapsed = time.perf_counter() - solve_start
        except RuntimeError as e:
            # Solver failed - log error and re-raise (infeasibility analysis happens below)
            logger.error(f"{'='*80}")
            logger.error(f"SOLVER FAILED: {str(e)[:200]}")
            logger.error(f"{'='*80}")
            raise  # Re-raise the original error
        
        logger.info(f"[Solve] {mode_name} mode: {solver_used} -> {status}")
        logger.info(
            "[Timing] optimizer build=%.3fs solve=%.3fs constraints=%d variables=%d",
            constraint_build_elapsed,
            solve_elapsed,
            len(hard_constraints),
            n,
        )
        if problem.value is not None:
            logger.info(f"   Objective: {problem.value:,.2f}")
        
        # ============================================================================
        # HANDLE INFEASIBILITY WITH USER-FRIENDLY ANALYSIS
        # ============================================================================
        if solver_used == "INFEASIBLE" or status == cp.INFEASIBLE or status == "infeasible":
            logger.error(f"{'='*80}")
            logger.error(f"OPTIMIZATION INFEASIBLE - ANALYZING ROOT CAUSE")
            logger.error(f"{'='*80}")
            _diagnostic_print(
                "[Optimizer Debug] infeasible "
                f"solver_used={solver_used} "
                f"status={status} "
                f"constraint_type={constraint_type} "
                f"max_tax_bill={float(max_tax_bill):,.2f} "
                f"realized_gains_constraint="
                f"{'None' if realized_gains_constraint is None else f'{float(realized_gains_constraint):,.2f}'}"
            )
            
            try:
                # Get cash values for analysis
                cash_idx = symbols.index("CASH") if "CASH" in symbols else -1
                current_cash = float(lot_quantities[cash_idx] * current_prices[cash_idx]) if cash_idx >= 0 else 0.0

                minimum_budget_result = self._calculate_minimum_required_budget(
                    hard_constraints=hard_constraints,
                    budget_constraints=[realized_gains_budget_constraint, tax_budget_constraint],
                    realized_gains=realized_gains,
                    tax_liability=tax_liability,
                    constraint_type=constraint_type,
                    solve_opts=solve_opts,
                    mandatory_constraints=minimum_budget_constraints,
                )
                allocation_budget_result = None

                infeasibility_result = None
                if minimum_budget_result:
                    minimum_required_budget = minimum_budget_result["minimum_required_budget"]
                    current_budget = (
                        float(realized_gains_constraint)
                        if constraint_type == "realized_gains" and realized_gains_constraint is not None
                        else float(max_tax_bill)
                    )
                    if minimum_required_budget > current_budget + 1.0:
                        if constraint_type == "realized_gains":
                            minimum_budget_label = "realized gains limit"
                        else:
                            minimum_budget_label = "tax budget"
                        infeasibility_result = self._build_minimum_budget_infeasibility_result(
                            minimum_budget_result=minimum_budget_result,
                            current_budget=current_budget,
                            budget_label=minimum_budget_label,
                            budget_value=budget_value,
                            current_cash=current_cash,
                            cash_floor=self._cash_floor_dollars or 0.0,
                        )
                        _diagnostic_print(
                            "[Optimizer Debug] minimum_required_budget "
                            f"type={constraint_type} "
                            f"current={current_budget:,.2f} "
                            f"minimum={minimum_required_budget:,.2f}"
                        )

                if infeasibility_result is None:
                    if constraint_type in {"realized_gains", "tax_budget"}:
                        current_budget = (
                            float(realized_gains_constraint)
                            if constraint_type == "realized_gains" and realized_gains_constraint is not None
                            else float(max_tax_bill)
                        )
                        allocation_budget_result = self._calculate_minimum_required_budget(
                            hard_constraints=hard_constraints,
                            budget_constraints=[realized_gains_budget_constraint, tax_budget_constraint],
                            realized_gains=realized_gains,
                            tax_liability=tax_liability,
                            constraint_type=constraint_type,
                            solve_opts=solve_opts,
                        )
                        infeasibility_result = self._build_constrained_budget_infeasibility_result(
                            constraint_type=constraint_type,
                            current_budget=current_budget,
                            budget_value=budget_value,
                            current_cash=current_cash,
                            cash_floor=self._cash_floor_dollars or 0.0,
                            minimum_budget_result=minimum_budget_result,
                            allocation_budget_result=allocation_budget_result,
                        )
                    else:
                        # Run the comprehensive infeasibility analysis for non-budget
                        # failures, such as cash bounds or incompatible restrictions.
                        infeasibility_result = self._analyze_infeasibility(
                            hard_constraints=hard_constraints,
                            objective=objective,
                            symbols=symbols,
                            lot_quantities=lot_quantities,
                            current_prices=current_prices,
                            target_weight_map=target_weight_map,
                            budget_value=budget_value,
                            substitutes_into=substitutes_into,
                            max_tax_bill=max_tax_bill,
                            cash_floor=self._cash_floor_dollars or 0.0,
                            cash_ceiling=getattr(self, "_cash_ceiling_dollars", float("inf")),
                            current_cash=current_cash,
                            constraint_type=constraint_type
                        )
                
                # Print user-friendly summary
                logger.error(f"{'='*80}")
                logger.error(f"INFEASIBILITY ANALYSIS RESULTS")
                logger.error(f"{'='*80}")
                logger.error(f"SUMMARY: {infeasibility_result['summary']}")
                _diagnostic_print(f"[Optimizer Debug] infeasibility_summary={infeasibility_result['summary']}")
                
                if infeasibility_result['causes']:
                    logger.error(f"CAUSES IDENTIFIED:")
                    for i, cause in enumerate(infeasibility_result['causes'], 1):
                        logger.error(f"   {i}. {cause}")
                        _diagnostic_print(f"[Optimizer Debug] cause_{i}={cause}")
                
                if infeasibility_result['suggestions']:
                    logger.info(f"SUGGESTIONS:")
                    for i, suggestion in enumerate(infeasibility_result['suggestions'], 1):
                        logger.info(f"   {i}. {suggestion}")
                        _diagnostic_print(f"[Optimizer Debug] suggestion_{i}={suggestion}")
                
                logger.debug(f"DETAILS:")
                logger.debug(infeasibility_result['details'])
                
                # Print technical details for debugging
                tech = infeasibility_result['technical']
                logger.debug(f"TECHNICAL DETAILS:")
                logger.debug(f"   First infeasible constraint: #{tech.get('first_infeasible_constraint_idx', 'N/A')}")
                logger.debug(f"   Constraint counts: {tech.get('constraint_counts', {})}")
                logger.debug(f"   Causes found: {tech.get('causes_found', [])}")
                logger.debug(f"   Total sell needed: ${tech.get('total_sell_needed', 0):,.0f}")
                logger.debug(f"   Total buy needed: ${tech.get('total_buy_needed', 0):,.0f}")
                logger.debug(f"   Estimated tax: ${tech.get('estimated_tax', 0):,.0f}")
                logger.debug(f"   Tax headroom: ${tech.get('tax_headroom', 0):,.0f}")
                _diagnostic_print(
                    "[Optimizer Debug] infeasibility_technical "
                    f"first_constraint={tech.get('first_infeasible_constraint_idx', 'N/A')} "
                    f"total_sell_needed={tech.get('total_sell_needed', 0):,.2f} "
                    f"total_buy_needed={tech.get('total_buy_needed', 0):,.2f} "
                    f"estimated_tax={tech.get('estimated_tax', 0):,.2f} "
                    f"tax_headroom={tech.get('tax_headroom', 0):,.2f}"
                )
                
                logger.error(f"{'='*80}")
                
                # Raise with user-friendly message
                error_msg = f"Optimization cannot be completed.\n\n"
                error_msg += f"PROBLEM: {infeasibility_result['summary']}\n\n"
                if infeasibility_result['causes']:
                    error_msg += "CAUSES:\n"
                    for cause in infeasibility_result['causes']:
                        error_msg += f"  • {cause}\n"
                    error_msg += "\n"
                if infeasibility_result['suggestions']:
                    error_msg += "SUGGESTIONS:\n"
                    for suggestion in infeasibility_result['suggestions']:
                        error_msg += f"  • {suggestion}\n"
                
                raise RuntimeError(error_msg)
                
            except RuntimeError:
                # Preserve the user-friendly infeasibility message generated above.
                raise
            except Exception as analysis_error:
                # Analysis failed - raise with basic info
                logger.warning(f"Infeasibility analysis failed: {analysis_error}")
                logger.warning(f"   Raising basic error message instead")
                _diagnostic_print(f"[Optimizer Debug] infeasibility_analysis_failed={analysis_error}")
                
                # Determine user-friendly constraint name based on what the user entered
                if constraint_type == 'realized_gains':
                    constraint_name = "Realized Gains Budget"
                    constraint_field = "realized gains limit"
                elif constraint_type == 'tax_budget':
                    constraint_name = "Tax Budget"
                    constraint_field = "tax budget"
                else:
                    constraint_name = "Tax Budget"  # Default fallback
                    constraint_field = "tax budget"
                
                # Build a basic error message with what we know
                basic_error_msg = "Optimization cannot be completed.\n\n"
                basic_error_msg += "PROBLEM: The requested portfolio rebalancing is not feasible with the current constraints.\n\n"
                basic_error_msg += "CAUSES:\n"
                basic_error_msg += f"  • {constraint_name} of ${max_tax_bill:,.0f} may be insufficient for the required trades\n"
                basic_error_msg += f"  • Target allocation may require more buying/selling than constraints allow\n\n"
                basic_error_msg += "SUGGESTIONS:\n"
                basic_error_msg += f"  • Try increasing the {constraint_field}\n"
                basic_error_msg += "  • Choose a target allocation closer to current holdings\n"
                basic_error_msg += "  • Reduce the cash reserve requirement\n"
                
                raise RuntimeError(basic_error_msg)
        
        # ============================================================================
        # EXTRACT AND POST-PROCESS SOLUTION
        # ============================================================================
        tol = 1.0
        sold_val = self._to_array(sold, n)
        bought_val = self._to_array(bought, n)

        # DEBUG: Check all symbols immediately after solve
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("=== POST-SOLVE DEBUG (before enforcement) ===")
            for sym in sorted(set(symbols)):
                if sym == "CASH":
                    continue
                sym_indices = [i for i, s in enumerate(symbols) if s == sym]
                if sym_indices:
                    total_bought = sum(bought_val[idx] for idx in sym_indices)
                    total_sold = sum(sold_val[idx] for idx in sym_indices)
                    if abs(total_bought) > 0.01 or abs(total_sold) > 0.01:
                        logger.debug(f"{sym}: lots={len(sym_indices)}, bought={total_bought:.2f}, sold={total_sold:.2f}")
            logger.debug("============================")

        # ============================================================================
        # POST-SOLVE DIRECTION ENFORCEMENT
        # ============================================================================
        # The solver may violate constraints due to numerical issues.
        # Re-enforce the direction constraints by zeroing out invalid trades.
        # ============================================================================
        logger.debug("=== POST-SOLVE DIRECTION ENFORCEMENT ===")
        enforced_count = 0

        # Get substitution info
        substitution_col_post = None
        if has_substitutions:
            substitution_col_post = self.portfolio.get_column("Substitution").to_list()

        # Re-apply explicit no-trade hard blocks first. These are true hard
        # constraints and must survive any inexact solver output.
        hard_block_buy_idxs = set(int(i) for i in np.atleast_1d(existing_idx).tolist()) if existing_idx.size else set()
        hard_block_sell_idxs = set()

        hold_symbols_post = set(trade_restrictions.get("Hold", []))
        buy_only_symbols_post = set(trade_restrictions.get("Buy", []))
        sell_only_symbols_post = set(trade_restrictions.get("Sell", []))

        for i, sym in enumerate(symbols):
            if sym == "CASH":
                continue

            if sym in hold_symbols_post:
                hard_block_buy_idxs.add(i)
                hard_block_sell_idxs.add(i)
            elif sym in buy_only_symbols_post:
                hard_block_sell_idxs.add(i)
            elif sym in sell_only_symbols_post:
                hard_block_buy_idxs.add(i)

            if wash_sale and sym in wash_sale_symbols:
                hard_block_buy_idxs.add(i)

            if sym in excluded_set:
                if wash_sale and sym in wash_sale_symbols:
                    hard_block_buy_idxs.add(i)
                else:
                    hard_block_buy_idxs.add(i)
                    hard_block_sell_idxs.add(i)

            if sym not in buyable_symbols:
                hard_block_buy_idxs.add(i)

        if has_substitutions:
            wash_sale_proxy_symbols_post = set(getattr(self, '_wash_sale_proxy_substitutions', {}) or {})
            for i, sub in enumerate(substitution_col_post or []):
                if sub and lot_quantities[i] < 1e-9 and symbols[i] not in wash_sale_proxy_symbols_post:
                    hard_block_buy_idxs.add(i)

        for idx in sorted(hard_block_buy_idxs):
            if bought_val[idx] > 0:
                logger.debug(f"  Enforcing bought[{idx}]=0 (was {bought_val[idx]:.4f}) - explicit hard buy block")
                bought_val[idx] = 0.0
                enforced_count += 1

        for idx in sorted(hard_block_sell_idxs):
            if sold_val[idx] > 0:
                logger.debug(f"  Enforcing sold[{idx}]=0 (was {sold_val[idx]:.4f}) - explicit hard sell block")
                sold_val[idx] = 0.0
                enforced_count += 1

        for idx in sorted(forced_liquidation_lot_indices):
            target_sold = float(lot_quantities[idx])
            if abs(float(sold_val[idx]) - target_sold) > 1e-6 or bought_val[idx] > 0:
                logger.debug(
                    f"  Enforcing full forced liquidation for {symbols[idx]} "
                    f"(sold {sold_val[idx]:.4f} → {target_sold:.4f}, bought {bought_val[idx]:.4f} → 0)"
                )
                sold_val[idx] = target_sold
                bought_val[idx] = 0.0
                enforced_count += 1

        wash_sale_trace_symbols = set()
        if wash_sale:
            wash_sale_trace_symbols.update(wash_sale_symbols)
        wash_sale_trace_symbols.update(set(getattr(self, '_wash_sale_proxy_substitutions', {}) or {}))
        wash_sale_trace_symbols.update(set((getattr(self, '_wash_sale_proxy_substitutions', {}) or {}).values()))
        if wash_sale_trace_symbols and _verbose_debug_logging_enabled():
            substitution_trace = (
                self.portfolio.get_column("Substitution").to_list()
                if "Substitution" in self.portfolio.columns
                else [""] * n
            )
            wash_sale_trade_rows = []
            for i, sym in enumerate(symbols):
                if sym not in wash_sale_trace_symbols:
                    continue
                wash_sale_trade_rows.append({
                    "idx": int(i),
                    "symbol": sym,
                    "substitution": substitution_trace[i],
                    "lot_quantity": float(lot_quantities[i]),
                    "price": float(current_prices[i]),
                    "current_value": float(lot_quantities[i] * current_prices[i]),
                    "bought_shares_after_hard_blocks": float(bought_val[i]),
                    "sold_shares_after_hard_blocks": float(sold_val[i]),
                    "bought_value_after_hard_blocks": float(bought_val[i] * current_prices[i]),
                    "sold_value_after_hard_blocks": float(sold_val[i] * current_prices[i]),
                    "hard_buy_blocked": int(i) in hard_block_buy_idxs,
                    "hard_sell_blocked": int(i) in hard_block_sell_idxs,
                })
            logger.debug(
                "[WASH_SALE_DEBUG] post_hard_block_trade_trace "
                f"trace_symbols={sorted(wash_sale_trace_symbols)} rows={wash_sale_trade_rows}"
            )

        bought_val_after_explicit_blocks = bought_val.copy()
        sold_val_after_explicit_blocks = sold_val.copy()

        def _rebalance_corridor_status_from_trades(candidate_bought, candidate_sold):
            if not target_rebalance_weights:
                return None

            managed_indices = rebalance_indices.get("equity", []) + rebalance_indices.get("fixed income", [])
            if not managed_indices:
                return None

            candidate_qty = np.maximum(0.0, lot_quantities + candidate_bought - candidate_sold)
            equity_indices = np.array(rebalance_indices.get("equity", []), dtype=int)
            fixed_indices = np.array(rebalance_indices.get("fixed income", []), dtype=int)
            equity_value = float(np.sum(candidate_qty[equity_indices] * current_prices[equity_indices])) if equity_indices.size else 0.0
            fixed_income_value = float(np.sum(candidate_qty[fixed_indices] * current_prices[fixed_indices])) if fixed_indices.size else 0.0
            managed_total = equity_value + fixed_income_value
            if managed_total <= 1e-9:
                return None

            equity_percent = equity_value / managed_total
            fixed_income_percent = fixed_income_value / managed_total
            target_equity = float(target_rebalance_weights.get("equity", 0.0))
            target_fixed_income = float(target_rebalance_weights.get("fixed income", 0.0))
            tolerance = 0.05
            equity_diff = abs(equity_percent - target_equity)
            fixed_income_diff = abs(fixed_income_percent - target_fixed_income)

            return {
                "within_tolerance": equity_diff <= tolerance and fixed_income_diff <= tolerance,
                "equity_value": equity_value,
                "fixed_income_value": fixed_income_value,
                "managed_total": managed_total,
                "equity_percent": equity_percent,
                "fixed_income_percent": fixed_income_percent,
                "target_equity": target_equity,
                "target_fixed_income": target_fixed_income,
                "equity_diff": equity_diff,
                "fixed_income_diff": fixed_income_diff,
            }

        def _print_rebalance_position_diagnostics(label, candidate_bought, candidate_sold):
            if not _verbose_debug_logging_enabled():
                return
            if not target_rebalance_weights:
                logger.debug(f"[MODEL_ASSIGNMENT_DEBUG] {label}_positions skipped reason=no_target_rebalance_weights")
                return

            rebalance_category_values = (
                self.portfolio.get_column("Rebalance Category").to_list()
                if "Rebalance Category" in self.portfolio.columns
                else [""] * n
            )
            unmanaged_values = (
                self.portfolio.get_column("Unmanaged").to_list()
                if "Unmanaged" in self.portfolio.columns
                else [""] * n
            )
            category_values = (
                self.portfolio.get_column("Category").to_list()
                if "Category" in self.portfolio.columns
                else [""] * n
            )
            asset_class_values = (
                self.portfolio.get_column("Asset Class").to_list()
                if "Asset Class" in self.portfolio.columns
                else [""] * n
            )
            security_type_values = (
                self.portfolio.get_column("Security Type").to_list()
                if "Security Type" in self.portfolio.columns
                else [""] * n
            )
            substitution_values = (
                self.portfolio.get_column("Substitution").to_list()
                if "Substitution" in self.portfolio.columns
                else [""] * n
            )

            candidate_qty = np.maximum(0.0, lot_quantities + candidate_bought - candidate_sold)
            rows = []
            for i, sym in enumerate(symbols):
                normalized_symbol = str(sym or "").strip().upper()
                current_value = float(lot_quantities[i] * current_prices[i])
                final_value = float(candidate_qty[i] * current_prices[i])
                bought_value = float(candidate_bought[i] * current_prices[i])
                sold_value = float(candidate_sold[i] * current_prices[i])

                rebalance_norm = _normalize_rebalance_category_for_tolerance(rebalance_category_values[i])
                unmanaged_norm = str(unmanaged_values[i] or "").strip().lower()
                if not normalized_symbol:
                    decision = "skip_missing_symbol"
                elif normalized_symbol == "CASH":
                    decision = "skip_cash"
                elif normalized_symbol in excluded_set:
                    decision = "skip_trading_exclusion"
                elif unmanaged_norm == "yes":
                    decision = "skip_unmanaged"
                elif not rebalance_norm:
                    decision = "skip_missing_rebalance_category"
                else:
                    decision = "included"

                if (
                    decision != "included"
                    and abs(final_value) < 0.01
                    and abs(current_value) < 0.01
                    and abs(bought_value) < 0.01
                    and abs(sold_value) < 0.01
                ):
                    continue

                rows.append({
                    "idx": i,
                    "symbol": normalized_symbol or sym,
                    "decision": decision,
                    "rebalance_category": rebalance_category_values[i],
                    "rebalance_norm": rebalance_norm,
                    "unmanaged": unmanaged_values[i],
                    "category": category_values[i],
                    "asset_class": asset_class_values[i],
                    "security_type": security_type_values[i],
                    "substitution": substitution_values[i],
                    "current_qty": float(lot_quantities[i]),
                    "final_qty": float(candidate_qty[i]),
                    "price": float(current_prices[i]),
                    "current_value": current_value,
                    "final_value": final_value,
                    "bought_shares": float(candidate_bought[i]),
                    "sold_shares": float(candidate_sold[i]),
                    "bought_value": bought_value,
                    "sold_value": sold_value,
                    "target_weight": float(target_weight_map.get(substitution_values[i] or normalized_symbol, 0.0) or 0.0),
                    "excluded": normalized_symbol in excluded_set,
                })

            rows.sort(key=lambda row: (row["decision"] != "included", row["rebalance_norm"], -abs(row["final_value"]), row["symbol"]))
            included_equity = sum(row["final_value"] for row in rows if row["decision"] == "included" and row["rebalance_norm"] == "equity")
            included_fixed = sum(row["final_value"] for row in rows if row["decision"] == "included" and row["rebalance_norm"] == "fixed income")
            included_total = included_equity + included_fixed
            logger.debug(
                f"[MODEL_ASSIGNMENT_DEBUG] {label}_position_diagnostics "
                f"included_equity={included_equity:.2f} "
                f"included_fixed_income={included_fixed:.2f} "
                f"included_total={included_total:.2f} "
                f"included_equity_percent={(included_equity / included_total * 100.0) if included_total else None} "
                f"row_count={len(rows)} rows={rows}"
            )
        
        # Build substitutes_into map again
        substitutes_into_post = defaultdict(list)
        if has_substitutions and substitution_col_post:
            for sym, lot_idxs in symbol_to_indices.items():
                if lot_idxs:
                    sym_sub = substitution_col_post[lot_idxs[0]]
                    if sym_sub:
                        substitutes_into_post[sym_sub].append(sym)
        
        if legacy_mode:
            logger.debug("  Legacy mode: post-solve direction enforcement deferred to legacy/category constraints")
        else:
            def _post_trade_value(index_array: np.ndarray) -> float:
                if index_array.size == 0:
                    return 0.0
                post_qty = np.maximum(0.0, lot_quantities[index_array] + bought_val[index_array] - sold_val[index_array])
                return float(np.sum(post_qty * current_prices[index_array]))

            for sym, lot_indices in symbol_to_indices.items():
                if sym == "CASH":
                    continue
                
                idxs = np.array(lot_indices, dtype=int)
                if idxs.size == 0:
                    continue
                
                # Check if substitute
                sym_sub = None
                if has_substitutions and substitution_col_post and lot_indices:
                    raw_sub = substitution_col_post[lot_indices[0]]
                    if raw_sub and raw_sub != sym:
                        sym_sub = raw_sub
                
                if sym_sub:
                    is_wash_sale_proxy = sym in set(getattr(self, '_wash_sale_proxy_substitutions', {}) or {})
                    combined_for_target_post = 0.0
                    target_idxs = np.array(symbol_to_indices.get(sym_sub, []), dtype=int)
                    if target_idxs.size > 0:
                        combined_for_target_post += _post_trade_value(target_idxs)
                    combined_for_target_post += _post_trade_value(idxs)
                    for other_sub in substitutes_into_post.get(sym_sub, []):
                        if other_sub == sym:
                            continue
                        other_idxs = np.array(symbol_to_indices.get(other_sub, []), dtype=int)
                        if other_idxs.size > 0:
                            combined_for_target_post += _post_trade_value(other_idxs)
                    target_val = target_weight_map.get(sym_sub, 0.0) * budget_value
                    threshold = budget_value * 0.001
                    for idx in lot_indices:
                        if bought_val[idx] > 0 and not is_wash_sale_proxy:
                            logger.debug(f"  {sym}: Enforcing bought[{idx}]=0 (was {bought_val[idx]:.4f}) - substitute")
                            bought_val[idx] = 0.0
                            enforced_count += 1
                        if combined_for_target_post < target_val - threshold and sold_val[idx] > 0:
                            logger.debug(f"  {sym}: Enforcing sold[{idx}]=0 (was {sold_val[idx]:.4f}) - underweight substitute group")
                            sold_val[idx] = 0.0
                            enforced_count += 1
                else:
                    has_subs_into = len(substitutes_into_post.get(sym, [])) > 0
                    combined_val_post = _post_trade_value(idxs)
                    if has_subs_into:
                        for sub_sym in substitutes_into_post.get(sym, []):
                            sub_idxs_post = np.array(symbol_to_indices.get(sub_sym, []), dtype=int)
                            if sub_idxs_post.size > 0:
                                combined_val_post += _post_trade_value(sub_idxs_post)
                    
                    target_val = target_weight_map.get(sym, 0.0) * budget_value
                    threshold = budget_value * 0.001
                    
                    if combined_val_post > target_val + threshold:
                        for idx in lot_indices:
                            if bought_val[idx] > 0:
                                logger.debug(f"  {sym}: Enforcing bought[{idx}]=0 (was {bought_val[idx]:.4f}) - overweight{'(with subs)' if has_subs_into else ''}")
                                bought_val[idx] = 0.0
                                enforced_count += 1
                    elif combined_val_post < target_val - threshold:
                        for idx in lot_indices:
                            if sold_val[idx] > 0:
                                logger.debug(f"  {sym}: Enforcing sold[{idx}]=0 (was {sold_val[idx]:.4f}) - underweight{'(with subs)' if has_subs_into else ''}")
                                sold_val[idx] = 0.0
                                enforced_count += 1
        
        logger.debug(f"  Total enforcements: {enforced_count}")
        logger.debug("=========================================")

        post_direction_status = _rebalance_corridor_status_from_trades(bought_val, sold_val)
        explicit_only_status = _rebalance_corridor_status_from_trades(
            bought_val_after_explicit_blocks,
            sold_val_after_explicit_blocks,
        )
        if (
            post_direction_status
            and explicit_only_status
            and not post_direction_status["within_tolerance"]
            and explicit_only_status["within_tolerance"]
        ):
            logger.warning(
                "Post-solve direction enforcement would move the optimized portfolio outside "
                "the Rebalance Category model corridor; reverting heuristic direction edits "
                "and keeping explicit hard-block enforcement only."
            )
            logger.debug(
                "[MODEL_ASSIGNMENT_DEBUG] optimizer_post_direction_reverted "
                f"post_equity={post_direction_status['equity_percent'] * 100:.4f} "
                f"post_fixed_income={post_direction_status['fixed_income_percent'] * 100:.4f} "
                f"explicit_equity={explicit_only_status['equity_percent'] * 100:.4f} "
                f"explicit_fixed_income={explicit_only_status['fixed_income_percent'] * 100:.4f}"
            )
            bought_val = bought_val_after_explicit_blocks.copy()
            sold_val = sold_val_after_explicit_blocks.copy()
        elif post_direction_status:
            logger.debug(
                "[MODEL_ASSIGNMENT_DEBUG] optimizer_post_direction_status "
                f"within_tolerance={post_direction_status['within_tolerance']} "
                f"equity={post_direction_status['equity_percent'] * 100:.4f} "
                f"fixed_income={post_direction_status['fixed_income_percent'] * 100:.4f} "
                f"target_equity={post_direction_status['target_equity'] * 100:.4f} "
                f"target_fixed_income={post_direction_status['target_fixed_income'] * 100:.4f}"
            )
        _print_rebalance_position_diagnostics("optimizer_post_direction", bought_val, sold_val)

        # Drop tiny trades
        sold_val[sold_val < tol] = 0.0
        bought_val[bought_val < tol] = 0.0

        # DEBUG: Check symbols AFTER enforcement and tiny drop
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("=== AFTER ENFORCEMENT & TINY DROP ===")
            for sym in sorted(set(symbols)):
                if sym == "CASH":
                    continue
                sym_indices = [i for i, s in enumerate(symbols) if s == sym]
                if sym_indices:
                    total_bought = sum(bought_val[idx] for idx in sym_indices)
                    total_sold = sum(sold_val[idx] for idx in sym_indices)
                    if abs(total_bought) > 0.01 or abs(total_sold) > 0.01:
                        logger.debug(f"{sym}: lots={len(sym_indices)}, bought={total_bought:.2f}, sold={total_sold:.2f}")
            logger.debug("==========================================")

        # Log raw solution before rounding
        logger.info("RAW OPTIMIZATION SOLUTION (before rounding)")
        
        if has_substitutions:
            substitution_col = self.portfolio.get_column("Substitution").to_list()
            logger.info("SUBSTITUTED SECURITIES:")
            for i, (sym, sub, qty) in enumerate(zip(symbols, substitution_col, lot_quantities)):
                if sub and (bought_val[i] > tol or sold_val[i] > tol):
                    logger.info(f"  {sym} (->{sub}): Initial={qty:.2f}, Bought={bought_val[i]:.2f}, Sold={sold_val[i]:.2f}, Final={qty + bought_val[i] - sold_val[i]:.2f}")
        
        logger.info("REGULAR SECURITIES (with trades):")
        for i, (sym, qty) in enumerate(zip(symbols, lot_quantities)):
            sub = substitution_col[i] if has_substitutions else None
            if not sub and (bought_val[i] > tol or sold_val[i] > tol):
                logger.info(f"  {sym}: Initial={qty:.2f}, Bought={bought_val[i]:.2f}, Sold={sold_val[i]:.2f}, Final={qty + bought_val[i] - sold_val[i]:.2f}")
        

        # Preserve your prior rounding: floor when > 1 share
        if not fractional:
            pass  # (flag kept for interface; current rounding logic below matches your original)
        sold_val = np.where(sold_val > 1, np.floor(sold_val), sold_val)
        bought_val = np.where(bought_val > 1, np.floor(bought_val), bought_val)

        for idx in sorted(forced_liquidation_lot_indices):
            sold_val[idx] = float(lot_quantities[idx])
            bought_val[idx] = 0.0

        if constraint_type == "none":
            zero_target_dust_closed = []
            for i, sym in enumerate(symbols):
                if sym == "CASH":
                    continue
                if i in hard_block_sell_idxs or i in lots_sell_blocked:
                    continue
                if bought_val[i] > tol or sold_val[i] <= tol:
                    continue
                if float(target_values_static.get(sym, 0.0) or 0.0) > 1.0:
                    continue

                residual_qty = max(0.0, float(lot_quantities[i] + bought_val[i] - sold_val[i]))
                residual_value = residual_qty * float(current_prices[i])
                if residual_qty > 1e-9 and residual_value <= zero_target_liquidation_band + 1e-6:
                    sold_val[i] = float(lot_quantities[i])
                    bought_val[i] = 0.0
                    zero_target_dust_closed.append((sym, residual_qty, residual_value))

            if zero_target_dust_closed:
                logger.info(
                    "Closed zero-target dust residuals after whole-share rounding: "
                    f"{[(sym, round(qty, 4), round(val, 2)) for sym, qty, val in zero_target_dust_closed]}"
                )

        optimized_qty = np.maximum(0, lot_quantities + bought_val - sold_val)

        # Safety guard (overshoot)
        if float(np.sum(optimized_qty * current_prices)) > budget_value + 1e-6:
            optimized_qty, bought_val, cash_slack_amt = self._correct_overshoot(
                optimized_qty, bought_val, sold_val, lot_quantities, current_prices, budget_value, cash_idxs=cash_idxs
            )
        else:
            cash_slack_amt = 0.0

        # Net cash lots and recompute q
        bought_val, sold_val = self._net_cash_lots(bought_val, sold_val, lot_quantities, symbols)
        optimized_qty = np.maximum(0, lot_quantities + bought_val - sold_val)

        # ------------------------------------------------------------------
        # RAISE CASH TO FLOOR (post-rounding correction)
        # ------------------------------------------------------------------
        # Whole-share rounding floors every sell (see np.floor above), which
        # systematically under-raises cash. In cash-raise / carve-out
        # scenarios the required cash floor is large, so the floored proceeds
        # can land just below the floor and trip the hard cash-target guard
        # further down. Sell additional whole shares (lots already being sold
        # first, then lowest realized gain per share to minimize added tax)
        # until the projected cash meets the floor.
        budget_violation_tolerance = 1.0
        cash_correction_tol = 0.01
        if cash_idxs.size and cash_floor > cash_correction_tol:
            noncash_mask = ~is_cash
            noncash_value = float(np.sum(optimized_qty[noncash_mask] * current_prices[noncash_mask]))
            cash_deficit = cash_floor - (budget_value - noncash_value)
            if cash_deficit > cash_correction_tol:
                excluded_set = getattr(self, "_excluded_securities", set())
                protected_extra_sell_idxs = set(hard_block_sell_idxs) | set(lots_sell_blocked)
                current_realized_gains_for_budget = float(np.sum(sold_val * gains_per_share))
                current_tax_for_budget = float(np.sum(sold_val * gains_per_share * rate_vec))

                def _budget_limited_extra_shares(lot_idx, desired_shares):
                    max_shares = float(desired_shares)
                    per_share_gain = float(gains_per_share[lot_idx])

                    if (
                        constraint_type == "realized_gains"
                        and realized_gains_constraint is not None
                        and per_share_gain > 0
                    ):
                        remaining_gain_budget = (
                            float(realized_gains_constraint)
                            - current_realized_gains_for_budget
                            + budget_violation_tolerance
                        )
                        if remaining_gain_budget <= 0:
                            return 0.0
                        max_shares = min(max_shares, np.floor(remaining_gain_budget / per_share_gain))

                    if constraint_type == "tax_budget":
                        per_share_tax = per_share_gain * float(rate_vec[lot_idx])
                        if per_share_tax > 0:
                            remaining_tax_budget = (
                                float(max_tax_bill)
                                - current_tax_for_budget
                                + budget_violation_tolerance
                            )
                            if remaining_tax_budget <= 0:
                                return 0.0
                            max_shares = min(max_shares, np.floor(remaining_tax_budget / per_share_tax))

                    return max(0.0, float(max_shares))

                sellable = [
                    i for i in range(n)
                    if not is_cash[i]
                    and symbols[i] not in excluded_set
                    and i not in protected_extra_sell_idxs
                    and bought_val[i] <= tol
                    and current_prices[i] > 0
                    and optimized_qty[i] > 1e-9
                ]
                # Prefer lots already being sold (extends the intended sells),
                # then lowest realized gain per share to minimize added tax.
                sellable.sort(key=lambda j: (sold_val[j] <= tol, gains_per_share[j]))
                for i in sellable:
                    if cash_deficit <= cash_correction_tol:
                        break
                    max_shares = float(np.floor(optimized_qty[i] + 1e-9))
                    if max_shares < 1:
                        continue
                    need_shares = float(np.ceil(cash_deficit / current_prices[i]))
                    sell_more = min(max_shares, need_shares)
                    sell_more = _budget_limited_extra_shares(i, sell_more)
                    if sell_more < 1:
                        continue
                    sold_val[i] += sell_more
                    optimized_qty[i] = max(0.0, lot_quantities[i] + bought_val[i] - sold_val[i])
                    cash_deficit -= sell_more * current_prices[i]
                    current_realized_gains_for_budget += sell_more * gains_per_share[i]
                    current_tax_for_budget += sell_more * gains_per_share[i] * rate_vec[i]
                if cash_deficit > cash_correction_tol:
                    logger.warning(
                        "Cash-raise rounding correction could not fully close deficit; "
                        f"remaining ${cash_deficit:,.2f}"
                    )
                else:
                    logger.info(
                        "Cash-raise rounding correction: sold additional whole shares to meet cash floor"
                    )

        cash_lower = float(min(start_cash, cash_floor))
        cash_upper = float(max(start_cash, cash_floor))

        # ========================================================================
        # BUDGET BALANCING: Adjust CASH to ensure total value matches exactly
        # ========================================================================
        # Due to rounding and solver tolerances, the optimized total may not 
        # exactly equal the starting budget. Adjust CASH position to compensate.
        optimized_qty = self._balance_budget_via_cash(
            optimized_qty=optimized_qty,
            current_prices=current_prices,
            symbols=symbols,
            budget_value=budget_value,
            cash_lower=None,
            cash_upper=None
        )
        if cash_idxs.size:
            # Keep CASH trade instructions aligned with the final balanced
            # portfolio so exports/results match the proposed cash position.
            cash_delta = optimized_qty[cash_idxs] - lot_quantities[cash_idxs]
            bought_val[cash_idxs] = np.where(cash_delta > 0, cash_delta, 0.0)
            sold_val[cash_idxs] = np.where(cash_delta < 0, -cash_delta, 0.0)

        if wash_sale_trace_symbols and _verbose_debug_logging_enabled():
            substitution_trace = (
                self.portfolio.get_column("Substitution").to_list()
                if "Substitution" in self.portfolio.columns
                else [""] * n
            )
            final_wash_sale_trade_rows = []
            for i, sym in enumerate(symbols):
                if sym not in wash_sale_trace_symbols:
                    continue
                final_wash_sale_trade_rows.append({
                    "idx": int(i),
                    "symbol": sym,
                    "substitution": substitution_trace[i],
                    "lot_quantity": float(lot_quantities[i]),
                    "optimized_quantity": float(optimized_qty[i]),
                    "price": float(current_prices[i]),
                    "current_value": float(lot_quantities[i] * current_prices[i]),
                    "final_value": float(optimized_qty[i] * current_prices[i]),
                    "bought_shares": float(bought_val[i]),
                    "sold_shares": float(sold_val[i]),
                    "bought_value": float(bought_val[i] * current_prices[i]),
                    "sold_value": float(sold_val[i] * current_prices[i]),
                })
            logger.debug(
                "[WASH_SALE_DEBUG] final_trade_trace "
                f"trace_symbols={sorted(wash_sale_trace_symbols)} rows={final_wash_sale_trade_rows}"
            )

        final_corridor_status = _rebalance_corridor_status_from_trades(bought_val, sold_val)
        if final_corridor_status:
            logger.debug(
                "[MODEL_ASSIGNMENT_DEBUG] optimizer_final_rebalance_corridor "
                f"within_tolerance={final_corridor_status['within_tolerance']} "
                f"equity={final_corridor_status['equity_percent'] * 100:.4f} "
                f"fixed_income={final_corridor_status['fixed_income_percent'] * 100:.4f} "
                f"equity_value={final_corridor_status['equity_value']:.2f} "
                f"fixed_income_value={final_corridor_status['fixed_income_value']:.2f} "
                f"managed_total={final_corridor_status['managed_total']:.2f}"
            )
            if not final_corridor_status["within_tolerance"]:
                logger.warning(
                    "Final optimized portfolio remains outside Rebalance Category model corridor "
                    f"after rounding/cash balancing: equity={final_corridor_status['equity_percent']:.4%}, "
                    f"fixed_income={final_corridor_status['fixed_income_percent']:.4%}"
                )
        _print_rebalance_position_diagnostics("optimizer_final", bought_val, sold_val)

        # Loss-only post-solve enforcement REMOVED
        # Allow all solved trades to go through

        # ---------- Gains & taxes ----------
        realized_gains_per_lot = sold_val * gains_per_share
        realized_gains_short = float(np.sum(realized_gains_per_lot[~is_long_term]))
        realized_gains_long = float(np.sum(realized_gains_per_lot[is_long_term]))
        tax_per_lot = np.where(
            is_long_term, realized_gains_per_lot * long_term_rate, realized_gains_per_lot * short_term_rate
        )
        total_tax = realized_gains_short * short_term_rate + realized_gains_long * long_term_rate
        total_realized_gain = realized_gains_short + realized_gains_long

        cash_floor_tolerance = 0.01
        final_cash = float(np.sum(optimized_qty[cash_idxs] * current_prices[cash_idxs])) if cash_idxs.size else 0.0
        cash_shortfall = max(cash_floor - final_cash, 0.0)
        if cash_shortfall > cash_floor_tolerance:
            logger.error(
                "Post-processed trades do not satisfy cash target: "
                f"cash=${final_cash:,.2f}, floor=${cash_floor:,.2f}, shortfall=${cash_shortfall:,.2f}"
            )
            selected_budget_label = (
                "tax budget"
                if constraint_type == "tax_budget"
                else "realized gains limit"
                if constraint_type == "realized_gains"
                else "selected constraints"
            )
            raise RuntimeError(
                "Optimization cannot be completed.\n\n"
                "PROBLEM: The optimizer could not satisfy the mandatory cash target with the selected constraints.\n\n"
                "CAUSES:\n"
                f"  • The final proposed cash balance is ${final_cash:,.0f}, which is ${cash_shortfall:,.0f} below the required cash target of ${cash_floor:,.0f}.\n"
                f"  • The current {selected_budget_label} prevents enough additional selling to raise the required cash.\n\n"
                "SUGGESTIONS:\n"
                f"  • Increase the {selected_budget_label}, reduce the one-time cash raise, or choose a target allocation closer to current holdings.\n"
            )

        cash_ceiling_value = float(getattr(self, "_cash_ceiling_dollars", float("inf")))
        cash_excess = max(final_cash - cash_ceiling_value, 0.0)
        if cash_excess > cash_floor_tolerance:
            logger.error(
                "Post-processed trades exceed cash ceiling: "
                f"cash=${final_cash:,.2f}, ceiling=${cash_ceiling_value:,.2f}, excess=${cash_excess:,.2f}"
            )
            raise RuntimeError(
                "Optimization cannot be completed.\n\n"
                "PROBLEM: Whole-share rounding would leave too much uninvested cash after satisfying the target trades.\n\n"
                "CAUSES:\n"
                f"  • The final proposed cash balance is ${final_cash:,.0f}, which is ${cash_excess:,.0f} above the allowed cash ceiling of ${cash_ceiling_value:,.0f}.\n"
                "  • Returning this portfolio would violate the optimizer's cash-management constraint.\n\n"
                "SUGGESTIONS:\n"
                "  • Allow fractional trading for the affected buy, choose a target allocation closer to current holdings, or adjust the cash target.\n"
            )

        if constraint_type == "tax_budget" and total_tax > max_tax_bill + budget_violation_tolerance:
            logger.error(
                "Post-processed trades exceed tax budget: "
                f"tax=${total_tax:,.2f}, budget=${max_tax_bill:,.2f}"
            )
            raise RuntimeError(
                "Optimization cannot be completed.\n\n"
                "PROBLEM: The selected tax budget is below the amount required after rounding and cash balancing.\n\n"
                "CAUSES:\n"
                f"  • The current tax budget is ${max_tax_bill:,.0f}, but meeting the cash target after whole-share rounding would create approximately ${total_tax:,.0f} of tax liability.\n\n"
                "SUGGESTIONS:\n"
                f"  • Increase the tax budget to at least ${total_tax:,.0f}, or choose a target allocation closer to current holdings.\n"
            )

        if (
            constraint_type == "realized_gains"
            and realized_gains_constraint is not None
            and total_realized_gain > float(realized_gains_constraint) + budget_violation_tolerance
        ):
            logger.error(
                "Post-processed trades exceed realized gains limit: "
                f"gains=${total_realized_gain:,.2f}, limit=${float(realized_gains_constraint):,.2f}"
            )
            raise RuntimeError(
                "Optimization cannot be completed.\n\n"
                "PROBLEM: The selected realized gains limit is below the amount required after rounding and cash balancing.\n\n"
                "CAUSES:\n"
                f"  • The current realized gains limit is ${float(realized_gains_constraint):,.0f}, but meeting the cash target after whole-share rounding would realize approximately ${total_realized_gain:,.0f} of gains.\n\n"
                "SUGGESTIONS:\n"
                f"  • Increase the realized gains limit to at least ${total_realized_gain:,.0f}, or choose a target allocation closer to current holdings.\n"
            )

        # DEBUG: Final check of symbols before dataframe creation
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("=== FINAL CHECK (before dataframe) ===")
            for sym in sorted(set(symbols)):
                if sym == "CASH":
                    continue
                sym_indices = [i for i, s in enumerate(symbols) if s == sym]
                if sym_indices:
                    total_bought = sum(bought_val[idx] for idx in sym_indices)
                    total_sold = sum(sold_val[idx] for idx in sym_indices)
                    if abs(total_bought) > 0.01 or abs(total_sold) > 0.01:
                        logger.debug(f"{sym}: bought_val={total_bought:.2f}, sold_val={total_sold:.2f}")
            logger.debug("==========================================")

        # ---------- Output dataframe ----------
        portfolio = self.portfolio.with_columns([
            pl.Series("Current Price", current_prices),
            pl.Series("Optimized Quantity", optimized_qty),
            pl.Series("Shares Sold", sold_val),
            pl.Series("Shares Bought", bought_val),
            pl.Series("Final Market Value", optimized_qty * current_prices),
            pl.Series("Realized Gain", realized_gains_per_lot),
            pl.Series("Tax Paid Per Lot", tax_per_lot),
            pl.Series("Term", ["Long" if f else "Short" for f in is_long_term]),
        ])
        
        # Filter out unused buy lots (empty lots that were never used)
        # These are lots with: Lot Quantity = 0, Optimized Quantity = 0, no trades
        # Keep CASH even if unused (it's always needed for cash balance)
        portfolio = portfolio.filter(
            (pl.col("Symbol") == "CASH") |
            (pl.col("Lot Quantity") > 0) |  # Original lots are always kept
            (pl.col("Optimized Quantity") > 0) |  # Lots with final position
            (pl.col("Shares Bought") > 0.001) |  # Lots that had buys
            (pl.col("Shares Sold") > 0.001)  # Lots that had sells
        )

        # Build substitution map for tracking error calculation
        # Maps each symbol to its substitution target (for grouping)
        sub_map_for_te = {}
        if has_substitutions:
            _te_sub_col = self.portfolio.get_column("Substitution").to_list()
            for sym, sub in zip(symbols, _te_sub_col):
                if sub and sub != sym:  # True substitute
                    sub_map_for_te[sym] = sub

        tracking_error = float(self._calculate_tracking_error(
            optimized_qty, current_prices, symbols, target_values_static,
            substitution_map=sub_map_for_te
        ))
        adjusted_allocation = self.adjusted_target_allocation

        # Return values:
        # 1. portfolio
        # 2. max_tax_bill (the budget/constraint)
        # 3. total_tax (the actual tax used)
        # 4. realized_gains_short
        # 5. realized_gains_long
        # 6. total_realized_gain
        # 7. tracking_error
        # 8. adjusted_allocation
        return (
            portfolio,
            max_tax_bill,
            total_tax,
            realized_gains_short,
            realized_gains_long,
            total_realized_gain,
            tracking_error,
            adjusted_allocation,
        )







    def optimize_portfolio(self, short_term_rate, long_term_rate, max_tax_bill, realized_gains_constraint, legacy_mode=False, wash_sale=False, exclude_securities=None, trade_restrictions=None, constraint_type='none'):
        self._align_portfolio_with_target(exclude_securities, wash_sale=wash_sale)
        self._log_run_fingerprint(
            short_term_rate=short_term_rate,
            long_term_rate=long_term_rate,
            max_tax_bill=max_tax_bill,
            realized_gains_constraint=realized_gains_constraint,
            legacy_mode=legacy_mode,
            wash_sale=wash_sale,
            constraint_type=constraint_type,
            trade_restrictions=trade_restrictions or {},
        )
        optimized_portfolio, total_tax_budget, tax_budget, realized_gains_short_val, realized_gains_long_val, total_realize_gain, tracking_error, adjusted_allocation = self._optimize_portfolio(short_term_rate, long_term_rate, max_tax_bill=max_tax_bill, realized_gains_constraint=realized_gains_constraint, legacy_mode=legacy_mode, wash_sale=wash_sale, trade_restrictions=trade_restrictions, fractional=False, constraint_type=constraint_type)
        return optimized_portfolio, total_tax_budget, tax_budget, realized_gains_short_val, realized_gains_long_val, total_realize_gain, tracking_error, adjusted_allocation
    

    def get_asset_allocation_comparison_table(self, optimized_portfolio: pl.DataFrame) -> pl.DataFrame:
        # Defensive guard: asset allocation should reflect the managed sleeve only.
        # Excluded/unmanaged positions are captured separately for display/export and
        # must not affect the asset allocation comparison or model-assignment checks.
        excluded_symbols = {
            p.get('symbol') for p in getattr(self, '_excluded_unmanaged_positions', []) if p.get('symbol')
        }
        managed_portfolio = optimized_portfolio
        if excluded_symbols and "Symbol" in optimized_portfolio.columns:
            managed_portfolio = optimized_portfolio.filter(~pl.col("Symbol").is_in(list(excluded_symbols)))

        # Get current prices and optimized quantities from managed positions only
        current_prices = managed_portfolio["Current Price"].to_numpy()
        previous_quantities = managed_portfolio['Lot Quantity'].to_numpy()
        final_quantities = managed_portfolio["Optimized Quantity"].to_numpy()
        asset_classes = managed_portfolio["Asset Class"].fill_null("Unclassified").to_list()


        previous_values = previous_quantities * current_prices
        final_values = final_quantities * current_prices
        total_previous_value = previous_values.sum()
        total_value = final_values.sum()

        # --- Optimized allocation by asset class ---
        optimized_by_class = defaultdict(float)
        previous_by_class = defaultdict(float)

        for val, cls in zip(previous_values, asset_classes):
            previous_by_class[cls] += val
        previous_weights = {cls: val / total_previous_value for cls, val in previous_by_class.items()}

        for val, cls in zip(final_values, asset_classes):
            optimized_by_class[cls] += val
        optimized_weights = {cls: val / total_value for cls, val in optimized_by_class.items()}

        # --- Target allocation by asset class ---
        target_values = self.adjusted_target_allocation.select(["Symbol", "Target Weight"]).to_dict(as_series=False)
        symbol_to_class = dict(zip(self.portfolio["Symbol"], self.portfolio["Asset Class"].fill_null("Unclassified")))
        target_by_class = defaultdict(float)
        for sym, weight in zip(target_values["Symbol"], target_values["Target Weight"]):
            cls = symbol_to_class.get(sym, "Unclassified")
            target_by_class[cls] += weight
        target_weights = dict(target_by_class)
   

        # --- Build comparison table ---
        all_classes = set(target_weights.keys()) | set(optimized_weights.keys() | set(previous_weights.keys()))
        comparison_data = []
        for cls in sorted(all_classes):
            pre_wt = previous_weights.get(cls, 0.0)
            tgt_wt = target_weights.get(cls, 0.0)
            opt_wt = optimized_weights.get(cls, 0.0)
            comparison_data.append({
                "Asset Class": cls,
                "Current Weight": round(pre_wt * 100, 1),
                "Optimized Weight": round(opt_wt * 100, 1),
                "Target Weight": round(tgt_wt * 100, 1),
                "Difference": round(opt_wt - tgt_wt, 3) * 100
            })

        # Normalize Optimized Weight to sum to exactly 100% after rounding
        # This adjusts for rounding errors that can cause sum to be 99.9% or 100.1%
        opt_weight_sum = sum(d["Optimized Weight"] for d in comparison_data)
        if opt_weight_sum != 100.0 and opt_weight_sum > 0 and len(comparison_data) > 0:
            # Find the item with the largest optimized weight to apply the adjustment
            max_idx = max(range(len(comparison_data)), key=lambda i: comparison_data[i]["Optimized Weight"])
            adjustment = round(100.0 - opt_weight_sum, 1)
            comparison_data[max_idx]["Optimized Weight"] = round(comparison_data[max_idx]["Optimized Weight"] + adjustment, 1)

        return pl.DataFrame(comparison_data)
    
    def summarize_initial_vs_target(self, optimized_portfolio: pl.DataFrame) -> pl.DataFrame:

        # Aggregate current and optimized values by symbol
        symbol_totals = (
            optimized_portfolio.group_by("Symbol")
            .agg([
                (pl.col("Lot Quantity") * pl.col("Current Price")).sum().alias("Current Value"),
                pl.col("Final Market Value").sum().alias("Optimized Value")
            ])
            .sort("Symbol")
        )

        # Compute total portfolio values
        total_current_value = symbol_totals["Current Value"].sum()
        total_optimized_value = symbol_totals["Optimized Value"].sum()

        # Compute weights
        symbol_totals = symbol_totals.with_columns([
            (pl.col("Current Value") / total_current_value).alias("Current Weight"),
            (pl.col("Optimized Value") / total_optimized_value).alias("Optimized Weight")
        ])

        # Join with target allocation on symbol
        symbol_totals = symbol_totals.join(
            self.adjusted_target_allocation.select(["Symbol", "Target Weight"]),
            on="Symbol",
            how="left"
        )

        symbol_totals = symbol_totals.with_columns([
            pl.col('Target Weight').fill_null(0)
        ])

        symbol_totals = symbol_totals.with_columns([
            ((pl.col("Target Weight") - pl.col("Optimized Weight")).round(3) * 100 ).alias("Deviation (%)")
        ])

        symbol_totals = symbol_totals.with_columns([
            (pl.col("Current Weight") * 100).round(1).alias("Current Weight"),
            (pl.col("Optimized Weight") * 100).round(1).alias("Optimized Weight"),
            (pl.col("Target Weight") * 100).round(1).alias("Target Weight")
        ])

        # Normalize Optimized Weight to sum to exactly 100% after rounding
        # This adjusts for rounding errors that can cause sum to be 99.9% or 100.1%
        opt_weight_sum = symbol_totals["Optimized Weight"].sum()
        if opt_weight_sum != 100.0 and opt_weight_sum > 0:
            # Find the row with the largest optimized weight to apply the adjustment
            max_opt_weight = symbol_totals["Optimized Weight"].max()
            adjustment = 100.0 - opt_weight_sum
            symbol_totals = symbol_totals.with_columns([
                pl.when(pl.col("Optimized Weight") == max_opt_weight)
                .then(pl.col("Optimized Weight") + adjustment)
                .otherwise(pl.col("Optimized Weight"))
                .alias("Optimized Weight")
            ])

        # Final formatting
        return symbol_totals.select(["Symbol", "Current Weight", "Optimized Weight", "Target Weight", "Deviation (%)"]).sort("Symbol")
    
    def _calculate_tracking_error(self, optimized_qty, current_prices, symbols, target_values, substitution_map=None):
        """Calculate tracking error between optimized portfolio and target allocation.
        
        Tracking error is the sum of absolute weight deviations at the symbol level.
        Lots are aggregated by symbol before computing weights.
        
        When substitution_map is provided, substitute securities are grouped with
        their substitution target for both actual and target weight calculations.
        E.g., if ITOT→VTI, ITOT's actual value is added to VTI's bucket.
        """
        
        # Calculate total portfolio value
        total_portfolio_value = np.sum(optimized_qty * current_prices)
        
        if total_portfolio_value == 0:
            return 0.0
        
        # Aggregate actual values by effective symbol (grouping substitutes with targets)
        actual_values_by_sym = {}
        for i, symbol in enumerate(symbols):
            actual_value = optimized_qty[i] * current_prices[i]
            # Group substitute value under its target symbol
            effective_sym = substitution_map.get(symbol, symbol) if substitution_map else symbol
            actual_values_by_sym[effective_sym] = actual_values_by_sym.get(effective_sym, 0.0) + actual_value
        
        # Convert to weights
        actual_weights = {sym: val / total_portfolio_value for sym, val in actual_values_by_sym.items()}
        
        # Calculate target weights (normalized), also grouping by effective symbol
        total_target_value = sum(target_values.values())
        target_values_grouped = {}
        if total_target_value > 0:
            for symbol, value in target_values.items():
                effective_sym = substitution_map.get(symbol, symbol) if substitution_map else symbol
                target_values_grouped[effective_sym] = target_values_grouped.get(effective_sym, 0.0) + value
        
        target_weights = {sym: val / total_target_value for sym, val in target_values_grouped.items()} if target_values_grouped else {}
        
        # Calculate tracking error as sum of absolute deviations
        tracking_error = 0.0
        all_symbols = set(actual_weights.keys()) | set(target_weights.keys())
        
        for symbol in all_symbols:
            actual_weight = actual_weights.get(symbol, 0.0)
            target_weight = target_weights.get(symbol, 0.0)
            tracking_error += abs(actual_weight - target_weight)
        
        return tracking_error
    
    def summarize_allocation_vs_target(self, optimized_portfolio):

        symbol_totals = (
            optimized_portfolio.group_by("Symbol")
            .agg(pl.col("Final Market Value").sum().alias("Optimized Value"))
            .sort("Symbol")
        )


        total_value = symbol_totals["Optimized Value"].sum()
        symbol_totals = symbol_totals.with_columns([
            (pl.col("Optimized Value") / total_value).alias("Optimized Weight")
        ])

        comparison = symbol_totals.join(self.adjusted_target_allocation, on="Symbol", how="left")

        comparison = comparison.with_columns([
            pl.col("Target Weight").fill_null(0)
        ])

        comparison = comparison.with_columns([
            (pl.col("Optimized Weight") - pl.col("Target Weight")).abs().alias("Deviation")
        ])


        return comparison.sort("Optimized Weight", descending=True)

    def generate_trade_orders(self, optimized_portfolio: pl.DataFrame) -> pl.DataFrame:

        # --- Sell orders ---
        sell_orders = (
            optimized_portfolio
            .filter(pl.col("Shares Sold") > 0)
            .select([
                "Symbol",
                pl.col("Shares Sold").cast(float).alias("Shares"),
                pl.lit("SELL").alias("Action"),
            pl.col("Lot Cost Basis"),
            pl.col("Date"),
            pl.col("Current Price"),
            pl.col("Realized Gain").round(2),
            pl.col("Term")
        ])
    )

    # --- Buy orders ---
        buy_orders = (
            optimized_portfolio
            .filter(pl.col("Shares Bought") > 0)
            .select([
                "Symbol",
                pl.col("Shares Bought").cast(float).alias("Shares"),
                pl.lit("BUY").alias("Action"),
                pl.lit(None).alias("Lot Cost Basis"),
                pl.lit(None).alias("Date"),
                pl.col("Current Price"),
                pl.lit(None).alias("Realized Gain"),
                pl.lit(None).alias("Term")
            ])
        )

        # --- Combine both ---
        orders = pl.concat([sell_orders, buy_orders], how="vertical").sort(["Symbol", "Action"])

        return orders

    def generate_trade_orders_condensed(self,optimized_portfolio: pl.DataFrame) -> pl.DataFrame:
        # Check if Target Symbol and Original Security Name columns exist (from security substitution)
        has_substitutions = 'Target Symbol' in optimized_portfolio.columns
        has_original_security_name = 'Original Security Name' in optimized_portfolio.columns
        
        # Build aggregation expressions for sell orders
        sell_agg_exprs = [
            pl.sum("Shares").alias('Shares'),
            (pl.sum('Weighted Cost') / pl.sum('Shares')).alias('Lot Cost Basis'),
            pl.first('Current Price'),
            pl.first('Security Description').alias('Security Description'),
            pl.sum("Realized Gain").alias("Realized Gain"),
            pl.sum("Tax Paid Per Lot").alias("Taxes Paid"),
            pl.sum("Short Term Realized Gain").alias("Short Term Gains"),
            pl.sum("Long Term Realized Gain").alias("Long Term Gains"),
        ]
        
        if has_substitutions:
            sell_agg_exprs.append(pl.first("Target Symbol").alias("Target Symbol"))
        if has_original_security_name:
            sell_agg_exprs.append(pl.first("Original Security Name").alias("Original Security Name"))
        
        sell_orders = (
            optimized_portfolio
            .filter(pl.col("Shares Sold") > 0)
            .with_columns([
                pl.col("Shares Sold").cast(float).alias('Shares'),
                (pl.col('Shares Sold') * pl.col('Lot Cost Basis')).alias('Weighted Cost'),
                # Calculate short-term and long-term gains separately
                pl.when(pl.col("Term") == "Short")
                .then(pl.col("Realized Gain"))
                .otherwise(0.0)
                .alias("Short Term Realized Gain"),
                pl.when(pl.col("Term") == "Long")
                .then(pl.col("Realized Gain"))
                .otherwise(0.0)
                .alias("Long Term Realized Gain"),
            ])
            .group_by(['Symbol']) # Remove Term
            .agg(sell_agg_exprs)
            .with_columns([
                pl.lit("SELL").alias("Action")
            ])
        )
        
        # Build select columns for sell orders
        sell_select_cols = [
            "Symbol", "Security Description", "Action", "Shares", "Lot Cost Basis", "Current Price", 
            "Realized Gain", "Taxes Paid", "Short Term Gains", "Long Term Gains"
        ]
        if has_substitutions:
            sell_select_cols.append("Target Symbol")
        if has_original_security_name:
            sell_select_cols.append("Original Security Name")
        
        sell_orders = sell_orders.select(sell_select_cols)
        
        # Build aggregation expressions for buy orders
        buy_agg_exprs = [
            pl.sum("Shares Bought").cast(float).alias("Shares"),
            pl.first("Current Price"),
            pl.first('Security Description').alias('Security Description'),
        ]
        
        if has_substitutions:
            buy_agg_exprs.append(pl.first("Target Symbol").alias("Target Symbol"))
        if has_original_security_name:
            buy_agg_exprs.append(pl.first("Original Security Name").alias("Original Security Name"))

        buy_orders = (
            optimized_portfolio
            .filter(pl.col("Shares Bought") > 0)
            .group_by("Symbol")
            .agg(buy_agg_exprs)
            .with_columns([
                pl.lit("BUY").alias("Action"),
                pl.lit(None).alias("Lot Cost Basis"),
                pl.lit(None).alias("Realized Gain"),
                pl.lit(None).alias("Taxes Paid"),
                pl.lit(0.0).alias("Short Term Gains"),
                pl.lit(0.0).alias("Long Term Gains"),
            ])
        )
        
        # Build select columns for buy orders
        buy_select_cols = [
            "Symbol", "Security Description", "Action", "Shares", "Lot Cost Basis", "Current Price", 
            "Realized Gain", "Taxes Paid", "Short Term Gains", "Long Term Gains"
        ]
        if has_substitutions:
            buy_select_cols.append("Target Symbol")
        if has_original_security_name:
            buy_select_cols.append("Original Security Name")
        
        buy_orders = buy_orders.select(buy_select_cols)

        orders = pl.concat([sell_orders, buy_orders], how='vertical').sort(['Symbol','Action'])

        return orders
    
   
