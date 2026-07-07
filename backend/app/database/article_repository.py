import sqlite3

from app.database.database import get_connection


def save_article(article):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT OR IGNORE INTO articles
        (
            title,
            link,
            published,
            content,
            country,
            organization,
            technology,
            category,
            importance,
            summary,
            impact
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            article["title"],
            article["link"],
            article["published"],
            article.get("content_preview", ""),
            article["analysis"]["country"],
            article["analysis"]["organization"],
            article["analysis"]["technology"],
            article["analysis"]["category"],
            article["analysis"]["importance"],
            article["analysis"]["summary"],
            article["analysis"]["impact"],
        ),
    )

    conn.commit()
    conn.close()


def get_saved_articles():
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT *
        FROM articles
        ORDER BY id DESC
        """
    )

    rows = cursor.fetchall()
    conn.close()

    articles = []

    for row in rows:
        item = dict(row)

        articles.append({
            "title": item["title"],
            "link": item["link"],
            "published": item["published"],
            "content_preview": item["content"],
            "analysis": {
                "title": item["title"],
                "country": item["country"],
                "organization": item["organization"],
                "technology": item["technology"],
                "category": item["category"],
                "importance": item["importance"],
                "summary": item["summary"],
                "impact": item["impact"],
            }
        })

    return articles