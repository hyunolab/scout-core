import feedparser

RSS_URL = "https://world-nuclear-news.org/rss"


def get_latest_news(limit=5):
    feed = feedparser.parse(RSS_URL)

    news = []

    for article in feed.entries[:limit]:
        news.append({
            "title": article.title,
            "link": article.link,
            "published": article.published
        })

    return news


if __name__ == "__main__":
    articles = get_latest_news()

    for article in articles:
        print(article)