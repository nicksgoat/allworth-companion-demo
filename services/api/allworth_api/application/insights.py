# Nudges: data fetch lives here; the rules are pure domain logic.
from allworth_api.domain.nudge_rules import build_nudges
from allworth_api.infrastructure.seed import portfolio_for, seed, spending_summary


def nudges_for(client_id):
    return build_nudges(spending_summary(3), portfolio_for()["positions"], seed["accounts"])
