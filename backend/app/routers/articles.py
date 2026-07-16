import logging

from fastapi import APIRouter, HTTPException

from app.collector.scraper import get_article_content
from app.collector.world_nuclear_news import get_latest_news
from app.database.article_repository import (
    get_latest_articles,
    save_article,
    update_missing_event_keys,
)
from app.services.article_analysis import (
    analyze_unprocessed_articles,
    default_analysis,
)

router = APIRouter(
    prefix="/api/v1/articles",
    tags=["Articles"]
)

logger = logging.getLogger(__name__)


@router.get("")
def get_articles():
    try:
        return get_latest_articles(limit=20)
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load saved articles: {error}",
        ) from error


@router.post("/refresh")
def refresh_articles():
    try:
        articles = get_latest_news(limit=5)
    except Exception as error:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to fetch latest nuclear news: {error}",
        ) from error

    for article in articles:
        try:
            content = get_article_content(article["link"])
        except Exception as e:
            logger.warning("Scraper error for %s: %s", article["link"], e)
            content = ""

        article_data = {
            **article,
            "content_preview": content,
            "analysis": default_analysis(article["title"])
        }

        try:
            save_article(article_data)
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to save article '{article['title']}': {e}",
            ) from e

    saved_articles = get_latest_articles(limit=20)

    return {
        "message": "Articles refreshed",
        "count": len(saved_articles),
        "articles": saved_articles
    }


@router.post("/analyze")
def analyze_articles():
    try:
        result = analyze_unprocessed_articles(limit=20)
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to analyze articles: {error}",
        ) from error

    return {
        "message": "Articles analyzed",
        "count": result["count"],
        "articles": result["articles"],
        "errors": result["errors"],
    }


@router.post("/events/backfill")
def backfill_event_keys():
    try:
        updated = update_missing_event_keys()
        articles = get_latest_articles(limit=20)
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to backfill event keys: {error}",
        ) from error

    return {
        "message": "Event keys backfilled",
        "updated": updated,
        "count": len(articles),
        "articles": articles,
    }
