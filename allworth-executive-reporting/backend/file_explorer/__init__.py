"""File Explorer — download (and later upload) data-lake files (mounts at /api/file-explorer).

Phase 1 surfaces Delta tables under configured ADLS Gen2 roots (e.g. silver/recon)
and lets allow-listed users download them as CSV or tab-delimited text, converted
on the fly. Access is governed by an inline sharing model: admins share a
directory or a single table with users or groups; directory shares cascade to all
current and future children. Group membership is resolved from the existing Admin
console (backend/admin/store.py).
"""
