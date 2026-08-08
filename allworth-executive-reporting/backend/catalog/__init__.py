"""Data Catalog blueprint — a searchable, visual dictionary of the `tho`
warehouse.

Structured catalog data lives under ``catalog/data/`` (generated from the
ThoughtSpot TML repo + ``schema_index.yaml`` by ``catalog/generate.py``). The
same files are designed to be read by a future MCP server so the web UI and AI
tools share one source of truth.
"""
