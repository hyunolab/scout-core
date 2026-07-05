from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import articles

app = FastAPI(
    title="Nuclear Scout API",
    version="0.0.1"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(articles.router)


@app.get("/")
def root():
    return {
        "service": "Nuclear Scout",
        "status": "online"
    }