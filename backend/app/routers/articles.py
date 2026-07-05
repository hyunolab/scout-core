from fastapi import APIRouter
from app.collector.world_nuclear_news import get_latest_news

router = APIRouter(
    prefix="/api/v1/articles",
    tags=["Articles"]
)


@router.get("")
def get_articles():
    return get_latest_news(limit=5)