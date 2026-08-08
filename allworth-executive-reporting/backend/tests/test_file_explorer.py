"""Tests for the File Explorer download + inline-sharing module.

No live ADLS / Synapse: table discovery, Delta reads, and the Admin-console
group/manager lookups are all mocked. Run from the backend/ directory:

    python -m pytest tests/test_file_explorer.py -v
"""
from __future__ import annotations

import os
from io import BytesIO

import pandas as pd
import pytest
from flask import Flask

os.environ["AUTH_DISABLE"] = "1"

import delta_reader  # noqa: E402
from admin import store as admin_store  # noqa: E402
from file_explorer import adls, routes, shares  # noqa: E402


# ── fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    """Isolate the share store on disk and reset the route caches per test."""
    monkeypatch.setattr(shares, "_DIR", tmp_path)
    monkeypatch.setattr(shares, "_STATE", tmp_path / "shares.json")
    monkeypatch.setattr(routes, "_roots_cache", None)
    monkeypatch.setattr(routes, "_uploads_cache", None)
    monkeypatch.setattr(routes, "_discovery_cache", {})
    # Default: two discovered tables under any root.
    monkeypatch.setattr(adls, "list_delta_tables", lambda c, p: ["cust_positions", "trade_recon"])
    # Last-modified lookups are mocked so discovery never touches ADLS.
    monkeypatch.setattr(
        adls, "table_last_modified", lambda c, p, t: "2026-01-15T12:00:00Z"
    )


def _admin(monkeypatch, *, admins=(), groups=None, users=None, enforcement=True):
    monkeypatch.setattr(admin_store, "enforcement_enabled", lambda: enforcement)

    def effective_for(email):
        e = (email or "").lower()
        return {"all_access": e in {a.lower() for a in admins}, "effective_tools": []}

    monkeypatch.setattr(admin_store, "effective_for", effective_for)
    monkeypatch.setattr(admin_store, "list_groups", lambda: list(groups or []))
    monkeypatch.setattr(admin_store, "list_users", lambda: list(users or []))


@pytest.fixture
def client():
    app = Flask(__name__)
    app.register_blueprint(routes.bp, url_prefix="/api/file-explorer")
    app.testing = True
    return app.test_client()


def _hdr(email):
    return {"X-User-Email": email}


# ── share store ──────────────────────────────────────────────────────────────


def test_direct_user_share_resolves(monkeypatch):
    _admin(monkeypatch, groups=[])
    shares.add_share("recon", "user", "Jane@allworth.com", "admin@allworth.com")
    assert shares.shared_resource_ids_for("jane@allworth.com") == {"recon"}
    assert shares.shared_resource_ids_for("other@allworth.com") == set()


def test_group_share_resolves_via_membership(monkeypatch):
    _admin(
        monkeypatch,
        groups=[{"id": "analysts", "name": "Analysts", "members": ["sam@allworth.com"]}],
    )
    shares.add_share("recon/cust_positions", "group", "analysts", "admin@allworth.com")
    assert "recon/cust_positions" in shares.shared_resource_ids_for("sam@allworth.com")
    assert shares.shared_resource_ids_for("nobody@allworth.com") == set()


def test_add_share_is_idempotent_and_removable(monkeypatch):
    _admin(monkeypatch, groups=[])
    shares.add_share("recon", "user", "jane@allworth.com", "admin@allworth.com")
    shares.add_share("recon", "user", "jane@allworth.com", "admin@allworth.com")
    assert len(shares.list_shares("recon")) == 1
    assert shares.remove_share("recon", "user", "jane@allworth.com") is True
    assert shares.list_shares("recon") == []


def test_add_share_rejects_bad_principal(monkeypatch):
    _admin(monkeypatch, groups=[])
    with pytest.raises(ValueError):
        shares.add_share("recon", "user", "not-an-email", "admin@allworth.com")
    with pytest.raises(ValueError):
        shares.add_share("recon", "banana", "x@y.com", "admin@allworth.com")


# ── downloads listing (dir cascade + access) ─────────────────────────────────


def test_directory_share_cascades_to_all_tables(monkeypatch, client):
    _admin(monkeypatch, groups=[])
    shares.add_share("recon", "user", "jane@allworth.com", "admin@allworth.com")
    r = client.get("/api/file-explorer/downloads", headers=_hdr("jane@allworth.com"))
    body = r.get_json()
    assert r.status_code == 200
    assert {x["id"] for x in body["resources"]} == {
        "recon/cust_positions",
        "recon/trade_recon",
    }
    assert body["can_manage"] is False


def test_single_table_share_limits_listing(monkeypatch, client):
    _admin(monkeypatch, groups=[])
    shares.add_share("recon/cust_positions", "user", "bob@allworth.com", "admin@allworth.com")
    r = client.get("/api/file-explorer/downloads", headers=_hdr("bob@allworth.com"))
    body = r.get_json()
    assert {x["id"] for x in body["resources"]} == {"recon/cust_positions"}


def test_unshared_user_sees_nothing(monkeypatch, client):
    _admin(monkeypatch, groups=[])
    r = client.get("/api/file-explorer/downloads", headers=_hdr("nobody@allworth.com"))
    assert r.get_json()["resources"] == []


def test_manager_sees_everything(monkeypatch, client):
    _admin(monkeypatch, admins=["admin@allworth.com"], groups=[])
    r = client.get("/api/file-explorer/downloads", headers=_hdr("admin@allworth.com"))
    body = r.get_json()
    assert {x["id"] for x in body["resources"]} == {
        "recon/cust_positions",
        "recon/trade_recon",
    }
    assert body["can_manage"] is True
    assert all(x["last_modified"] == "2026-01-15T12:00:00Z" for x in body["resources"])


# ── download conversion + access ─────────────────────────────────────────────


def _mock_delta(monkeypatch):
    monkeypatch.setattr(delta_reader, "DELTA_AVAILABLE", True)
    monkeypatch.setattr(
        delta_reader,
        "read_delta_table",
        lambda path, limit=None: pd.DataFrame({"a": [1, 2], "b": ["x", "y"]}),
    )


def test_download_csv(monkeypatch, client):
    _admin(monkeypatch, groups=[])
    _mock_delta(monkeypatch)
    shares.add_share("recon", "user", "jane@allworth.com", "admin@allworth.com")
    r = client.get(
        "/api/file-explorer/download/recon/cust_positions?format=csv",
        headers=_hdr("jane@allworth.com"),
    )
    assert r.status_code == 200
    assert r.headers["Content-Disposition"] == 'attachment; filename="cust_positions.csv"'
    assert r.mimetype == "text/csv"
    assert "a,b" in r.get_data(as_text=True)


def test_download_txt_is_tab_delimited(monkeypatch, client):
    _admin(monkeypatch, groups=[])
    _mock_delta(monkeypatch)
    shares.add_share("recon", "user", "jane@allworth.com", "admin@allworth.com")
    r = client.get(
        "/api/file-explorer/download/recon/cust_positions?format=txt",
        headers=_hdr("jane@allworth.com"),
    )
    assert r.status_code == 200
    assert r.headers["Content-Disposition"] == 'attachment; filename="cust_positions.txt"'
    assert r.mimetype == "text/plain"
    assert "a\tb" in r.get_data(as_text=True)


def test_download_denied_without_share(monkeypatch, client):
    _admin(monkeypatch, groups=[])
    _mock_delta(monkeypatch)
    r = client.get(
        "/api/file-explorer/download/recon/cust_positions?format=csv",
        headers=_hdr("nobody@allworth.com"),
    )
    assert r.status_code == 403


def test_download_unknown_resource_404(monkeypatch, client):
    _admin(monkeypatch, admins=["admin@allworth.com"], groups=[])
    _mock_delta(monkeypatch)
    r = client.get(
        "/api/file-explorer/download/recon",  # directory, not a table
        headers=_hdr("admin@allworth.com"),
    )
    assert r.status_code == 404


# ── sharing management is manager-only ───────────────────────────────────────


def test_non_manager_cannot_create_share(monkeypatch, client):
    _admin(monkeypatch, groups=[])
    r = client.post(
        "/api/file-explorer/shares",
        json={"resource_id": "recon", "principal_type": "user", "principal_id": "x@allworth.com"},
        headers=_hdr("jane@allworth.com"),
    )
    assert r.status_code == 403


def test_manager_can_create_and_list_shares(monkeypatch, client):
    _admin(monkeypatch, admins=["admin@allworth.com"], groups=[])
    r = client.post(
        "/api/file-explorer/shares",
        json={"resource_id": "recon", "principal_type": "user", "principal_id": "x@allworth.com"},
        headers=_hdr("admin@allworth.com"),
    )
    assert r.status_code == 201
    r2 = client.get("/api/file-explorer/shares/recon", headers=_hdr("admin@allworth.com"))
    assert r2.status_code == 200
    assert len(r2.get_json()["shares"]) == 1


def test_principals_manager_only(monkeypatch, client):
    _admin(
        monkeypatch,
        admins=["admin@allworth.com"],
        groups=[{"id": "analysts", "name": "Analysts", "members": []}],
        users=[{"email": "sam@allworth.com"}],
    )
    denied = client.get("/api/file-explorer/principals", headers=_hdr("jane@allworth.com"))
    assert denied.status_code == 403
    ok = client.get("/api/file-explorer/principals", headers=_hdr("admin@allworth.com"))
    body = ok.get_json()
    assert body["users"] == ["sam@allworth.com"]
    assert body["groups"] == [{"id": "analysts", "name": "Analysts"}]


# ── uploads (validation + storage) ───────────────────────────────────────────

GL_COLUMNS = [
    "GL", "Description", "Posted dt.", "Doc dt.", "Doc", "Memo/Description",
    "Department name", "Vendor name", "Legal Entitiy name", "Location name",
    "Project name", "JNL", "Debit", "Credit", "Balance",
]

# What GET /uploads reports: column 9 accepts either spelling.
GL_COLUMNS_DISPLAY = GL_COLUMNS.copy()
GL_COLUMNS_DISPLAY[8] = "Legal Entitiy name (or Legal Entity name)"


def _gl_csv(header: list[str], *, lead_rows: int = 0) -> bytes:
    lines = ["Report title,,," for _ in range(lead_rows)]
    lines.append(",".join(header))
    lines.append(",".join(["x"] * len(header)))  # one data row
    return ("\n".join(lines) + "\n").encode("utf-8")


def _gl_csv_titled(header: list[str]) -> bytes:
    """A single-column title on row 1, blank row 2, real header on row 3."""
    lines = ["Monthly GL Export", "", ",".join(header), ",".join(["x"] * len(header))]
    return ("\n".join(lines) + "\n").encode("utf-8")


def _capture_upload(monkeypatch):
    captured: dict[str, Any] = {}

    def _upload(container, path, filename, data):
        captured.update(container=container, path=path, filename=filename, data=data)
        return f"{path}/{filename}"

    monkeypatch.setattr(adls, "upload_bytes", _upload)
    return captured


def _post_gl(client, email, content: bytes, name: str = "gl.csv"):
    return client.post(
        "/api/file-explorer/upload/accounting-gl",
        data={"file": (BytesIO(content), name)},
        content_type="multipart/form-data",
        headers=_hdr(email),
    )


def test_uploads_listed_for_manager_only(monkeypatch, client):
    _admin(monkeypatch, admins=["admin@allworth.com"], groups=[])
    denied = client.get("/api/file-explorer/uploads", headers=_hdr("jane@allworth.com"))
    body = denied.get_json()
    assert body["can_manage"] is False and body["uploads"] == []
    ok = client.get("/api/file-explorer/uploads", headers=_hdr("admin@allworth.com"))
    data = ok.get_json()
    assert data["can_manage"] is True
    gl = next(u for u in data["uploads"] if u["id"] == "accounting-gl")
    assert gl["label"] == "Accounting GL File"
    assert gl["columns"] == GL_COLUMNS_DISPLAY


def test_upload_manager_only(monkeypatch, client):
    _admin(monkeypatch, groups=[])
    _capture_upload(monkeypatch)
    r = _post_gl(client, "jane@allworth.com", _gl_csv(GL_COLUMNS))
    assert r.status_code == 403


def test_upload_rejects_non_csv(monkeypatch, client):
    _admin(monkeypatch, admins=["admin@allworth.com"], groups=[])
    _capture_upload(monkeypatch)
    r = _post_gl(client, "admin@allworth.com", _gl_csv(GL_COLUMNS), name="gl.xlsx")
    assert r.status_code == 400
    assert ".csv" in r.get_json()["error"]


def test_upload_accepts_header_on_row_1(monkeypatch, client):
    _admin(monkeypatch, admins=["admin@allworth.com"], groups=[])
    captured = _capture_upload(monkeypatch)
    r = _post_gl(client, "admin@allworth.com", _gl_csv(GL_COLUMNS))
    assert r.status_code == 200
    body = r.get_json()
    assert body["success"] is True
    assert captured["container"] == "bronze"
    assert captured["path"] == "gl_data/gl_raw"
    assert captured["filename"].endswith("_gl.csv")


def test_upload_accepts_header_on_row_3(monkeypatch, client):
    _admin(monkeypatch, admins=["admin@allworth.com"], groups=[])
    captured = _capture_upload(monkeypatch)
    r = _post_gl(client, "admin@allworth.com", _gl_csv(GL_COLUMNS, lead_rows=2))
    assert r.status_code == 200
    assert captured["path"] == "gl_data/gl_raw"


def test_upload_rejects_wrong_column_count(monkeypatch, client):
    _admin(monkeypatch, admins=["admin@allworth.com"], groups=[])
    _capture_upload(monkeypatch)
    r = _post_gl(client, "admin@allworth.com", _gl_csv(GL_COLUMNS[:-1]))
    assert r.status_code == 422
    err = r.get_json()["error"]
    assert "Expected 15 columns" in err and "found 14" in err


def test_upload_rejects_wrong_column_name(monkeypatch, client):
    _admin(monkeypatch, admins=["admin@allworth.com"], groups=[])
    _capture_upload(monkeypatch)
    bad = GL_COLUMNS.copy()
    bad[7] = "Vender name"  # column 8 misspelled
    r = _post_gl(client, "admin@allworth.com", _gl_csv(bad))
    assert r.status_code == 422
    err = r.get_json()["error"]
    assert "Column 8" in err
    assert "Vendor name" in err and "Vender name" in err


def test_upload_accepts_alternate_legal_entity_spelling(monkeypatch, client):
    _admin(monkeypatch, admins=["admin@allworth.com"], groups=[])
    captured = _capture_upload(monkeypatch)
    alt = GL_COLUMNS.copy()
    alt[8] = "Legal Entity name"  # accepted alternate for column 9
    r = _post_gl(client, "admin@allworth.com", _gl_csv(alt))
    assert r.status_code == 200
    assert captured["path"] == "gl_data/gl_raw"


def test_upload_skips_single_column_title_row(monkeypatch, client):
    _admin(monkeypatch, admins=["admin@allworth.com"], groups=[])
    captured = _capture_upload(monkeypatch)
    r = _post_gl(client, "admin@allworth.com", _gl_csv_titled(GL_COLUMNS))
    assert r.status_code == 200
    assert captured["path"] == "gl_data/gl_raw"

