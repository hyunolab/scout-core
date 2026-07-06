from fastapi import APIRouter

from app.ai.analyzer import analyze
from app.collector.scraper import get_article_content
from app.collector.world_nuclear_news import get_latest_news

router = APIRouter(
    prefix="/api/v1/articles",
    tags=["Articles"]
)


@router.get("")
def get_articles():
    articles = get_latest_news(limit=5)

    results = []

    for article in articles:
        content = get_article_content(article["link"])
        analysis = analyze(article["title"])

        results.append({
            **article,
            "content_preview": content,
            "analysis": analysis
        })

    return results