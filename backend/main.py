from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from core.database import init_db, SessionLocal
from core.config import settings
from core.security import hash_password
from models.user import User, UserRole
import os
from api import auth, documents, chat, analytics, matters, library, research


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database tables
    init_db()

    # Seed admin user if not present
    db = SessionLocal()
    try:
        if not db.query(User).filter(User.email == settings.admin_email).first():
            db.add(
                User(
                    email=settings.admin_email,
                    hashed_password=hash_password(settings.admin_password),
                    full_name="System Admin",
                    role=UserRole.admin,
                )
            )
            db.commit()
    finally:
        db.close()

    # Ensure storage directories exist
    os.makedirs(settings.uploads_path, exist_ok=True)
    os.makedirs(settings.library_path, exist_ok=True)

    # Pre-warm embedding model so first upload is not slow
    from services.rag_service import prewarm
    prewarm()

    yield


app = FastAPI(
    title="Law Firm AI",
    description="Private, secure AI assistant for legal document analysis",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8501",
        "http://frontend:8501",
        "http://127.0.0.1:8501",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(matters.router)
app.include_router(documents.router)
app.include_router(chat.router)
app.include_router(analytics.router)
app.include_router(library.router)
app.include_router(research.router)


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok"}
