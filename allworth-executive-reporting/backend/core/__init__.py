"""Shared backend core — cross-cutting modules used by multiple tool packages.

Tool packages (backend/<tool>/) may import from ``core`` and from their own
package only; they must not import from each other. app.py composes the tools.

- ``core.auth_middleware`` — global JWT (Entra ID) validation middleware.
- ``core.delta_reader`` — ADLS Gen2 Delta Lake reader (delta-rs).
"""
