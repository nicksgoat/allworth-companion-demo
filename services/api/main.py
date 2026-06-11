# Entrypoint shim: run.sh invokes `uvicorn main:app` from this directory.
# (.env is loaded by allworth_api.config on import, before the API key is read.)
from allworth_api.presentation.api import app  # noqa: F401
