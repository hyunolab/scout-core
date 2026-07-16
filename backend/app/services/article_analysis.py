from app.ai.analyzer import analyze
from app.database.article_repository import (
    get_unprocessed_articles,
    update_article_analysis,
)


def default_analysis(title):
    return {
        "title": title,
        "country": "Unknown",
        "organization": "Unknown",
        "technology": "Unknown",
        "category": "Unknown",
        "importance": 3,
        "summary": title,
        "impact": "",
    }


def analyze_unprocessed_articles(limit=20):
    articles = get_unprocessed_articles(limit=limit)
    analyzed_articles = []
    errors = []

    for article in articles:
        try:
            analysis = analyze(article["title"])
        except Exception as error:
            analysis = default_analysis(article["title"])
            analysis["impact"] = f"AI analysis failed: {error}"
            errors.append({
                "title": article["title"],
                "message": str(error),
            })

        update_article_analysis(article["link"], analysis)
        analyzed_articles.append({
            **article,
            "analysis": analysis,
        })

    return {
        "count": len(analyzed_articles),
        "articles": analyzed_articles,
        "errors": errors,
    }
