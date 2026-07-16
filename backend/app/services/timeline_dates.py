import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime


DATE_PRECISION_ORDER = {
    "unknown": 0,
    "year": 1,
    "month": 2,
    "day": 3,
}


def _result(event_date=None, precision="unknown", source="unknown", confidence=0.0):
    return {
        "event_date": event_date,
        "date_precision": precision,
        "date_source": source,
        "confidence": confidence,
    }


def normalize_event_date(value):
    if value is None:
        return _result()

    text = str(value).strip()
    if not text:
        return _result()

    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return _result(text, "day", "explicit", 0.95)
    if re.fullmatch(r"\d{4}-\d{2}", text):
        return _result(text, "month", "explicit", 0.85)
    if re.fullmatch(r"\d{4}", text):
        return _result(text, "year", "explicit", 0.75)

    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return _result(parsed.date().isoformat(), "day", "explicit", 0.95)
    except (TypeError, ValueError):
        pass

    return parse_article_published(text, source="explicit")


def parse_article_published(value, source="article_published"):
    if value is None:
        return _result()

    text = str(value).strip()
    if not text:
        return _result()

    try:
        parsed = parsedate_to_datetime(text)
        return _result(parsed.date().isoformat(), "day", source, 0.75)
    except (TypeError, ValueError, IndexError, AttributeError):
        pass

    for pattern in [
        "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%d %B %Y",
        "%d %b %Y",
        "%B %d, %Y",
        "%b %d, %Y",
    ]:
        try:
            parsed = datetime.strptime(text.replace("Z", "+0000"), pattern)
            return _result(parsed.date().isoformat(), "day", source, 0.75)
        except ValueError:
            continue

    for pattern in ["%B %Y", "%b %Y", "%Y-%m"]:
        try:
            parsed = datetime.strptime(text, pattern)
            return _result(parsed.strftime("%Y-%m"), "month", source, 0.65)
        except ValueError:
            continue

    if re.fullmatch(r"\d{4}", text):
        return _result(text, "year", source, 0.55)

    return _result()


def _date_sort_value(resolved):
    event_date = resolved.get("event_date")
    precision = resolved.get("date_precision")
    if not event_date:
        return None
    if precision == "year":
        return f"{event_date}-01-01"
    if precision == "month":
        return f"{event_date}-01"
    return event_date[:10]


def resolve_fact_event_date(fact, linked_articles):
    existing = normalize_event_date(fact.get("event_date"))
    if existing["event_date"]:
        existing["date_source"] = fact.get("date_source") or "explicit"
        if fact.get("event_date_confidence") is not None:
            existing["confidence"] = fact.get("event_date_confidence")
        return existing

    article_dates = []
    for article in linked_articles or []:
        parsed = parse_article_published(article.get("published"))
        if parsed["event_date"]:
            article_dates.append(parsed)

    article_dates.sort(key=_date_sort_value)
    if article_dates:
        return article_dates[0]

    first_seen = parse_article_published(fact.get("first_seen_at"), source="first_seen")
    if first_seen["event_date"]:
        first_seen["confidence"] = 0.6
        return first_seen

    created_at = parse_article_published(fact.get("created_at"), source="created_at")
    if created_at["event_date"]:
        created_at["confidence"] = 0.5
        return created_at

    return _result()


def get_timeline_bucket(
    event_date,
    date_precision,
    grain="year",
    include_coarse_dates=False,
):
    if not event_date or date_precision == "unknown":
        return None

    if grain == "year":
        return event_date[:4]

    if grain == "month":
        if date_precision in {"day", "month"}:
            return event_date[:7]
        if include_coarse_dates and date_precision == "year":
            return f"{event_date[:4]}-unknown"
        return None

    if grain == "day":
        if date_precision == "day":
            return event_date[:10]
        if include_coarse_dates and date_precision == "month":
            return f"{event_date[:7]}-unknown"
        if include_coarse_dates and date_precision == "year":
            return f"{event_date[:4]}-unknown"
        return None

    return None


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
