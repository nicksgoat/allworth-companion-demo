from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from allworth_api.config import cors_origins, validate_startup_config
from allworth_api.core.observability import request_logging_middleware
from allworth_api.core.rate_limit import rate_limit_middleware
from allworth_api.financial_tools.router import router as financial_tools_router
from allworth_api.routes import advisors, auth, chat, clients, system


def create_app() -> FastAPI:
    validate_startup_config()
    app = FastAPI(title="Allworth Companion API")
    app.middleware("http")(request_logging_middleware)
    app.middleware("http")(rate_limit_middleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins(),
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(auth.router)
    app.include_router(system.router)
    app.include_router(clients.router)
    app.include_router(advisors.router)
    app.include_router(chat.router)
    app.include_router(financial_tools_router)
    return app


app = create_app()
