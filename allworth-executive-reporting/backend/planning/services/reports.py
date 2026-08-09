"""Deterministic HTML report rendering from engine outputs.

Named report definitions get purpose-built renderers; everything else falls
back to the generic year-ledger table. All renderers are pure functions of
(facts, projection) so reports stay reproducible and cacheable.
"""

from decimal import Decimal
from html import escape

from planengine.estate import build_estate_flow
from planengine.roth import analyze_roth_conversions
from planengine.tax.ss import claiming_adjustment

D = Decimal

DISCLAIMER = ("Hypothetical planning projection based on advisor-supplied assumptions. "
              "Results are not guaranteed. Consult qualified tax and legal professionals.")

_STYLE = ("body{font:14px Arial;color:#173d67;margin:40px}"
          "h1{border-bottom:3px solid #d8ae64;padding-bottom:12px}"
          "h2{margin-top:28px}table{width:100%;border-collapse:collapse;margin-top:10px}"
          "th,td{padding:8px;border-bottom:1px solid #ddd;text-align:right}"
          "th:first-child,td:first-child{text-align:left}"
          ".flag{color:#a33}.good{color:#2a7}"
          "footer{margin-top:30px;font-size:11px;color:#667}"
          "@media print{button{display:none}}")


def _money(value) -> str:
    return f"${D(value):,.0f}"


def _page(facts, title: str, scenario_name: str, body: str) -> str:
    return (f"<!doctype html><html><head><meta charset='utf-8'>"
            f"<title>{escape(title)}</title><style>{_STYLE}</style></head><body>"
            f"<button onclick='window.print()'>Print / Save PDF</button>"
            f"<h1>{escape(facts.name)} — {escape(title)}</h1>"
            f"<h3>{escape(scenario_name)}</h3>{body}"
            f"<footer>{DISCLAIMER}</footer></body></html>")


def _table(headers: list[str], rows: list[list[str]]) -> str:
    head = "".join(f"<th>{escape(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>"
                   for row in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _ledger_table(projection) -> str:
    return _table(
        ["Year", "Age", "Inflows", "Outflows", "Taxes", "Net worth"],
        [[str(row.year), str(row.client_age or ""), _money(row.inflows),
          _money(row.outflows), _money(row.taxes), _money(row.net_worth)]
         for row in projection.rows])


def _render_generic(facts, projection) -> str:
    return (f"<p>Ending net worth: {_money(projection.ending_net_worth)} · "
            f"Lifetime taxes: {_money(projection.lifetime_taxes)}</p>"
            f"{_ledger_table(projection)}")


def _render_balance_sheet(facts, projection) -> str:
    assets = [a for a in facts.accounts if not a.exclude_from_planning]
    total_assets = sum((a.value for a in assets), D("0"))
    total_debt = sum((x.current_balance for x in facts.liabilities), D("0"))
    asset_rows = [[escape(a.name), escape(a.kind), escape(a.owner), _money(a.value)]
                  for a in assets]
    debt_rows = [[escape(x.institution), "liability", "", _money(x.current_balance)]
                 for x in facts.liabilities]
    return (f"<h2>Assets — {_money(total_assets)}</h2>"
            + _table(["Name", "Type", "Owner", "Value"], asset_rows)
            + f"<h2>Liabilities — {_money(total_debt)}</h2>"
            + (_table(["Name", "Type", "", "Balance"], debt_rows) if debt_rows
               else "<p>No liabilities on file.</p>")
            + f"<h2>Net worth: {_money(total_assets - total_debt)}</h2>")


def _render_asset_allocation(facts, projection) -> str:
    totals: dict[str, Decimal] = {}
    for account in facts.accounts:
        if account.exclude_from_planning:
            continue
        holdings = getattr(account, "holdings", None) or []
        if holdings:
            for holding in holdings:
                name = holding.asset_class or "Unclassified"
                totals[name] = totals.get(name, D("0")) + D(holding.market_value)
        else:
            totals[account.kind] = totals.get(account.kind, D("0")) + D(account.value)
    grand = sum(totals.values(), D("0"))
    rows = [[escape(name), _money(value),
             f"{(value / grand * 100):.1f}%" if grand else "—"]
            for name, value in sorted(totals.items(), key=lambda kv: kv[1], reverse=True)]
    caveat = ("" if any(getattr(a, "holdings", None) for a in facts.accounts)
              else "<p class='flag'>No security-level holdings on file; allocation "
                   "shown by account type. Import holdings from the warehouse for "
                   "asset-class detail.</p>")
    return caveat + _table(["Asset class", "Market value", "Weight"], rows)


def _render_estate_flowchart(facts, projection) -> str:
    flow = build_estate_flow(facts)
    steps = [("Gross estate", flow.gross_estate), ("Less: liabilities", -flow.liabilities),
             ("Less: probate costs", -flow.probate_costs),
             ("Less: final expenses", -flow.final_expenses),
             ("Less: federal estate tax", -flow.federal_estate_tax),
             ("Less: state estate tax", -flow.state_estate_tax),
             ("Net to survivor", flow.net_to_survivor), ("Net to heirs", flow.net_to_heirs)]
    rows = [[escape(label), _money(value)] for label, value in steps]
    flags = "".join(f"<p class='flag'>⚠ {escape(flag)}</p>" for flag in flow.flags)
    liquidity = (f"<h2>Liquidity</h2><p>Liquid assets {_money(flow.liquid_assets)} vs "
                 f"settlement need {_money(flow.liquidity_need)}"
                 + (f" — <span class='flag'>shortfall {_money(flow.liquidity_shortfall)}</span>"
                    if flow.liquidity_shortfall else " — <span class='good'>covered</span>")
                 + "</p>")
    return _table(["Step", "Amount"], rows) + liquidity + flags


def _render_social_security(facts, projection) -> str:
    ss_flows = [flow for flow in facts.income if flow.kind == "social_security"]
    if not ss_flows:
        return "<p>No Social Security income on file for this household.</p>"
    sections = []
    for flow in ss_flows:
        fra_annual = D(flow.amount)
        rows = [[str(age), f"{claiming_adjustment(age) * 100:.1f}%",
                 _money(fra_annual * claiming_adjustment(age))]
                for age in range(62, 71)]
        sections.append(f"<h2>{escape(flow.name)} (FRA benefit {_money(fra_annual)}/yr)</h2>"
                        + _table(["Claim age", "% of FRA benefit", "Annual benefit"], rows))
    return ("<p>Benefit amounts by claiming age, using statutory early-claiming "
            "reductions and delayed retirement credits (FRA 67).</p>" + "".join(sections))


def _render_roth_conversion(facts, projection) -> str:
    analysis = analyze_roth_conversions(facts)
    if not analysis.candidates:
        warnings = "".join(f"<p class='flag'>{escape(w)}</p>" for w in analysis.warnings)
        return warnings or "<p>No conversion candidates were produced.</p>"
    rows = []
    for candidate in analysis.candidates:
        marker = " ★" if (analysis.recommended and
                          candidate.label == analysis.recommended.label) else ""
        rows.append([escape(candidate.label) + marker,
                     _money(candidate.annual_conversion),
                     _money(candidate.total_converted),
                     _money(candidate.lifetime_tax_delta),
                     _money(candidate.ending_after_tax_delta),
                     str(candidate.breakeven_year or "—")])
    recommendation = (f"<p class='good'>Recommended: {escape(analysis.recommended.label)} — "
                      f"{_money(analysis.recommended.annual_conversion)}/yr for "
                      f"{analysis.window_years} years, improving projected after-tax "
                      f"wealth by {_money(analysis.recommended.ending_after_tax_delta)}.</p>"
                      if analysis.recommended else
                      "<p class='flag'>No ladder improves after-tax wealth under "
                      "current assumptions.</p>")
    context = (f"<p>Source account: {escape(analysis.source_account_name or '—')} · "
               f"window {analysis.window_years} years starting "
               f"{analysis.window_start_year} · heir ordinary rate assumption "
               f"{analysis.heir_tax_rate * 100:.0f}%.</p>")
    return (context + recommendation
            + _table(["Strategy", "Annual conversion", "Total converted",
                      "Lifetime tax Δ", "After-tax wealth Δ", "Breakeven"], rows)
            + "<p>After-tax wealth values remaining tax-deferred balances at the "
              "heir rate; deltas are versus the no-conversion baseline.</p>")


def _render_retirement_analysis(facts, projection) -> str:
    shortfall = (f"<p class='flag'>Plan liquidity is depleted in "
                 f"{projection.first_shortfall_year}.</p>"
                 if projection.first_shortfall_year else
                 "<p class='good'>No projected shortfall through the plan horizon.</p>")
    retirement_rows = [row for row in projection.rows if row.phase != "current"]
    first_retirement = retirement_rows[0] if retirement_rows else None
    summary = ""
    if first_retirement:
        summary = (f"<p>Retirement begins in {first_retirement.year} "
                   f"(client age {first_retirement.client_age}). First-year spending "
                   f"{_money(first_retirement.outflows)} against inflows "
                   f"{_money(first_retirement.inflows)}.</p>")
    return summary + shortfall + _ledger_table(projection)


_RENDERERS = {
    "Balance Sheet / Net Worth": _render_balance_sheet,
    "Asset Allocation": _render_asset_allocation,
    "Estate Flowchart": _render_estate_flowchart,
    "Social Security Comparison": _render_social_security,
    "Roth Conversion Analysis": _render_roth_conversion,
    "Retirement Analysis": _render_retirement_analysis,
}


def render_report(facts, projection, title: str, scenario_name: str) -> str:
    renderer = _RENDERERS.get(title, _render_generic)
    return _page(facts, title, scenario_name, renderer(facts, projection))
