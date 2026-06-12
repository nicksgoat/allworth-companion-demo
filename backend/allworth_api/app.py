from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from allworth_api.routes import advisors, auth, chat, clients, system

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(auth.router)
app.include_router(system.router)
app.include_router(clients.router)
app.include_router(advisors.router)
app.include_router(chat.router)
