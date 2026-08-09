"""Client-style proposal PDF for generated sample bond portfolios.

Construction mirrors the AllworthIQ proposal generators
(``app/utils/pptx_generator_*_proposal*.py``): an explicit ``data`` object is
assembled once, a set of section ``populate_*`` builders fill their portion of a
programmatically-built, Allworth-branded template, and a single orchestrator
(:func:`generate_proposal`) runs the builders in order and writes the output.

Unlike AllworthIQ (which populates a ``.pptx`` via python-pptx and
``prs.save()``), this module keeps the WeasyPrint HTML -> PDF pipeline, so the
"template" is an HTML/CSS skeleton assembled in code rather than a ``.pptx``
file, and the orchestrator returns PDF bytes / writes a PDF to ``output_path``.

Brand conventions borrowed from the AllworthIQ decks: **Playfair Display** for
headings and **Lato** for body copy, over the Allworth blue / night-blue palette.
"""

from __future__ import annotations

import base64
import html
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from investments.models.bond import Bond, rating_rank
from investments.services import portfolio_metrics as metrics
from investments.services.sample_portfolio import SamplePortfolio

_ASSET_DIR = Path(__file__).resolve().parent.parent / "assets"


class ProposalUnavailableError(RuntimeError):
    """Raised when the proposal renderer is not available."""


# ---------------------------------------------------------------------------
# Brand conventions (mirrors AllworthIQ: Playfair Display headings, Lato body)
# ---------------------------------------------------------------------------

FONT_HEADING = '"Playfair Display", Georgia, "Times New Roman", serif'
FONT_BODY = '"Lato", "Source Sans Pro", "Helvetica Neue", Arial, sans-serif'

BRAND = {
    "allworth_blue": "#0075BF",
    "night_blue": "#0C2E4E",
    "green": "#84BD00",
    "dark_gray": "#333333",
    "muted": "#6a7078",
    "light_gray": "#F5F7F9",
    "beige": "#F8F9F6",
    "line": "#E0E4E8",
}


# ---------------------------------------------------------------------------
# Formatting + asset helpers
# ---------------------------------------------------------------------------

def _logo_data_uri() -> str:
    png = _ASSET_DIR / "allworth-logo.png"
    if not png.exists():
        return ""
    return "data:image/png;base64," + base64.b64encode(png.read_bytes()).decode("ascii")


def _fmt_money(value: float | None, decimals: int = 0) -> str:
    if value is None:
        return "-"
    return f"${value:,.{decimals}f}"


def _fmt_pct(value: float | None, decimals: int = 2) -> str:
    if value is None:
        return "-"
    return f"{value:.{decimals}f}%"


def _fmt_date(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, date):
        return value.strftime("%m/%d/%Y")
    return str(value)


def _fmt_title_case(value: str | None) -> str:
    if not value:
        return ""
    preserve = {"US", "USA", "GO", "LLC", "LP", "NA", "USD"}
    words = []
    for word in str(value).split():
        if word.upper() in preserve:
            words.append(word.upper())
        elif word[:1].isdigit():
            words.append(word)
        else:
            words.append(word.capitalize())
    return " ".join(words)


def _esc(value) -> str:
    """HTML-escape arbitrary text pulled from the security data."""
    return html.escape("" if value is None else str(value))


# ---------------------------------------------------------------------------
# Data contract (the explicit ``data`` object the populate_* builders consume)
# ---------------------------------------------------------------------------

@dataclass
class ProposalData:
    """Everything the proposal template needs, assembled once from a portfolio.

    Analogous to the ``data`` dict the AllworthIQ generators receive, but typed.
    """

    title: str
    client_name: str
    prepared_by: str
    proposal_id: str
    as_of: str
    logo: str
    strategy: object
    metrics: dict
    bonds: list[Bond]
    stats: dict
    credit: list[dict]
    maturities: list[dict]
    income: list[dict]
    unrated_count: int = 0
    footer: str = (
        "Hypothetical & illustrative — for discussion purposes only.  ·  "
        "AllworthFinancial.com  ·  (888) 242-6766"
    )
    warnings: list[str] = field(default_factory=list)

    @classmethod
    def from_portfolio(
        cls,
        portfolio: SamplePortfolio,
        *,
        client_name: str | None = None,
        prepared_by: str | None = None,
        proposal_title: str | None = None,
        proposal_id: str | None = None,
    ) -> "ProposalData":
        m = portfolio.metrics
        return cls(
            title=(proposal_title or "").strip() or portfolio.strategy.label,
            client_name=(client_name or "").strip(),
            prepared_by=(prepared_by or "").strip(),
            proposal_id=(proposal_id or "").strip(),
            as_of=_fmt_date(portfolio.as_of),
            logo=_logo_data_uri(),
            strategy=portfolio.strategy,
            metrics=m,
            bonds=list(portfolio.bonds),
            stats=_proposal_stats(portfolio),
            credit=list(m.get("credit_quality_distribution") or []),
            maturities=_maturity_rows(portfolio),
            income=_income_rows(portfolio),
            unrated_count=sum(1 for b in portfolio.bonds if rating_rank(b.best_rating) is None),
            warnings=list(portfolio.warnings),
        )


# ---------------------------------------------------------------------------
# Derived tables / stats (kept pure so populate_* stays declarative)
# ---------------------------------------------------------------------------

def _maturity_rows(portfolio: SamplePortfolio) -> list[dict]:
    rows: dict[int, dict] = {}
    for bond in portfolio.bonds:
        if not bond.maturity_date:
            continue
        year = bond.maturity_date.year
        row = rows.setdefault(year, {"year": year, "count": 0, "market_value": 0.0, "face": 0.0})
        row["count"] += 1
        row["market_value"] += bond.market_value or 0.0
        row["face"] += bond.quantity or 0.0
    ordered = [rows[y] for y in sorted(rows)]
    max_mv = max((r["market_value"] for r in ordered), default=0.0) or 1.0
    for r in ordered:
        r["bar"] = round(r["market_value"] / max_mv * 100.0, 1)
    return ordered


def _income_rows(portfolio: SamplePortfolio) -> list[dict]:
    schedule = list(portfolio.metrics.get("income_schedule") or [])
    max_annual = max((r["annual"] for r in schedule), default=0.0) or 1.0
    rows = []
    for r in schedule:
        rows.append(
            {
                "year": r["year"],
                "annual": r["annual"],
                "cumulative": r["cumulative"],
                "annual_bar": round(r["annual"] / max_annual * 100.0, 1),
            }
        )
    return rows


def _proposal_stats(portfolio: SamplePortfolio) -> dict:
    """Derive the proposal-summary averages the fact-sheet/proposal layouts expose."""
    bonds = portfolio.bonds
    m = portfolio.metrics
    mv_total = sum(b.effective_market_value() for b in bonds) or 1.0

    def _wavg(pairs: list[tuple[float | None, float]]) -> float | None:
        cleaned = [(v, w) for v, w in pairs if v is not None]
        if not cleaned:
            return None
        denom = sum(w for _, w in cleaned) or 1.0
        return sum(v * w for v, w in cleaned) / denom

    average_coupon = _wavg([(b.coupon, b.effective_market_value()) for b in bonds])
    average_price = _wavg([(b.price, b.effective_market_value()) for b in bonds])
    average_maturity = _wavg(
        [(metrics.years_to_maturity(b, portfolio.as_of), b.effective_market_value()) for b in bonds]
    )
    mod_duration = _wavg([(b.effective_duration, b.effective_market_value()) for b in bonds])
    callable_mv = sum(b.effective_market_value() for b in bonds if b.callable)
    callable_pct = callable_mv / mv_total * 100.0
    net_cash = max(0.0, portfolio.target_value - (m.get("portfolio_value") or 0.0))

    return {
        "net_cash": round(net_cash, 2),
        "average_coupon": average_coupon,
        "average_maturity": average_maturity,
        "average_price": average_price,
        "mod_duration": mod_duration,
        "callable_pct": callable_pct,
        "noncallable_pct": 100.0 - callable_pct,
        "total_income": round(
            (m.get("annual_taxable_income") or 0.0) + (m.get("annual_tax_exempt_income") or 0.0), 2
        ),
    }


# ---------------------------------------------------------------------------
# Section builders (mirror AllworthIQ's populate_* per-slide functions)
# ---------------------------------------------------------------------------

def _rhead(d: ProposalData) -> str:
    return (
        f'<div class="rhead"><div class="t">{_esc(d.title)} '
        f'<span>| {_esc(d.client_name) or "—"}</span></div>'
        f'<div class="b">Allworth Financial</div></div>'
    )


def populate_cover(d: ProposalData) -> str:
    brand = (
        f'<img src="{d.logo}" alt="Allworth Financial">'
        if d.logo
        else '<div class="brand-text">Allworth Financial</div>'
    )
    ident = f'<div>ID {_esc(d.proposal_id)}</div>' if d.proposal_id else ""
    return f"""
  <section class="cover">
    <div>
      <div class="eyebrow">Proposal</div>
      <h1 class="cover-title">Portfolio Report</h1>
      <div class="cover-rule"></div>
    </div>
    <div class="cover-meta">
      <div class="doc-title">{_esc(d.title)}</div>
      <div>As of {_esc(d.as_of)}</div>
      {ident}
      <div class="lbl">Regarding:</div>
      <div>{_esc(d.client_name) or "—"}</div>
      <div class="lbl">Prepared By:</div>
      <div>{_esc(d.prepared_by) or "—"}</div>
    </div>
    <div class="cover-brand">
      {brand}
      <div class="cover-tag">Bond Ladder Proposal</div>
    </div>
  </section>"""


def populate_summary(d: ProposalData) -> str:
    m, st = d.metrics, d.stats
    coupon = f'{st["average_coupon"]:.3f}' if st["average_coupon"] is not None else "-"
    maturity = f'{st["average_maturity"]:.2f} Yrs' if st["average_maturity"] is not None else "-"
    duration = (
        f'{st["mod_duration"]:.3f} / {st["mod_duration"]:.3f}'
        if st["mod_duration"] is not None
        else "- / -"
    )
    return f"""
  <section class="page">
    {_rhead(d)}
    <h2>Proposal Summary</h2>
    <div class="band">
      <div><div class="lab">Net Cash Available for Investment</div><div class="val">{_fmt_money(st["net_cash"])}</div></div>
      <div class="band-right"><div class="lab">Proposed Portfolio Value</div><div class="val">{_fmt_money(m.get("portfolio_value"))}</div></div>
    </div>
    <table class="summary">
      <tr class="sec"><td>Principal</td><td class="rt">Proposed</td></tr>
      <tr><td>Total Face Value</td><td class="rt">{_fmt_money(m.get("total_face_value"))}</td></tr>
      <tr><td>Cash Invested</td><td class="rt">{_fmt_money(m.get("cash_invested"))}</td></tr>
      <tr><td>Number of Securities</td><td class="rt">{m.get("number_of_securities", 0)}</td></tr>
      <tr class="sec"><td>Income</td><td class="rt">Proposed</td></tr>
      <tr><td>Annual Taxable Interest Income</td><td class="rt">{_fmt_money(m.get("annual_taxable_income"))}</td></tr>
      <tr><td>Annual Tax-Exempt Interest Income</td><td class="rt">{_fmt_money(m.get("annual_tax_exempt_income"))}</td></tr>
      <tr class="tot"><td>Total (Estimated Annual Income)</td><td class="rt">{_fmt_money(st["total_income"])}</td></tr>
      <tr class="sec"><td>Averages</td><td class="rt">Proposed</td></tr>
      <tr><td>Average Coupon</td><td class="rt">{coupon}</td></tr>
      <tr><td>Average Maturity</td><td class="rt">{maturity}</td></tr>
      <tr><td>Average Market Price</td><td class="rt">{_fmt_money(st["average_price"], 3)}</td></tr>
      <tr><td>Estimated Avg. Credit Quality</td><td class="rt">{_esc(m.get("average_credit_quality") or "-")}</td></tr>
      <tr><td>Callable / Non-callable</td><td class="rt">{st["callable_pct"]:.1f}% / {st["noncallable_pct"]:.1f}%</td></tr>
      <tr><td>Mod Duration to Worst / OAD</td><td class="rt">{duration}</td></tr>
      <tr><td>Average YTW / YTM</td><td class="rt">{_fmt_pct(m.get("yield_to_worst"), 3)} / {_fmt_pct(m.get("yield_to_maturity"), 3)}</td></tr>
      <tr><td>Tax-Equivalent YTW / YTM</td><td class="rt">{_fmt_pct(m.get("tax_equivalent_ytw"), 3)} / {_fmt_pct(m.get("tax_equivalent_ytm"), 3)}</td></tr>
      <tr><td>Investor Federal Tax Rate</td><td class="rt">{_fmt_pct(m.get("investor_federal_tax_rate"), 1)}</td></tr>
    </table>
    {_unrated_note(d)}
  </section>"""


def _unrated_note(d: ProposalData) -> str:
    if not d.unrated_count:
        return ""
    return (
        f'<p class="note"><b>Note:</b> {d.unrated_count} of {len(d.bonds)} holdings carry no '
        f"agency rating in the source data (only Fitch is available) and are shown as "
        f'"Not rated"; the A- credit screen was not applied to them.</p>'
    )


def populate_analysis(d: ProposalData) -> str:
    credit_bars = "".join(
        f'<div class="barrow"><div class="k">{_esc(g["grade"])}</div>'
        f'<div class="track"><div class="fill navy" style="width: {g["pct"]}%"></div></div>'
        f'<div class="v">{g["pct"]:.2f}%</div></div>'
        for g in d.credit
    )
    maturity_bars = "".join(
        f'<div class="barrow"><div class="k">{r["year"]}</div>'
        f'<div class="track"><div class="fill" style="width: {r["bar"]}%"></div></div>'
        f'<div class="v">{_fmt_money(r["market_value"])}</div></div>'
        for r in d.maturities
    )
    income_rows = "".join(
        f'<tr><td>{r["year"]}</td><td class="rt">{_fmt_money(r["annual"])}</td>'
        f'<td class="rt">{_fmt_money(r["cumulative"])}</td>'
        f'<td><div class="track" style="height:11px;"><div class="fill green" '
        f'style="width: {r["annual_bar"]}%"></div></div></td></tr>'
        for r in d.income
    )
    return f"""
  <section class="page">
    {_rhead(d)}
    <div class="two-col">
      <div>
        <h2>Estimated Credit Quality</h2>
        <div class="barlist">{credit_bars}</div>
      </div>
      <div>
        <h2>MV by Final Maturity</h2>
        <div class="barlist">{maturity_bars}</div>
      </div>
    </div>
    <h2 style="margin-top:20px;">Estimated Annual &amp; Cumulative Income</h2>
    <table class="summary">
      <tr class="sec"><td>Year</td><td class="rt">Annual</td><td class="rt">Cumulative</td><td style="width:36%">&nbsp;</td></tr>
      {income_rows}
    </table>
    <p class="note">Estimated gross annual income is the sum of upcoming interest payments for all
    proposed securities in a given year if held to maturity without reinvestment. Return of principal
    is excluded. Estimated income is not guaranteed and excludes the impact of taxes and fees.</p>
  </section>"""


def populate_holdings(d: ProposalData) -> str:
    rows = []
    for b in d.bonds:
        rating = (
            _esc(b.best_rating)
            if rating_rank(b.best_rating) is not None
            else '<span class="nr">Not rated</span>'
        )
        rows.append(
            "<tr>"
            f"<td>{_esc(b.cusip or '')}</td>"
            f"<td>{_esc(_fmt_title_case(b.description))}</td>"
            f"<td>{_esc(b.state or '-')}</td>"
            f'<td class="num">{_fmt_pct(b.coupon, 3)}</td>'
            f'<td class="num">{_fmt_date(b.maturity_date)}</td>'
            f'<td class="num">{_fmt_money(b.quantity)}</td>'
            f'<td class="num">{_fmt_money(b.price, 2)}</td>'
            f'<td class="num">{_fmt_money(b.market_value)}</td>'
            f'<td class="num">{_fmt_pct(b.yield_to_worst, 3)}</td>'
            f'<td class="num">{rating}</td>'
            "</tr>"
        )
    body = "".join(rows)
    return f"""
  <section class="page">
    {_rhead(d)}
    <h2>Proposed Holdings</h2>
    <table class="holdings">
      <thead>
        <tr><th>CUSIP</th><th>Description</th><th>State</th><th class="num">Coupon</th><th class="num">Maturity</th><th class="num">Face</th><th class="num">Price</th><th class="num">Market Value</th><th class="num">YTW</th><th class="num">Rating</th></tr>
      </thead>
      <tbody>{body}</tbody>
    </table>
    <p class="disclosure"><b>Detailed disclosures and risk considerations:</b> The figures in this proposal
    are hypothetical and for illustrative purposes only; actual bond-ladder portfolios may differ
    substantially. These figures do not represent actual historical performance or future returns. Data is
    sourced from the Allworth DataWarehouse based on inventory available at the time of generation. Credit
    quality reflects the available agency rating in the security master (Fitch); securities without a Fitch
    rating are shown as "Not rated." Yield to maturity is the annualized rate of return if the bond is held
    to its effective legal maturity date; yield to worst is the lowest yield calculated to maturity or to any
    early redemption. Bond investments are exposed to interest-rate and default risk and may lose value. For
    some investors, income may be subject to the Alternative Minimum Tax; capital gains, if any, are federally
    taxable and income may be subject to state and local taxes. The securities shown have been selected based
    on general characteristics and are not a recommendation to buy or sell. Advisory services offered through
    Allworth Financial, an SEC-registered investment advisor. Securities offered through AW Securities, a
    Registered Broker/Dealer, member FINRA/SIPC.</p>
  </section>"""


# Ordered registry of section builders (mirrors the AllworthIQ orchestration chain).
_SECTION_BUILDERS = (populate_cover, populate_summary, populate_analysis, populate_holdings)


# ---------------------------------------------------------------------------
# Template (built programmatically) + orchestrator
# ---------------------------------------------------------------------------

def _build_style(d: ProposalData) -> str:
    b = BRAND
    return f"""
  @page {{
    size: Letter portrait;
    margin: 0.6in 0.6in 0.7in;
    @bottom-center {{
      content: "{d.footer}";
      font-family: {FONT_BODY};
      font-size: 7.5px;
      color: #8a8f96;
    }}
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; color: {b['dark_gray']}; font-family: {FONT_BODY}; font-size: 10.5px; line-height: 1.4; }}

  .cover {{
    min-height: 9.4in; margin: -0.6in -0.6in 0; padding: 1.1in 0.9in 0.6in;
    background: {b['beige']}; display: flex; flex-direction: column;
  }}
  .eyebrow {{ color: {b['allworth_blue']}; font-family: {FONT_HEADING}; font-size: 22px; font-weight: 600; margin-bottom: 2px; }}
  .cover-title {{ color: {b['night_blue']}; font-family: {FONT_HEADING}; font-size: 52px; font-weight: 700; letter-spacing: -0.5px; margin: 0; }}
  .cover-rule {{ height: 4px; width: 100%; background: {b['allworth_blue']}; margin: 22px 0 0; }}
  .cover-meta {{ margin-top: 2.2in; font-size: 12px; }}
  .cover-meta .doc-title {{ color: {b['allworth_blue']}; font-weight: 700; font-size: 14px; margin-bottom: 2px; }}
  .cover-meta .lbl {{ color: {b['night_blue']}; font-weight: 700; margin-top: 14px; }}
  .cover-brand {{ margin-top: auto; display: flex; align-items: center; justify-content: space-between; }}
  .cover-brand img {{ height: 38px; }}
  .cover-brand .brand-text {{ color: {b['night_blue']}; font-family: {FONT_HEADING}; font-size: 24px; font-weight: 700; }}
  .cover-tag {{ color: {b['muted']}; font-size: 10px; }}

  .page {{ page-break-before: always; }}
  .rhead {{ display: flex; align-items: baseline; justify-content: space-between; border-bottom: 1px solid {b['line']}; padding-bottom: 6px; margin-bottom: 14px; }}
  .rhead .t {{ color: {b['night_blue']}; font-weight: 700; font-size: 12px; }}
  .rhead .t span {{ color: {b['muted']}; font-weight: 400; }}
  .rhead .b {{ color: {b['allworth_blue']}; font-weight: 700; font-size: 12px; }}

  h2 {{ color: {b['night_blue']}; font-family: {FONT_HEADING}; font-size: 16px; margin: 0 0 10px; letter-spacing: 0.2px; }}

  .band {{ display: flex; gap: 14px; margin-bottom: 16px; }}
  .band > div {{ flex: 1; border: 1px solid {b['line']}; border-radius: 5px; padding: 12px 14px; box-shadow: 0 2px 10px rgba(0,0,0,0.05); }}
  .band .band-right {{ background: {b['night_blue']}; border-color: {b['night_blue']}; }}
  .band .lab {{ font-size: 8.5px; font-weight: 700; letter-spacing: 0.8px; text-transform: uppercase; color: {b['muted']}; }}
  .band .band-right .lab {{ color: #b9cbe0; }}
  .band .val {{ font-family: {FONT_HEADING}; font-size: 24px; font-weight: 700; color: {b['night_blue']}; margin-top: 3px; }}
  .band .band-right .val {{ color: white; }}

  table {{ width: 100%; border-collapse: collapse; }}
  table.summary td {{ padding: 6px 4px; border-bottom: 1px solid {b['line']}; }}
  table.summary td.rt {{ text-align: right; font-weight: 700; color: {b['night_blue']}; font-variant-numeric: tabular-nums; }}
  table.summary tr.sec td {{ background: {b['light_gray']}; color: {b['night_blue']}; font-weight: 700; font-size: 8.5px; letter-spacing: 0.8px; text-transform: uppercase; border-bottom: 2px solid {b['line']}; }}
  table.summary tr.sec td.rt {{ color: {b['muted']}; }}
  table.summary tr.tot td {{ font-weight: 700; color: {b['night_blue']}; border-bottom: 2px solid {b['night_blue']}; }}

  .barlist {{ margin-top: 4px; }}
  .barrow {{ display: flex; align-items: center; gap: 8px; margin: 4px 0; }}
  .barrow .k {{ width: 62px; font-size: 9.5px; color: {b['muted']}; }}
  .barrow .track {{ flex: 1; background: {b['light_gray']}; border-radius: 3px; height: 13px; overflow: hidden; }}
  .barrow .fill {{ height: 100%; background: {b['allworth_blue']}; border-radius: 3px 0 0 3px; }}
  .barrow .fill.navy {{ background: {b['night_blue']}; }}
  .barrow .fill.green {{ background: {b['green']}; }}
  .barrow .v {{ width: 92px; text-align: right; font-size: 9.5px; font-weight: 700; color: {b['night_blue']}; font-variant-numeric: tabular-nums; }}

  .two-col {{ display: flex; gap: 18px; }}
  .two-col > div {{ flex: 1; }}

  table.holdings th {{ background: {b['night_blue']}; color: white; text-align: left; padding: 6px 5px; font-size: 8px; text-transform: uppercase; letter-spacing: 0.3px; }}
  table.holdings td {{ border-bottom: 1px solid {b['line']}; padding: 4px 5px; font-size: 9px; }}
  table.holdings tr:nth-child(even) td {{ background: {b['light_gray']}; }}
  .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .nr {{ color: {b['muted']}; font-style: italic; }}

  .note {{ margin-top: 12px; color: {b['muted']}; font-size: 8px; line-height: 1.45; }}
  .note b {{ color: {b['dark_gray']}; }}
  .disclosure {{ margin-top: 12px; color: {b['muted']}; font-size: 7.5px; line-height: 1.45; text-align: justify; }}
  .disclosure b {{ color: {b['dark_gray']}; }}
"""


def _build_template(d: ProposalData, sections: list[str]) -> str:
    """Assemble the Allworth-branded HTML document from section fragments.

    Programmatic analogue of ``Presentation(template_path)`` — the "template" is
    built in code here (fonts, palette, page frame) and the ``populate_*``
    fragments are injected in order.
    """
    fonts = (
        "@import url('https://fonts.googleapis.com/css2?"
        "family=Playfair+Display:wght@600;700&family=Lato:wght@400;700&display=swap');"
    )
    body = "\n".join(sections)
    return (
        "<!doctype html><html><head><meta charset=\"utf-8\"><style>"
        f"{fonts}{_build_style(d)}"
        f"</style></head><body>{body}</body></html>"
    )


def _assemble_html(data: ProposalData) -> str:
    sections = [build(data) for build in _SECTION_BUILDERS]
    return _build_template(data, sections)


def generate_proposal(data: ProposalData, output_path: str | Path | None = None) -> bytes:
    """Orchestrate the section builders and render the proposal PDF.

    Mirrors ``generate_advisor_proposal_pptx(data, template_path, output_path)``:
    assemble from ``data``, run the ordered section builders, then write/return
    the result. Here the result is PDF bytes (WeasyPrint) rather than a ``.pptx``.
    """
    try:
        from weasyprint import HTML
    except Exception as exc:  # pragma: no cover
        raise ProposalUnavailableError("Proposal PDF generation requires WeasyPrint.") from exc
    pdf = HTML(string=_assemble_html(data)).write_pdf()
    if output_path is not None:
        Path(output_path).write_bytes(pdf)
    return pdf


# ---------------------------------------------------------------------------
# Public API (kept stable for the router)
# ---------------------------------------------------------------------------

def render_html(
    portfolio: SamplePortfolio,
    *,
    client_name: str | None = None,
    prepared_by: str | None = None,
    proposal_title: str | None = None,
    proposal_id: str | None = None,
) -> str:
    """Assemble proposal HTML for preview/testing (no PDF engine required)."""
    data = ProposalData.from_portfolio(
        portfolio,
        client_name=client_name,
        prepared_by=prepared_by,
        proposal_title=proposal_title,
        proposal_id=proposal_id,
    )
    return _assemble_html(data)


def render_pdf(
    portfolio: SamplePortfolio,
    *,
    client_name: str | None = None,
    prepared_by: str | None = None,
    proposal_title: str | None = None,
    proposal_id: str | None = None,
    output_path: str | Path | None = None,
) -> bytes:
    """Render proposal PDF. Raises ProposalUnavailableError if WeasyPrint fails."""
    data = ProposalData.from_portfolio(
        portfolio,
        client_name=client_name,
        prepared_by=prepared_by,
        proposal_title=proposal_title,
        proposal_id=proposal_id,
    )
    return generate_proposal(data, output_path=output_path)
