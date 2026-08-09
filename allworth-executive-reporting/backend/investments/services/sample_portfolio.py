"""Sample bond portfolio generator.

Selects real bonds from the Allworth bond-ladder universe (see the query in
docs/Sample_Bond_Portfolio_Generator_Spec.md) and sizes them into a laddered
sample portfolio that mirrors a named strategy, then computes the fact-sheet
metrics via :mod:`app.services.portfolio_metrics`.

Pipeline:
    load_universe(session) -> filter by strategy -> ladder selection ->
    even sizing -> weight optimization -> metric computation

The selection/optimization functions are pure and accept an in-memory bond list
so they can be unit-tested without a database.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from investments.models.bond import Bond, CreditRating, rating_rank
from investments.services import portfolio_metrics as metrics
from investments.services.db_analyzer import (
    SECURITY_COLUMN_CANDIDATES,
    SECURITY_TABLE_CANDIDATES,
    _build_select_clause,
    _custodian_join_and_reinvestment_filter,
    _first_existing_column,
    _resolve_table_source,
    _to_bool,
    _to_date,
    _to_float,
)


# ---------------------------------------------------------------------------
# Strategy configuration
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Strategy:
    key: str
    label: str
    asset: str  # "municipal" | "treasury" | "corporate"
    tax_exempt: bool
    min_year: int
    max_year: int
    bonds_per_year: int
    # Fact-sheet reference targets used by the optimizer (percent / notch label).
    target_ytw: float
    target_rating: str
    description: str

    @property
    def target_count(self) -> int:
        return self.bonds_per_year * (self.max_year - self.min_year + 1)


_DESC = {
    "municipal": (
        "This investment strategy aims to generate income by focusing primarily on "
        "investment-grade municipal securities, structured in a laddered portfolio with "
        "staggered maturities. As each bond matures, it is typically replaced by a new bond "
        "with the longest maturity within the strategy's defined range."
    ),
    "treasury": (
        "This investment strategy aims to generate income by focusing primarily on "
        "investment-grade Treasurys, structured in a laddered portfolio with staggered "
        "maturities. As each bond matures, it is typically replaced by a new bond with the "
        "longest maturity within the strategy's defined range."
    ),
    "corporate": (
        "This investment strategy aims to generate income by focusing primarily on "
        "investment-grade corporate securities, structured in a laddered portfolio with "
        "staggered maturities. As each bond matures, it is typically replaced by a new bond "
        "with the longest maturity within the strategy's defined range."
    ),
}


def _mk(key, label, asset, tax_exempt, max_year, per_year, ytw, rating) -> Strategy:
    return Strategy(
        key=key,
        label=label,
        asset=asset,
        tax_exempt=tax_exempt,
        min_year=1,
        max_year=max_year,
        bonds_per_year=per_year,
        target_ytw=ytw,
        target_rating=rating,
        description=_DESC[asset],
    )


STRATEGIES: dict[str, Strategy] = {
    s.key: s
    for s in [
        _mk("municipal-1-5", "1-5 Year Municipal Bond Ladder", "municipal", True, 5, 3, 2.777, "A1"),
        _mk("municipal-1-10", "1-10 Year Municipal Bond Ladder", "municipal", True, 10, 2, 2.9, "A1"),
        _mk("treasury-1-5", "1-5 Year Treasury Bond Ladder", "treasury", False, 5, 1, 4.121, "Aa1"),
        _mk("treasury-1-10", "1-10 Year Treasury Bond Ladder", "treasury", False, 10, 1, 4.2, "Aa1"),
        _mk("corporate-1-5", "1-5 Year Corporate Bond Ladder", "corporate", False, 5, 3, 4.429, "A3"),
        _mk("corporate-1-10", "1-10 Year Corporate Bond Ladder", "corporate", False, 10, 2, 4.6, "A3"),
    ]
}

DEFAULT_TARGET_VALUE = 1_000_000.0


# ---------------------------------------------------------------------------
# Universe loading (DataWarehouse)
# ---------------------------------------------------------------------------

def load_universe(session: Session) -> list[Bond]:
    """Load the eligible bond universe from the DataWarehouse.

    Mirrors the spec query: distinct symbols held in bond-ladder accounts, then
    the full security master row for each, mapped to canonical Bonds.
    """
    security_source = _resolve_table_source(session, SECURITY_TABLE_CANDIDATES)
    symbol_col = _first_existing_column(security_source.columns, SECURITY_COLUMN_CANDIDATES["Symbol"])
    if not symbol_col:
        raise RuntimeError(f"Could not find a Symbol column in {security_source.ref}.")

    symbols = _load_ladder_symbols(session)
    if not symbols:
        return []

    select_clause = _build_select_clause(SECURITY_COLUMN_CANDIDATES, security_source.columns)
    stmt = (
        text(
            f"SELECT {select_clause} "
            f"FROM {security_source.ref} "
            f"WHERE [{symbol_col}] IN :symbols"
        )
        .bindparams(bindparam("symbols", expanding=True))
    )
    rows = session.execute(stmt, {"symbols": symbols}).mappings().all()
    return [_security_to_bond(dict(row)) for row in rows]


def _load_ladder_symbols(session: Session) -> list[str]:
    """Distinct fixed-income symbols held in accounts flagged Bond_Ladder = 'Yes'."""
    holdings = _resolve_table_source(session, [("tav", "Account_Daily_Holdings"), ("tho", "Account_Daily_Holdings")])
    custodian_join, reinvestment_filter = _custodian_join_and_reinvestment_filter(
        session,
        holdings,
        holdings_alias="h",
        custodian_alias="c",
    )

    stmt = text(
        f"SELECT DISTINCT h.[Symbol] AS Symbol "
        f"FROM {holdings.ref} AS h "
        f"{custodian_join} "
        f"WHERE c.[Bond_Ladder] = 'Yes' "
        f"AND h.[Security_Type] = 'Fixed Income' "
        f"{reinvestment_filter}"
    )
    rows = session.execute(stmt).mappings().all()
    return sorted({str(r.get("Symbol") or "").strip() for r in rows if r.get("Symbol")})


# Trailing coupon + maturity/description noise that follows the issuer name in a
# security description, e.g. "Abilene Tex Indpt Sch Dist 5.000 02/15/29" -> the
# issuer is everything before the coupon. ``tav.Security_Info`` has no Issuer
# column, so the issuer key (Rule 11: one bond per issuer) is derived from text.
_ISSUER_COUPON_RE = re.compile(r"\s+\d+(?:\.\d+)?\s*%?\s+\d{1,2}[/-]\d{1,2}[/-]\d{2,4}.*$")
_ISSUER_COUPON_ONLY_RE = re.compile(r"\s+\d+\.\d+.*$")
_ISSUER_DATE_RE = re.compile(r"\s+\d{1,2}[/-]\d{1,2}[/-]\d{2,4}.*$")
_BARE_CUSIP_RE = re.compile(r"^[A-Z0-9]{8,9}$")


def _derive_issuer(description: str | None, cusip: str | None = None) -> str | None:
    """Derive a normalised issuer key from a security description.

    The security master exposes no ``Issuer`` column, so issuer uniqueness is
    approximated from the leading text of the description (the portion before
    the coupon/maturity).  When the description is effectively a bare CUSIP the
    6-character CUSIP issuer prefix is used instead.
    """
    cusip_prefix = (str(cusip).strip()[:6].upper() or None) if cusip else None
    if not description:
        return cusip_prefix
    blob = " ".join(str(description).split())
    if _BARE_CUSIP_RE.match(blob.upper()):
        return cusip_prefix or blob.upper()[:6]
    trimmed = _ISSUER_COUPON_RE.sub("", blob)
    if trimmed == blob:  # no coupon+date pattern; strip a lone coupon or date
        trimmed = _ISSUER_COUPON_ONLY_RE.sub("", trimmed)
        trimmed = _ISSUER_DATE_RE.sub("", trimmed)
    key = trimmed.strip(" ,-").upper()
    if len(key) < 3:
        return cusip_prefix or (key or None)
    return key


def _security_to_bond(security: dict) -> Bond:
    """Map a security-master row (no holding) to a canonical Bond.

    Fitch is the primary rating source; Moody's is added as a fallback when
    Fitch is absent so that ``bond.best_rating`` always has something to work
    with even for securities not yet rated by Fitch.
    """
    ratings: list[CreditRating] = []
    if security.get("Fitch_Rating"):
        ratings.append(
            CreditRating(
                agency="Fitch",
                current=security.get("Fitch_Rating"),
                previous=security.get("Previous_Fitch_Rating"),
                effective_date=_to_date(security.get("Fitch_Effective_Date")),
                previous_effective_date=_to_date(security.get("Previous_Fitch_Effective_Date")),
            )
        )
    elif security.get("Moodys_Rating"):  # fallback only when Fitch absent
        ratings.append(CreditRating(agency="Moody's", current=security.get("Moodys_Rating")))

    call_date = _to_date(security.get("Call_Date"))
    return Bond(
        symbol=security.get("Symbol"),
        cusip=security.get("CUSIP"),
        description=security.get("Security_Description") or "Unknown Security",
        coupon=_to_float(security.get("Interest_Rate")),
        price=_to_float(security.get("Current_Price")),
        yield_to_worst=_to_float(security.get("Current_Yield_to_Worst")),
        effective_duration=_to_float(security.get("Effective_Duration")),
        issue_date=_to_date(security.get("Issue_Date")),
        maturity_date=_to_date(security.get("Maturity_Date")),
        first_coupon_date=_to_date(security.get("First_Coupon_Date")),
        call_date=call_date,
        callable=call_date is not None or str(security.get("Call_Put") or "").strip().upper() == "CALL",
        call_price=_to_float(security.get("Call_Price")),
        ratings=ratings,
        asset_class="Fixed Income",
        sector=security.get("Sector"),
        broad_sector=security.get("Broad_Sector"),
        segment=security.get("Segment"),
        issuer=security.get("Issuer") or _derive_issuer(
            security.get("Security_Description"), security.get("CUSIP")
        ),
        state=security.get("Issue_State"),
        income_frequency=security.get("Income_Frequency"),
        next_income_date=_to_date(security.get("Next_Income_Date")),
        federal_taxable=_to_bool(security.get("Federal_Taxable")),
        state_taxable=_to_bool(security.get("State_Taxable")),
    )


# ---------------------------------------------------------------------------
# Strategy filtering
# ---------------------------------------------------------------------------

_TREASURY_HINTS = ("treasury", "u.s. treasury", "us treasury", "govt", "government", "t-note", "t-bond")
_MUNI_HINTS = ("muni", "municipal", "state of", "county", "city of", "school", "authority")

# Text signals used to classify municipals when no structural flag exists.
# GO: general-obligation / unlimited- or limited-tax / school-district issues.
_MUNI_GO_RE = re.compile(
    r"\bg\.?\s?o\.?\b|\bg/o\b|\bgo\s+b|general\s+oblig|\bunltd\b|\bunlimited\b"
    r"|\bltd\s+tax\b|\blimited\s+tax\b|sch\s+dist|school\s+dist|uni\s+sch"
)
# Revenue bonds / certificates of participation are excluded (GO-only ladders).
_MUNI_REVENUE_RE = re.compile(r"\brev\b|revenue|\bctfs\b|certificates?\s+of\s+part|\bcops?\b")
# Alternative Minimum Tax issues are excluded.
_MUNI_AMT_RE = re.compile(r"\bamt\b|alternative\s+min|alt\s+min")


def _asset_matches(bond: Bond, asset: str) -> bool:
    text_blob = f"{bond.sector or ''} {bond.description or ''} {bond.issuer or ''}".lower()
    if asset == "treasury":
        return any(h in text_blob for h in _TREASURY_HINTS)
    if asset == "municipal":
        return metrics._is_tax_exempt(bond) or any(h in text_blob for h in _MUNI_HINTS)
    if asset == "corporate":
        is_treasury = any(h in text_blob for h in _TREASURY_HINTS)
        is_muni = metrics._is_tax_exempt(bond) or any(h in text_blob for h in _MUNI_HINTS)
        return not is_treasury and not is_muni
    return False


def filter_candidates(
    universe: list[Bond],
    strategy: Strategy,
    as_of: date,
    *,
    exclude_unrated: bool = True,
    state: str | None = None,
) -> list[Bond]:
    """Filter the universe down to bonds eligible for this strategy.

    Credit-rating handling: ``tav.Security_Info`` carries only Fitch, and most
    municipals are Fitch-``NR``.  When a Fitch rating *exists* it is enforced
    (A- or better across every agency present).  Bonds with **no** rating are
    governed by ``exclude_unrated``: when ``False`` (the default from the API)
    they are kept and surfaced downstream as "Not rated" so a ladder can still
    be built from inventory that the source data does not rate.
    """
    candidates: list[Bond] = []
    for bond in universe:
        if bond.price is None or bond.price <= 0 or not bond.maturity_date:
            continue
        if bond.maturity_date < as_of:
            continue
        if bond.callable:
            continue
        if not bond.coupon or bond.coupon <= 0:
            continue
        # Credit-rating screen. Only enforce the A- minimum when the source
        # actually rates the bond; when no rating is present, defer to
        # ``exclude_unrated`` rather than dropping for missing data.
        if rating_rank(bond.best_rating) is None:
            if exclude_unrated:
                continue
        else:
            if bond.is_investment_grade is False:
                continue
            if not _meets_min_rating_all_agencies(bond, "A-"):
                continue
        years = metrics.years_to_maturity(bond, as_of)
        if years is None or years < strategy.min_year - 0.5 or years > strategy.max_year + 0.5:
            continue
        if not _asset_matches(bond, strategy.asset):
            continue
        if strategy.asset == "municipal" and not _eligible_muni(bond):
            continue
        if strategy.asset == "municipal" and state:
            state_key = state.strip().upper()
            bond_state = (bond.state or "").strip().upper()
            national = bond_state in {"", "US", "USA", "NATIONAL", "MULTI", "MULTI STATE"}
            if bond_state != state_key and not national:
                continue
        if strategy.asset == "corporate" and bond.price < 95:
            continue
        candidates.append(bond)
    return candidates


def _meets_min_rating_all_agencies(bond: Bond, minimum: str) -> bool:
    min_rank = rating_rank(minimum)
    if min_rank is None or not bond.ratings:
        return False
    for rating in bond.ratings:
        rank = rating_rank(rating.current)
        if rank is None or rank > min_rank:
            return False
    return True


def _eligible_muni(bond: Bond) -> bool:
    """Best-effort municipal eligibility (Rules 5, 9, 12).

    ``tav.Security_Info`` carries no structural GO/Revenue or AMT flag, so
    those attributes are inferred from the free-text ``Security_Description``.
    This is approximate and will misclassify some issues; it errs toward
    exclusion (an issue is only kept when a GO signal is present and no
    revenue/AMT/taxable signal is found).
    """
    text = f"{bond.description or ''} {bond.sector or ''} {bond.broad_sector or ''} {bond.segment or ''}".lower()
    # Rule 9: municipals must not be bought below par.
    if bond.price is None or bond.price < 100:
        return False
    # Rule 12: no taxable issues, no AMT bonds.
    if bond.federal_taxable is True:
        return False
    if "taxable" in text or _MUNI_AMT_RE.search(text):
        return False
    # Rule 5: GO only — exclude revenue bonds / certificates of participation.
    if _MUNI_REVENUE_RE.search(text):
        return False
    if _MUNI_GO_RE.search(text):
        return True
    return False


# ---------------------------------------------------------------------------
# Ladder selection
# ---------------------------------------------------------------------------

def _selection_score(bond: Bond, target_rank: int, y_min: float, y_span: float) -> float:
    y = bond.yield_to_worst if bond.yield_to_worst is not None else 0.0
    y_norm = (y - y_min) / y_span if y_span > 0 else 0.0
    rank = rating_rank(bond.best_rating)
    rank_pen = abs((rank if rank is not None else target_rank) - target_rank)
    call_pen = 1.0 if bond.callable else 0.0
    coupon_match = _clamp(1.0 - abs((bond.coupon or 0.0) - y) / max(abs(y), 1.0))
    return 1.0 * y_norm + 0.12 * coupon_match - 0.15 * rank_pen - 0.10 * call_pen


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def _price_quality(price: float | None, callable_: bool) -> float:
    if price is None or price <= 0:
        return 0.50
    # Corporate ladders usually look cleaner near par. Deep discounts can imply
    # credit stress, while callable premium bonds carry reinvestment risk.
    distance = abs(price - 100.0)
    score = _clamp(1.0 - distance / 25.0)
    if callable_ and price > 103:
        score -= min(0.25, (price - 103.0) / 40.0)
    return _clamp(score)


def corporate_quality_score(bond: Bond, target_rank: float) -> tuple[float, dict[str, float]]:
    """Return a 0-100 quality score for corporate bond selection.

    The score intentionally favours company/credit quality over raw yield:
    35% current Fitch rating, 20% rating momentum, 15% rating-adjusted YTW,
    10% price quality, 10% call risk, and 10% metadata confidence.
    """
    rank = rating_rank(bond.best_rating)
    ig_worst = rating_rank("Baa3") or 9
    rank_value = float(rank if rank is not None else target_rank)
    credit = _clamp(1.0 - rank_value / (ig_worst + 1.0))

    momentum = 0.75
    for rating in bond.ratings:
        current_rank = rating_rank(rating.current)
        previous_rank = rating_rank(rating.previous)
        if current_rank is None or previous_rank is None:
            continue
        if current_rank < previous_rank:
            momentum = 1.0
        elif current_rank > previous_rank:
            momentum = 0.20
        else:
            momentum = 0.85
        break

    ytw = bond.yield_to_worst or 0.0
    duration = max(0.25, bond.effective_duration or 0.25)
    # Reward income only after adjusting for duration and rating risk. The cap
    # keeps a distressed-looking yield from overwhelming credit quality.
    risk_adjusted_yield = _clamp((ytw / duration) / (rank_value + 1.0) / 0.35)

    price = _price_quality(bond.price, bond.callable)
    call = 0.65 if bond.callable else 1.0
    coupon_match = _clamp(
        1.0 - abs((bond.coupon or 0.0) - (bond.yield_to_worst or 0.0)) / max(abs(bond.yield_to_worst or 0.0), 1.0)
    )

    metadata = 0.60
    if bond.broad_sector or bond.segment:
        metadata += 0.25
    if bond.issuer:
        metadata += 0.15
    metadata = _clamp(metadata)

    components = {
        "credit": round(credit * 100, 1),
        "momentum": round(momentum * 100, 1),
        "risk_adjusted_yield": round(risk_adjusted_yield * 100, 1),
        "price": round(price * 100, 1),
        "call": round(call * 100, 1),
        "coupon_match": round(coupon_match * 100, 1),
        "metadata": round(metadata * 100, 1),
    }
    score = (
        0.35 * credit
        + 0.20 * momentum
        + 0.15 * risk_adjusted_yield
        + 0.10 * price
        + 0.10 * call
        + 0.05 * coupon_match
        + 0.05 * metadata
    ) * 100
    return round(score, 1), components


def select_ladder(
    candidates: list[Bond],
    strategy: Strategy,
    as_of: date,
    *,
    state: str | None = None,
) -> list[Bond]:
    """Pick the top-scoring bonds per maturity-year rung with geographic diversity.

    Within each rung candidates are ranked by :func:`_selection_score`.  Before
    adding a bond to the selection the builder checks how many bonds from that
    state are already chosen across the *entire* ladder.  A candidate whose
    state is already at the per-state cap is skipped in favour of the next-best
    bond from a different state, ensuring the portfolio is geographically
    diversified by construction rather than as a post-hoc optimiser nudge.

    The per-state cap is ``max(1, bonds_per_year)``, i.e. no state may supply
    more than one bond per strategy year.  When the rung is so thin that every
    remaining candidate is from a capped state the cap is relaxed and the
    best-available bond is taken instead (ladder completeness trumps diversity).
    """
    target_rank = rating_rank(strategy.target_rating) or 4
    # State concentration is only a national-muni rule. Single-state muni
    # ladders deliberately allow the requested state, supplemented by national
    # inventory when needed.
    per_state_cap = 2 if strategy.asset == "municipal" and not state else strategy.target_count
    max_financial = strategy.target_count // 2 if strategy.asset == "corporate" else strategy.target_count
    rungs: dict[int, list[Bond]] = {y: [] for y in range(strategy.min_year, strategy.max_year + 1)}
    for bond in candidates:
        years = metrics.years_to_maturity(bond, as_of) or 0.0
        rung = min(strategy.max_year, max(strategy.min_year, round(years)))
        rungs[rung].append(bond)

    selected: list[Bond] = []
    state_counts: dict[str, int] = {}  # tracks state usage across the whole ladder
    issuer_counts: dict[str, int] = {}
    financial_count = 0

    for _year, bucket in sorted(rungs.items()):
        if not bucket:
            continue
        yields = [b.yield_to_worst for b in bucket if b.yield_to_worst is not None]
        y_min = min(yields) if yields else 0.0
        y_span = (max(yields) - y_min) if yields else 0.0
        if strategy.asset == "corporate":
            for bond in bucket:
                score, components = corporate_quality_score(bond, float(target_rank))
                bond.corporate_quality_score = score
                bond.corporate_quality_components = components
            bucket.sort(key=lambda b: b.corporate_quality_score or 0.0, reverse=True)
        else:
            bucket.sort(key=lambda b: _selection_score(b, target_rank, y_min, y_span), reverse=True)

        rung_picks: list[Bond] = []
        for bond in bucket:
            if len(rung_picks) >= strategy.bonds_per_year:
                break
            state_key = (bond.state or "Unknown").upper().strip()
            issuer_key = (bond.issuer or bond.description or bond.cusip or "").upper().strip()
            is_financial = "financial" in f"{bond.sector or ''} {bond.broad_sector or ''} {bond.segment or ''}".lower()
            if strategy.asset != "treasury" and issuer_key and issuer_counts.get(issuer_key, 0) > 0:
                continue
            if is_financial and financial_count >= max_financial:
                continue
            if state_counts.get(state_key, 0) < per_state_cap:
                rung_picks.append(bond)
                state_counts[state_key] = state_counts.get(state_key, 0) + 1
                if issuer_key:
                    issuer_counts[issuer_key] = issuer_counts.get(issuer_key, 0) + 1
                if is_financial:
                    financial_count += 1

        # Fallback: relax only state/sector caps. Issuer uniqueness remains a
        # hard ladder rule.
        if not rung_picks:
            for bond in bucket:
                if len(rung_picks) >= strategy.bonds_per_year:
                    break
                state_key = (bond.state or "Unknown").upper().strip()
                issuer_key = (bond.issuer or bond.description or bond.cusip or "").upper().strip()
                if strategy.asset != "treasury" and issuer_key and issuer_counts.get(issuer_key, 0) > 0:
                    continue
                rung_picks.append(bond)
                state_counts[state_key] = state_counts.get(state_key, 0) + 1
                if issuer_key:
                    issuer_counts[issuer_key] = issuer_counts.get(issuer_key, 0) + 1

        selected.extend(rung_picks)
    return selected


# ---------------------------------------------------------------------------
# Quality-based position sizing
# ---------------------------------------------------------------------------

def _quality_weights(
    bonds: list[Bond],
    as_of: date,
    target_ytw: float,
    target_rank: float,
    *,
    min_weight_pct: float = 0.50,
) -> list[float]:
    """Compute market-value weights directly from per-bond quality scores.

    **Algorithm**

    For every bond compute a composite quality score from four metrics,
    each already available on the canonical Bond model:

    1. **YTW premium** (40 %) — how much the bond's YTW exceeds the
       strategy target.  A bond yielding more than the target scores higher;
       one below target still scores positively (it contributes income).

    2. **Credit efficiency** (30 %) — YTW earned *per unit of credit risk*,
       expressed as yield ÷ (Fitch rating rank + 1).  A bond rated AA that
       yields 4.5 % scores better than a BBB bond at the same yield because
       it delivers more return for less risk.

    3. **Income density** (20 %) — annual coupon ÷ price.  Bonds trading at
       a discount are rewarded for their higher running yield per dollar of
       cost.

    4. **Maturity spacing** (10 %) — how close the bond's maturity is to the
       centre of its ladder rung (penalises clustering at the near/far edges
       of the rung, which creates reinvestment bunching).

    Each signal is normalised to [0, 1] across the selected bond pool.
    The composite score is then converted to a weight:

    .. code-block:: text

        raw_weight_i = composite_score_i
        weight_i     = max(raw_weight_i, min_floor)   ← prevent collapse
        weight_i     = weight_i / Σ weight_j          ← normalise to sum = 1

    ``min_floor = min_weight_pct × (1/N)`` guarantees every selected bond
    receives at least half its even-split share, so a 15-bond portfolio never
    has positions below ~3.3 % regardless of relative quality differences.

    This is deterministic, O(N), and requires no iterative solver.
    Portfolio-level YTW and average credit quality mirror the fact-sheet
    targets closely because the *selection* step already restricts the
    candidate pool to bonds near those targets; sizing only tilts within
    the pool.
    """
    n = len(bonds)
    if n == 0:
        return []
    even = 1.0 / n
    min_floor = min_weight_pct * even

    ytw_vals = [b.yield_to_worst or 0.0 for b in bonds]
    ranks = [
        float(rating_rank(b.best_rating)) if rating_rank(b.best_rating) is not None else target_rank
        for b in bonds
    ]

    # ── 1. YTW premium ───────────────────────────────────────────────────────
    ytw_premium = [max(0.0, y - target_ytw + target_ytw) for y in ytw_vals]  # all positive

    # ── 2. Credit efficiency: yield / (rank + 1)  ────────────────────────────
    credit_eff = [ytw_vals[i] / (ranks[i] + 1.0) for i in range(n)]

    # ── 3. Income density: coupon / price ────────────────────────────────────
    density = [
        (b.coupon / (b.price or 100.0) * 100.0) if b.coupon else 0.0
        for b in bonds
    ]

    # ── 4. Maturity spacing: penalty for edge-of-rung clustering ─────────────
    # Score = 1 - |years_to_maturity - rung_centre| / 0.5
    spacing = []
    for b in bonds:
        yrs = metrics.years_to_maturity(b, as_of)
        if yrs is None:
            spacing.append(0.5)
            continue
        rung = round(yrs)
        dist = abs(yrs - rung)           # 0 = perfectly centred on rung
        spacing.append(max(0.0, 1.0 - dist / 0.5))

    def _norm(vals: list[float]) -> list[float]:
        lo, hi = min(vals), max(vals)
        span = hi - lo
        return [(v - lo) / span if span > 0 else 0.5 for v in vals]

    y_n = _norm(ytw_premium)
    c_n = _norm(credit_eff)
    d_n = _norm(density)
    s_n = _norm(spacing)

    corporate_scores = [
        b.corporate_quality_score or corporate_quality_score(b, target_rank)[0]
        for b in bonds
    ]
    q_n = _norm(corporate_scores)

    composite = [
        (
            0.45 * q_n[i]
            + 0.25 * y_n[i]
            + 0.15 * c_n[i]
            + 0.10 * d_n[i]
            + 0.05 * s_n[i]
        )
        if bonds[i].corporate_quality_score is not None
        else (
            0.40 * y_n[i]
            + 0.30 * c_n[i]
            + 0.20 * d_n[i]
            + 0.10 * s_n[i]
        )
        for i in range(n)
    ]

    # Shift to be strictly positive, apply floor, normalise.
    min_c = min(composite)
    composite = [c - min_c + 0.001 for c in composite]
    weights = [max(c, min_floor) for c in composite]
    total = sum(weights)
    return [w / total for w in weights]


def size_positions(
    bonds: list[Bond],
    weights: list[float],
    target_value: float,
    *,
    lot_size: int = 1_000,
) -> None:
    """Assign market_value / quantity / annual_income in place from weights.

    ``lot_size`` is the standard bond-trading increment in face-value dollars.
    Typical values:
      - 1 000  — minimum tradeable lot
      - 5 000  — small institutional (default — produces clean round faces)
      - 10 000 — common round lot
      - 25 000 — mid-size lot
      - 50 000 — 50-piece lot
      - 100 000 — 100-piece lot (standard institutional)

    Face is rounded to the nearest ``lot_size``; market value is then
    recomputed from the rounded face so all figures stay consistent.
    """
    remaining = target_value
    remaining_weight = sum(weights)
    for bond, weight in zip(bonds, weights):
        mv = remaining * (weight / remaining_weight) if remaining_weight > 0 else 0.0
        price = bond.price or 100.0
        raw_face = mv / (price / 100.0)
        # Round face to the nearest lot increment without exceeding remaining
        # market value. This keeps target sizing market-value based, not face
        # based, and avoids overspending after lot rounding.
        face = max(lot_size, round(raw_face / lot_size) * lot_size)
        if face * price / 100.0 > remaining and remaining >= lot_size * price / 100.0:
            face = max(lot_size, int((remaining / (price / 100.0)) // lot_size) * lot_size)
        bond.quantity = float(face)
        bond.market_value = round(face * price / 100.0, 2)
        if bond.coupon is not None:
            bond.annual_income = round(bond.coupon / 100.0 * face, 2)
        remaining = max(0.0, remaining - bond.market_value)
        remaining_weight = max(0.0, remaining_weight - weight)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

@dataclass
class SamplePortfolio:
    strategy: Strategy
    bonds: list[Bond]
    metrics: dict
    target_value: float
    as_of: date
    warnings: list[str] = field(default_factory=list)


def build_sample_portfolio(
    universe: list[Bond],
    strategy: Strategy,
    *,
    target_value: float = DEFAULT_TARGET_VALUE,
    tax_rate: float = metrics.DEFAULT_TAX_RATE,
    as_of: date | None = None,
    exclude_unrated: bool = True,
    lot_size: int = 5_000,
    state: str | None = None,
) -> SamplePortfolio:
    as_of = as_of or date.today()
    warnings: list[str] = []

    candidates = filter_candidates(universe, strategy, as_of, exclude_unrated=exclude_unrated, state=state)
    if strategy.asset == "municipal" and state:
        in_state = [
            b for b in candidates
            if (b.state or "").strip().upper() == state.strip().upper()
        ]
        if len(in_state) < strategy.target_count:
            warnings.append(
                f"Limited {state.upper()} GO inventory found; eligible national/multi-state issues may supplement the ladder."
            )
    if not candidates:
        raise ValueError(f"No eligible bonds found for strategy '{strategy.key}'.")

    selected = select_ladder(candidates, strategy, as_of, state=state)
    if not selected:
        raise ValueError(f"Could not build a ladder for strategy '{strategy.key}'.")

    # Rule 8 is enforced against Fitch (the only agency in tav.Security_Info)
    # and only where a rating exists. Surface an under-filled ladder and any
    # holdings the source data does not rate.
    if len(selected) < strategy.target_count:
        note = (
            "; municipal Fitch coverage is sparse (most issues are NR)"
            if exclude_unrated and strategy.asset == "municipal"
            else ""
        )
        warnings.append(
            f"Only {len(selected)} of {strategy.target_count} target rungs could be "
            f"filled from eligible inventory{note}."
        )
    unrated = sum(1 for bond in selected if rating_rank(bond.best_rating) is None)
    if unrated:
        warnings.append(
            f"{unrated} of {len(selected)} holdings have no Fitch rating in the source "
            f'data and are shown as "Not rated"; the A- credit screen was not applied to them.'
        )

    # Force strategy tax treatment so income splits are correct even when the
    # security master's Federal_Taxable flag is missing.
    for bond in selected:
        if bond.federal_taxable is None:
            bond.federal_taxable = not strategy.tax_exempt

    # Positions should be roughly equal in market-value exposure. Selection
    # handles quality/yield preferences; sizing keeps the ladder balanced.
    weights = [1.0 / len(selected) for _ in selected]
    size_positions(selected, weights, target_value, lot_size=lot_size)

    computed = metrics.compute_metrics(selected, as_of=as_of, tax_rate=tax_rate)
    return SamplePortfolio(
        strategy=strategy,
        bonds=selected,
        metrics=computed,
        target_value=target_value,
        as_of=as_of,
        warnings=warnings,
    )


def generate(
    session: Session,
    strategy_key: str,
    *,
    target_value: float = DEFAULT_TARGET_VALUE,
    tax_rate: float = metrics.DEFAULT_TAX_RATE,
    as_of: date | None = None,
    exclude_unrated: bool = True,
    lot_size: int = 5_000,
    state: str | None = None,
) -> SamplePortfolio:
    strategy = STRATEGIES.get(strategy_key)
    if strategy is None:
        raise ValueError(f"Unknown strategy '{strategy_key}'.")
    universe = load_universe(session)
    return build_sample_portfolio(
        universe, strategy, target_value=target_value, tax_rate=tax_rate,
        as_of=as_of, exclude_unrated=exclude_unrated, lot_size=lot_size, state=state,
    )
