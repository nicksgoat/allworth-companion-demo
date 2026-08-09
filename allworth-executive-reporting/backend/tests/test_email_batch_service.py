from __future__ import annotations

from io import BytesIO

import pandas as pd

from email_batch import service


def workbook_bytes(rows: list[dict]) -> bytes:
    buffer = BytesIO()
    pd.DataFrame(rows).to_excel(buffer, index=False)
    return buffer.getvalue()


def test_build_batch_groups_rows_and_totals():
    content = workbook_bytes([
        {"Primary Advisor": "Jane Advisor", "Email": "jane@example.com", "Account": "A100", "Amount": 1200},
        {"Primary Advisor": "Jane Advisor", "Email": "jane@example.com", "Account": "A101", "Amount": 800},
    ])

    batch = service.build_batch(
        content,
        "fee_review.xlsx",
        email_map={},
        sender_email="owner@allworth.com",
        body="<p>Please review.</p>",
    )

    assert batch.total_rows == 2
    assert batch.sendable_rows == 2
    assert len(batch.groups) == 1
    assert batch.numeric_totals["Amount"] == 2000
    assert batch.groups[0].cc == ["owner@allworth.com"]
    assert service.store.get(batch.id) is batch


def test_build_batch_marks_missing_advisor_email():
    content = workbook_bytes([
        {"Advisor": "Unmapped Advisor", "Account": "A200"},
        {"Advisor": "", "Account": "A201"},
    ])

    batch = service.build_batch(content, "review.xlsx", {}, None, None)

    assert batch.sendable_rows == 0
    assert batch.missing_advisors == ["Unmapped Advisor"]
    assert [row["__status"] for row in batch.rows] == ["missing_email", "missing_advisor"]
