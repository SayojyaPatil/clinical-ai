from fastapi import FastAPI
from contextlib import asynccontextmanager

from app.database import init_db
from app.routers import auth, notes


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="Clinical AI",
    description="AI-powered clinical note summarizer",
    version="1.0.0",
    lifespan=lifespan,
    redirect_slashes=False  # ← add this
)

app.include_router(auth.router)
app.include_router(notes.router)


@app.get("/")
def home():
    return {"message": "Clinical AI is running"}


@app.get("/health")
def health():
    return {"status": "ok"}