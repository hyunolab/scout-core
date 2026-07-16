import hashlib
import re
import sqlite3

from app.database.database import get_connection

COMMON_EVENT_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "by",
    "for",
    "from",
    "in",
    "into",
    "is",
    "its",
    "new",
    "of",
    "on",
    "or",
    "over",
    "the",
    "to",
    "with",
    "nuclear",
    "says",
    "set",
}


def ensure_event_key_column():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("PRAGMA table_info(articles)")
    columns = {row[1] for row in cursor.fetchall()}

    if "event_key" not in columns:
        cursor.execute("ALTER TABLE articles ADD COLUMN event_key TEXT")
        conn.commit()

    conn.close()


def _row_to_article(row):
    item = dict(row)

    return {
        "title": item["title"],
        "link": item["link"],
        "published": item["published"],
        "event_key": item.get("event_key"),
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
    }


def generate_event_key(article):
    title = article.get("title", "").lower()
    words = re.sub(r"[^a-z0-9\s]", " ", title).split()
    keywords = [
        word
        for word in words
        if word not in COMMON_EVENT_WORDS and len(word) > 2
    ]

    if keywords:
        return "-".join(keywords[:8])

    link = article.get("link", "")
    digest = hashlib.sha1(link.encode("utf-8")).hexdigest()[:12]
    return f"link-{digest}"


def find_article_by_url(url):
    ensure_event_key_column()

    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT *
        FROM articles
        WHERE link = ?
        LIMIT 1
        """,
        (url,),
    )

    row = cursor.fetchone()
    conn.close()

    if row is None:
        return None

    return _row_to_article(row)


def save_article(article):
    ensure_event_key_column()

    if find_article_by_url(article["link"]) is not None:
        return False

    event_key = article.get("event_key") or generate_event_key(article)

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
            impact,
            event_key
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            event_key,
        ),
    )

    conn.commit()
    saved = cursor.rowcount > 0
    conn.close()

    return saved


def get_latest_articles(limit=20):
    ensure_event_key_column()

    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT *
        FROM articles
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    )

    rows = cursor.fetchall()
    conn.close()

    return [_row_to_article(row) for row in rows]


def get_unprocessed_articles(limit=20):
    ensure_event_key_column()

    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT *
        FROM articles
        WHERE country = ?
          AND organization = ?
          AND technology = ?
          AND category = ?
          AND impact = ?
        ORDER BY id ASC
        LIMIT ?
        """,
        ("Unknown", "Unknown", "Unknown", "Unknown", "", limit),
    )

    rows = cursor.fetchall()
    conn.close()

    return [_row_to_article(row) for row in rows]


def update_article_analysis(url, analysis):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE articles
        SET
            country = ?,
            organization = ?,
            technology = ?,
            category = ?,
            importance = ?,
            summary = ?,
            impact = ?
        WHERE link = ?
        """,
        (
            analysis["country"],
            analysis["organization"],
            analysis["technology"],
            analysis["category"],
            analysis["importance"],
            analysis["summary"],
            analysis["impact"],
            url,
        ),
    )

    conn.commit()
    updated = cursor.rowcount > 0
    conn.close()

    return updated


def update_missing_event_keys():
    ensure_event_key_column()

    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT title, link
        FROM articles
        WHERE event_key IS NULL OR event_key = ?
        """,
        ("",),
    )
    rows = cursor.fetchall()

    updated = 0
    for row in rows:
        article = dict(row)
        event_key = generate_event_key(article)
        cursor.execute(
            """
            UPDATE articles
            SET event_key = ?
            WHERE link = ?
            """,
            (event_key, article["link"]),
        )
        updated += cursor.rowcount

    conn.commit()
    conn.close()

    return updated


def get_articles_grouped_by_event_key():
    ensure_event_key_column()

    articles = get_latest_articles(limit=1000)
    groups = {}

    for article in articles:
        event_key = article["event_key"] or generate_event_key(article)
        groups.setdefault(event_key, []).append(article)

    return [
        {
            "event_key": event_key,
            "count": len(grouped_articles),
            "articles": grouped_articles,
        }
        for event_key, grouped_articles in groups.items()
    ]


def get_saved_articles():
    return get_latest_articles()
