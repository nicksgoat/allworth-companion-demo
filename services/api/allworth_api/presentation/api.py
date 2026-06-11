# Allworth Companion demo backend (FastAPI). Demo-grade by design: no auth,
# in-memory conversation state, synthetic data only.
from fastapi import FastAPI

from allworth_api.presentation.routers import advisors, chat, clients, system

app = FastAPI()
app.include_router(system.router)
app.include_router(clients.router)
app.include_router(advisors.router)
app.include_router(chat.router)
