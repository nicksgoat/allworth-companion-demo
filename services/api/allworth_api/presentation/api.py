# Allworth Companion demo backend (FastAPI). Demo-grade by design: no auth,
# in-memory conversation state, synthetic data only.
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from allworth_api.presentation.routers import advisors, chat, clients, system

app = FastAPI()
# Web MVP runs in a browser (Expo web on :8081), which enforces CORS;
# native apps never did. Demo-grade: allow everything.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(system.router)
app.include_router(clients.router)
app.include_router(advisors.router)
app.include_router(chat.router)
