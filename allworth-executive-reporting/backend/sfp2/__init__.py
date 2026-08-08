"""SFP2 schema manager blueprint.

Lets internal admins compare bronze Delta tables under abfss://bronze/.../sfp2/<Object>
against live Salesforce describe() output and (in later phases) ALTER the Delta
table schema so the next ingestion run picks up new fields.

All imports are kept defensive — a failure here must not prevent the rest of
the Flask app from booting (mirrors the delta_reader pattern in app.py).
"""
