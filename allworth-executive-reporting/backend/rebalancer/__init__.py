"""Mock Rebalancer — tax-transition portfolio optimizer.

Engine vendored from AllworthFinancial/ProposalGen @ TaxToolDev
(modules/tax_tools). The engine subpackage is kept byte-identical to
upstream where possible; integration code lives in service.py/routes.py.

Read-only against the warehouse ([tho]/[tav] schemas). No trade
submission — this surface is strictly a mock rebalance / what-if tool.
"""
