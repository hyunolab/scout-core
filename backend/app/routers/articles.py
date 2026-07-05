from fastapi import APIRouter
from app.collector.world_nuclear_news import get_latest_news
from app.ai.analyzer import analyze

router = APIRouter(
    prefix="/api/v1/articles",
    tags=["Articles"]
)


@router.get("")
def get_articles():
    articles = get_latest_news(limit=5)

    analyzed_articles = []

    for article in articles:
        analysis = analyze(article["title"])

        analyzed_articles.append({
            **article,
            "analysis": analysis
        })

    return analyzed_articles