from __future__ import annotations

from allworth_api.data.seed import current_seed


def advisor_by_id(advisor_id: str | None) -> dict:
    """Return a known advisor, falling back to the seed default for demo data."""
    advisors = current_seed()["personas"]["advisors"]
    return next(
        (advisor for advisor in advisors if advisor.get("id") == advisor_id),
        advisors[0],
    )


def advisor_for_client(client_id: str | None) -> dict:
    client = next(
        (client for client in current_seed()["personas"]["clients"] if client.get("id") == client_id),
        None,
    )
    return advisor_by_id((client or {}).get("advisorId"))


def advisor_name_for_client(client_id: str | None) -> str:
    return advisor_for_client(client_id).get("name", "your advisor")


def advisor_first_name_for_client(client_id: str | None) -> str:
    return advisor_name_for_client(client_id).split()[0]
