from fastapi import FastAPI
from app.routers import articles

app = FastAPI(
    title="Nuclear Scout API",
    version="0.0.1"
)

app.include_router(articles.router)


@app.get("/")
def root():
    return {
        "service": "Nuclear Scout",
        "status": "online"
    }