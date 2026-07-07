from fastapi import APIRouter

from app.ai.analyzer import analyze
from app.collector.scraper import get_article_content
from app.collector.world_nuclear_news import get_latest_news
from app.database.article_repository import get_saved_articles, save_article

router = APIRouter(
    prefix="/api/v1/articles",
    tags=["Articles"]
)


@router.get("")
def get_articles():
    return get_saved_articles()


@router.post("/refresh")
def refresh_articles():
    articles = get_latest_news(limit=5)
    results = []

    for article in articles:
        try:
            content = get_article_content(article["link"])
        except Exception as e:
            print("Scraper Error:", e)
            content = ""

        try:
            analysis = analyze(article["title"])
        except Exception as e:
            print("Analyzer Error:", e)
            analysis = {
                "title": article["title"],
                "country": "Unknown",
                "organization": "Unknown",
                "technology": "Unknown",
                "category": "Unknown",
                "importance": 3,
                "summary": article["title"],
                "impact": ""
            }

        article_data = {
            **article,
            "content_preview": content,
            "analysis": analysis
        }

        try:
            save_article(article_data)
        except Exception as e:
            print("DB Error:", e)

        results.append(article_data)

    return {
        "message": "Articles refreshed",
        "count": len(results),
        "articles": results
    }