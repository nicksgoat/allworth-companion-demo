from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def isolate_feedback_log(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FEEDBACK_LOG_PATH", str(tmp_path / "feedback.log"))
