"""One-page PDF report for a sample bond portfolio.

Renders a Jinja2 HTML template (Allworth logo, analytics summary, and holdings
table) and converts it to a single-page PDF with WeasyPrint. WeasyPrint is an
optional dependency; :func:`render_pdf` raises :class:`PdfUnavailableError` with
a clear message when it is not installed so the API can return a 503.
"""

from __future__ import annotations

import base64
from datetime import date
from pathlib import Path

from investments.services.sample_portfolio import SamplePortfolio

_ASSET_DIR = Path(__file__).resolve().parent.parent / "assets"


class PdfUnavailableError(RuntimeError):
    """Raised when the PDF engine (WeasyPrint) is not available."""


# ---------------------------------------------------------------------------
# Lazy Jinja2 environment — built on first use so startup never fails even
# when Jinja2 is not yet installed in the active venv.
# ---------------------------------------------------------------------------

_env = None
_TEMPLATE = None


def _get_template():
    global _env, _TEMPLATE
    if _TEMPLATE is not None:
        return _TEMPLATE
    try:
        from jinja2 import Environment, select_autoescape
    except ModuleNotFoundError as exc:
        raise PdfUnavailableError(
            "PDF/HTML rendering requires Jinja2. Install with `pip install Jinja2`."
        ) from exc
    _env = Environment(autoescape=select_autoescape(["html", "xml"]), trim_blocks=True, lstrip_blocks=True)
    _env.filters["money"] = _fmt_money
    _env.filters["pct"] = _fmt_pct
    _env.filters["title_case"] = _fmt_title_case
    _TEMPLATE = _env.from_string(_TEMPLATE_SRC)
    return _TEMPLATE


def _logo_html() -> str:
    """Return ready-to-embed logo HTML.

    - If ``allworth-logo.png`` exists: returns an ``<img>`` tag with a PNG
      data URI (WeasyPrint renders raster images natively).
    - Otherwise: returns the SVG *inline* so WeasyPrint renders it directly
      without needing ``cairosvg``.
    """
    png = _ASSET_DIR / "allworth-logo.png"
    if png.exists():
        data = base64.b64encode(png.read_bytes()).decode("ascii")
        return f'<img src="data:image/png;base64,{data}" alt="Allworth Financial" style="height:48px"/>'
    # Inline SVG — WeasyPrint renders inline SVG without any extra library.
    svg_text = (_ASSET_DIR / "allworth-logo.svg").read_text(encoding="utf-8")
    # Strip the XML comment header so it embeds cleanly in HTML.
    import re as _re
    svg_text = _re.sub(r'<!--.*?-->', '', svg_text, flags=_re.DOTALL).strip()
    return svg_text


def _fmt_title_case(value: str | None) -> str:
    """Title-case a bond description, preserving known acronyms and short tokens."""
    if not value:
        return ''
    # Keep these exactly as-is (true acronyms that must stay upper-case).
    _PRESERVE = {'US', 'LLC', 'LP', 'LLP', 'NA', 'USA', 'GO', 'REV', 'USD'}
    result = []
    for w in value.split():
        if w.upper() in _PRESERVE:
            result.append(w.upper())
        elif len(w) <= 2 and w.isalpha():
            # Short all-alpha tokens (state codes, abbreviations) → upper
            result.append(w.upper())
        elif w[0].isdigit():
            # Tokens starting with a digit (e.g. "2.5%", "06/2030", "1Y") → upper alpha part
            result.append(w.upper() if w.isalpha() else w)
        else:
            result.append(w.capitalize())
    return ' '.join(result)


def _fmt_money(value: float | None, decimals: int = 0) -> str:
    if value is None:
        return "—"
    return f"{value:,.{decimals}f}"


def _fmt_pct(value: float | None, decimals: int = 3) -> str:
    if value is None:
        return "—"
    return f"{value:.{decimals}f}%"


_TEMPLATE_SRC = (
    """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<style>
  /* ── Allworth brand tokens (from frontend/src/theme.ts) ── */
  :root {
    --navy:       #173D67;   /* allworthNavy  */
    --cerulean:   #3E71B7;   /* allworthAccent */
    --night:      #0C2E4E;   /* chartNightBlue */
    --surface:    #F3F4F4;   /* surfacePrimary / Feather Gray */
    --card:       #FFFFFF;   /* surfaceCard */
    --hairline:   #E6E6E6;   /* hairline */
    --ink:        #000000;
    --ink-sec:    #595959;
    --ink-tert:   #828282;
    --gain:       #436434;
    --gold:       #A99C6C;
  }
  @page { size: Letter portrait; margin: 0.45in 0.55in; }
  @import url('https://fonts.googleapis.com/css2?family=Lato:wght@400;700&family=Playfair+Display:wght@600&display=swap');
  * { box-sizing: border-box; }
  body {
    font-family: 'Lato', 'Helvetica Neue', Arial, sans-serif;
    font-size: 10.5px;
    color: var(--ink);
    margin: 0;
    background: var(--card);
  }

  /* ── Header: white background so the real navy logo shows correctly ── */
  .header {
    background: var(--card);
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 0 10px;
    margin: -0.45in -0.55in 0;
    padding-left: 0.55in;
    padding-right: 0.55in;
    border-bottom: 3px solid var(--cerulean);
    gap: 12px;
  }
  /* Logo sits on white; png img path for when real asset is placed */
  .header img { height: 48px; flex-shrink: 0; }
  /* Pure HTML brand block (reliable in WeasyPrint) */
  .brand { display: flex; flex-direction: column; justify-content: center; gap: 0; }
  .brand-name {
    font-family: 'Lato', 'Helvetica Neue', Arial, sans-serif;
    font-size: 28px;
    font-weight: 700;
    color: var(--navy);
    letter-spacing: -0.5px;
    line-height: 1;
  }
  .brand-sub {
    font-family: 'Lato', 'Helvetica Neue', Arial, sans-serif;
    font-size: 8px;
    font-weight: 400;
    color: var(--cerulean);
    letter-spacing: 4px;
    text-transform: uppercase;
    margin-top: 1px;
  }
  /* Strategy title in navy on white */
  .header .title {
    font-family: 'Playfair Display', Georgia, serif;
    font-size: 19px;
    font-weight: 600;
    color: var(--navy);
    text-align: right;
  }
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 0.8px;
    text-transform: uppercase;
    color: var(--ink-tert);
    margin-bottom: 2px;
    text-align: right;
  }
  /* Narrow navy accent bar below the header */
  .header-accent {
    background: linear-gradient(90deg, var(--night) 0%, var(--navy) 60%, var(--cerulean) 100%);
    height: 4px;
    margin: 0 -0.55in 12px;
  }

  /* ── Body ── */
  .desc {
    font-size: 10px;
    color: var(--ink-sec);
    line-height: 1.45;
    margin-bottom: 11px;
  }
  .cols { display: flex; gap: 16px; margin-bottom: 12px; }
  .col { flex: 1; }

  /* section-header matches sectionHeaderStyle in theme.ts */
  .section-title {
    font-size: 9px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.6px;
    color: var(--ink-tert);
    border-bottom: 1px solid var(--hairline);
    padding-bottom: 2px;
    margin-bottom: 4px;
  }

  table.kv { width: 100%; border-collapse: collapse; }
  table.kv td { padding: 2.5px 0; font-size: 10px; }
  table.kv td.val {
    text-align: right;
    font-variant-numeric: tabular-nums;
    color: var(--navy);
    font-weight: 600;
  }
  table.kv tr { border-bottom: 1px solid var(--hairline); }

  /* ── Holdings table ── */
  .holdings { width: 100%; border-collapse: collapse; margin-top: 6px; font-size: 9px; }
  .holdings th {
    background: var(--navy);
    color: #fff;
    text-align: left;
    padding: 3px 5px;
    font-size: 8.5px; border-bottom: 1px solid var(--hairline); }
  .holdings td.num { text-align: right; font-variant-numeric: tabular-nums; color: var(--navy); }
  .holdings tr:nth-child(even) td { background: var(--surface); }

  /* ── Footer ── */
  .footer {
    margin-top: 12px;
    border-top: 2px solid var(--cerulean);
    padding-top: 6px;
    font-size: 8px;
  }
  .footer .contact {
    color: var(--navy);
    font-weight: 700;
    font-size: 10px;
  }
</style>
</head>
<body>
  <div class="header">
    {% if logo_is_png %}
    <img src="{{ logo_png }}" alt="Allworth Financial"/>
    {% else %}
    <div class="brand"><div class="brand-name">Allworth<span style="font-size:14px;vertical-align:super;font-weight:400">™</span></div><div class="brand-sub">Financial</div></div>
    {% endif %}
    <div>
      <div class="eyebrow">Sample Portfolio</div>
      <div class="title">{{ strategy.label }}</div>
    </div>
  </div>
  <div class="header-accent"></div>

  <div class="desc">{{ strategy.description }}</div>

  <div class="cols">
    <div class="col">
      <div class="section-title">Investment</div>
      <table class="kv">
        <tr><td>Portfolio Value</td><td class="val">{{ m.portfolio_value | money }}</td></tr>
        <tr><td>Cash Invested</td><td class="val">{{ m.cash_invested | money }}</td></tr>
        <tr><td>Total Face Value</td><td class="val">{{ m.total_face_value | money }}</td></tr>
        <tr><td>Number of Securities</td><td class="val">{{ m.number_of_securities }}</td></tr>
      </table>
      <div class="section-title" style="margin-top:10px;">Statistics</div>
      <table class="kv">
        <tr><td>Avg Credit Quality</td><td class="val">{{ m.average_credit_quality or '—' }}</td></tr>
        <tr><td>Yield-To-Worst / Yield-To-Maturity</td><td class="val">{{ m.yield_to_worst | pct }} / {{ m.yield_to_maturity | pct }}</td></tr>
        <tr><td>Tax-Equivalent YTW / YTM</td><td class="val">{{ m.tax_equivalent_ytw | pct }} / {{ m.tax_equivalent_ytm | pct }}</td></tr>
        <tr><td>Investor Federal Tax Rate</td><td class="val">{{ m.investor_federal_tax_rate | pct(1) }}</td></tr>
      </table>
    </div>
    <div class="col">
      <div class="section-title">Income</div>
      <table class="kv">
        <tr><td>Annual Taxable Interest Income</td><td class="val">{{ m.annual_taxable_income | money }}</td></tr>
        <tr><td>Annual Tax-Exempt Interest Income</td><td class="val">{{ m.annual_tax_exempt_income | money }}</td></tr>
      </table>
      <div class="section-title" style="margin-top:10px;">Credit Quality</div>
      <table class="kv">
        {% for row in m.credit_quality_distribution %}
        <tr><td>{{ row.grade }}</td><td class="val">{{ row.pct }}%</td></tr>
        {% endfor %}
      </table>
    </div>
  </div>

  <div class="section-title">Holdings</div>
  <table class="holdings">
    <thead>
      <tr>
        <th>CUSIP</th><th>Description</th><th>State</th><th style="text-align:right;">Coupon</th>
        <th style="text-align:right;">Maturity</th><th style="text-align:right;">Face</th>
        <th style="text-align:right;">Price</th><th style="text-align:right;">Market Value</th>
        <th style="text-align:right;">YTW</th><th style="text-align:right;">Rating</th>
      </tr>
    </thead>
    <tbody>
      {% for b in bonds %}
      <tr>
        <td>{{ b.cusip or '' }}</td>
        <td>{{ b.description | title_case }}</td>
        <td>{{ b.state or '—' }}</td>
        <td class="num">{{ b.coupon | pct(3) if b.coupon is not none else '—' }}</td>
        <td class="num">{{ b.maturity_date.isoformat() if b.maturity_date else '—' }}</td>
        <td class="num">{{ b.quantity | money }}</td>
        <td class="num">{{ b.price | money(2) if b.price is not none else '—' }}</td>
        <td class="num">{{ b.market_value | money }}</td>
        <td class="num">{{ b.yield_to_worst | pct(3) if b.yield_to_worst is not none else '—' }}</td>
        <td class="num">{{ b.best_rating or 'NR' }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>

  <div class="footer">
    <div class="contact">(888) 242-6766 &nbsp;•&nbsp; AllworthFinancial.com</div>
    Data as of {{ as_of }}. The figures in this proposal are hypothetical and for illustrative purposes
    only; actual bond-ladder portfolios may differ substantially. These figures do not represent actual
    historical performance or future returns. Return of principal is not included in income figures.
    Advisory services offered through Allworth Financial, an SEC-registered investment advisor.
  </div>
</body>
</html>"""
)


def render_html(portfolio: SamplePortfolio) -> str:
    """Render the report HTML (used by the PDF renderer and unit tests)."""
    png = _ASSET_DIR / "allworth-logo.png"
    logo_is_png = png.exists()
    logo_png = (
        "data:image/png;base64," + base64.b64encode(png.read_bytes()).decode("ascii")
        if logo_is_png else ""
    )
    return _get_template().render(
        logo_is_png=logo_is_png,
        logo_png=logo_png,
        strategy=portfolio.strategy,
        m=portfolio.metrics,
        bonds=portfolio.bonds,
        as_of=portfolio.as_of.strftime("%m/%d/%y") if isinstance(portfolio.as_of, date) else portfolio.as_of,
    )


def render_pdf(portfolio: SamplePortfolio) -> bytes:
    """Render the one-page PDF. Raises PdfUnavailableError if WeasyPrint missing."""
    try:
        from weasyprint import HTML  # imported lazily; heavy optional dependency
    except Exception as exc:  # pragma: no cover - depends on environment
        raise PdfUnavailableError(
            "PDF generation requires WeasyPrint and its native libraries "
            "(libpango, libcairo). Install with `pip install weasyprint`."
        ) from exc

    html = render_html(portfolio)
    return HTML(string=html).write_pdf()
