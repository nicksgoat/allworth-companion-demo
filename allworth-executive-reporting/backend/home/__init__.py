"""Home — team hub mounted under /home.

Flask Blueprint that serves a landing page with navigation cards to the
team's tools (performance dashboard, Jarvis, heatmaps, reports, etc.).

Register in ``backend/app.py``::

    from home.routes import bp as home_bp
    app.register_blueprint(home_bp, url_prefix="/home")
"""
