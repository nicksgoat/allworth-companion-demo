"""Jarvis — documentation encyclopedia mounted under /jarvis.

Flask Blueprint that exposes a browseable, editable knowledge base backed by
YAML files under ``backend/jarvis/knowledge/``. The same YAML schema is
consumed by the Allworth MCP server, so edits made through this UI become
source-of-truth for both.

Register in ``backend/app.py``::

    from jarvis.routes import bp as jarvis_bp
    app.register_blueprint(jarvis_bp, url_prefix="/jarvis")
"""
