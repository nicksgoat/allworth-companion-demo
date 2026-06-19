from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from allworth_api.config import cors_origins
from allworth_api.financial_tools.router import router as financial_tools_router
from allworth_api.routes import advisors, auth, chat, clients, system


def create_app() -> FastAPI:
    app = FastAPI(title="Allworth Companion API")
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
