import feedparser
from urllib.parse import urljoin, quote

RSS_URL = "https://www.world-nuclear-news.org/rss"
BASE_URL = "https://www.world-nuclear-news.org"


def normalize_link(link: str) -> str:
    if not link:
        return ""

    link = link.strip()

    if link.startswith("//"):
        link = "https:" + link

    if link.startswith("/"):
        link = urljoin(BASE_URL, link)

    link = link.replace("https://www.world-nuclear-news.org//", "https://www.world-nuclear-news.org/")

    parts = link.split("/")
    encoded_parts = [quote(part) if " " in part else part for part in parts]

    return "/".join(encoded_parts)


def get_latest_news(limit=5):
    feed = feedparser.parse(RSS_URL)

    news = []

    for article in feed.entries[:limit]:
        news.append({
            "title": article.get("title", ""),
            "link": normalize_link(article.get("link", "")),
            "published": article.get("published", "")
        })

    return news


if __name__ == "__main__":
    articles = get_latest_news()

    for article in articles:
        print(article)