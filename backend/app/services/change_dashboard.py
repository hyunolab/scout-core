from collections import Counter
import re

from app.database.article_repository import get_latest_articles

CATEGORY_BUCKETS = {
    "policy": {"policy", "regulation", "regulatory", "government"},
    "technology": {
        "technology",
        "smr",
        "fast reactor",
        "fusion",
        "research",
        "fuel cycle",
        "spent fuel",
        "waste management",
    },
    "investment": {"investment", "construction", "export"},
    "incident": {"incident", "accident", "safety"},
}

CATEGORY_FALLBACK_KEYWORDS = {
    "policy": {
        "policy",
        "regulation",
        "regulatory",
        "government",
        "minister",
        "parliament",
        "license",
        "approval",
        "approves",
        "planning",
        "aims",
    },
    "technology": {
        "technology",
        "smr",
        "triso",
        "fast reactor",
        "molten salt",
        "ap1000",
        "reactor",
        "fusion",
        "fuel",
        "reprocessing",
        "uranium",
        "component",
    },
    "investment": {
        "investment",
        "spend",
        "funding",
        "financing",
        "supply chain",
        "construction",
        "capacity",
        "project",
        "proposal",
        "contract",
    },
    "incident": {
        "incident",
        "accident",
        "safety",
        "outage",
        "shutdown",
        "failure",
        "risk",
        "emergency",
    },
}

TECHNOLOGY_KEYWORDS = {
    "SMR": {"smr", "small modular reactor", "small modular reactors"},
    "TRISO": {"triso"},
    "Fast Reactor": {"fast reactor", "fast reactors"},
    "Molten Salt": {"molten salt", "molten salt reactor"},
    "AP1000": {"ap1000"},
    "Reprocessing": {"reprocessing", "reprocess"},
    "Uranium": {"uranium"},
    "Fuel": {"fuel"},
    "Fusion": {"fusion"},
}

COUNTRY_KEYWORDS = {
    "USA": {"usa", "us", "u.s.", "united states", "america"},
    "France": {"france", "french"},
    "Korea": {"korea", "korean", "south korea"},
    "China": {"china", "chinese"},
    "Russia": {"russia", "russian"},
    "Japan": {"japan", "japanese"},
    "UK": {"uk", "u.k.", "united kingdom", "britain", "british"},
    "Poland": {"poland", "polish"},
    "Canada": {"canada", "canadian"},
    "India": {"india", "indian"},
}

COUNTRY_KO = {
    "USA": "미국",
    "France": "프랑스",
    "Korea": "한국",
    "China": "중국",
    "Russia": "러시아",
    "Japan": "일본",
    "UK": "영국",
    "Poland": "폴란드",
    "Canada": "캐나다",
    "India": "인도",
}

TECHNOLOGY_KO = {
    "SMR": "SMR",
    "TRISO": "TRISO",
    "Fast Reactor": "고속로",
    "Molten Salt": "용융염 원자로",
    "AP1000": "AP1000",
    "Reprocessing": "핵연료 재처리",
    "Uranium": "우라늄",
    "Fuel": "핵연료",
    "Fusion": "핵융합",
}


def _dashboard_articles():
    # TODO: Apply a real daily date window once article dates are normalized.
    return get_latest_articles(limit=1000)


def _normalized(value):
    return (value or "").strip()


def _analysis_value(article, key):
    return _normalized(article.get("analysis", {}).get(key))


def _is_unknown(value):
    return not value or value.lower() == "unknown"


def _article_text(article):
    analysis = article.get("analysis", {})
    return " ".join([
        _normalized(article.get("title")),
        _normalized(analysis.get("summary")),
    ]).lower()


def _has_keyword(text, keyword):
    normalized_keyword = re.escape(keyword.lower())
    return re.search(rf"\b{normalized_keyword}\b", text) is not None


def _find_keyword_value(article, keyword_map):
    text = _article_text(article)

    for value, keywords in keyword_map.items():
        if any(_has_keyword(text, keyword) for keyword in keywords):
            return value

    return "Unknown"


def _category_bucket(category):
    normalized_category = category.lower()

    for bucket, keywords in CATEGORY_BUCKETS.items():
        if any(keyword in normalized_category for keyword in keywords):
            return bucket

    return None


def _fallback_category(article):
    text = _article_text(article)

    for bucket, keywords in CATEGORY_FALLBACK_KEYWORDS.items():
        if any(_has_keyword(text, keyword) for keyword in keywords):
            return bucket

    return None


def _resolved_category(article):
    category = _analysis_value(article, "category")

    if not _is_unknown(category):
        bucket = _category_bucket(category)
        return category, bucket

    bucket = _fallback_category(article)
    if bucket:
        return bucket.title(), bucket

    return "Unknown", None


def _resolved_technology(article):
    technology = _analysis_value(article, "technology")

    if not _is_unknown(technology):
        return technology

    return _find_keyword_value(article, TECHNOLOGY_KEYWORDS)


def _resolved_country(article):
    country = _analysis_value(article, "country")

    if not _is_unknown(country):
        return country

    return _find_keyword_value(article, COUNTRY_KEYWORDS)


def get_today_changes():
    changes = {
        "policy": 0,
        "technology": 0,
        "investment": 0,
        "incident": 0,
    }

    for article in _dashboard_articles():
        _, bucket = _resolved_category(article)
        if bucket:
            changes[bucket] += 1

    return changes


def get_top_technologies(limit=5):
    counter = Counter()

    for article in _dashboard_articles():
        technology = _resolved_technology(article)
        if technology and technology.lower() != "unknown":
            counter[technology] += 1

    return [
        {
            "name": name,
            "count": count,
            "trend": "up",
        }
        for name, count in counter.most_common(limit)
    ]


def get_top_countries(limit=5):
    counter = Counter()

    for article in _dashboard_articles():
        country = _resolved_country(article)
        if country and country.lower() != "unknown":
            counter[country] += 1

    return [
        {
            "name": name,
            "count": count,
        }
        for name, count in counter.most_common(limit)
    ]


def _change_summary(article):
    country = _resolved_country(article)
    technology = _resolved_technology(article)
    category, _ = _resolved_category(article)
    title = _normalized(article.get("title"))
    text = _article_text(article)

    has_country = not _is_unknown(country)
    has_technology = not _is_unknown(technology)
    has_category = not _is_unknown(category)

    subject = "The nuclear industry"
    if has_country and has_technology:
        subject = f"{country}'s {technology} sector"
    elif has_country:
        subject = country
    elif has_technology:
        subject = f"{technology}-related activity"

    if _has_keyword(text, "reprocessing") and has_country:
        return f"{country} is moving toward expanded nuclear fuel reprocessing capacity."

    if technology == "SMR":
        if has_country:
            return f"{country} is seeing increased SMR development activity."
        return "SMR-related development activity is rising."

    if technology == "Fusion":
        if has_country:
            return f"Fusion activity is increasing in {country}."
        return "Fusion supply chain and development activity is increasing."

    if technology == "Uranium":
        if has_country:
            return f"{country} is signaling stronger uranium and nuclear capacity ambitions."
        return "Uranium-related nuclear capacity activity is increasing."

    if _has_keyword(text, "capacity") and has_country:
        return f"{country} is moving to expand nuclear capacity."

    if _has_keyword(text, "proposal") or _has_keyword(text, "project"):
        if has_country and has_technology:
            return f"{country} is advancing a {technology} project proposal."
        if has_technology:
            return f"{technology}-related project activity is advancing."

    if _has_keyword(text, "component") and has_country:
        return f"{country} is reaching a new nuclear project component milestone."

    if has_category and category == "Policy":
        if has_country:
            return f"{country} is showing new nuclear policy or planning activity."
        return "Nuclear policy activity is increasing."

    if has_category and category == "Investment":
        return f"{subject} is attracting new investment or project activity."

    if has_category and category == "Incident":
        return f"{subject} is facing a new safety or operational signal."

    if has_technology:
        return f"{technology}-related nuclear activity is increasing."

    if has_country:
        return f"{country} is showing new nuclear industry activity."

    return f"New nuclear industry signal detected: {title}"


def _display_summary_ko(article):
    country = _resolved_country(article)
    technology = _resolved_technology(article)
    category, _ = _resolved_category(article)
    title = _normalized(article.get("title"))
    text = _article_text(article)

    country_ko = COUNTRY_KO.get(country, country)
    technology_ko = TECHNOLOGY_KO.get(technology, technology)
    has_country = not _is_unknown(country)
    has_technology = not _is_unknown(technology)
    has_category = not _is_unknown(category)

    if _has_keyword(text, "reprocessing") and has_country:
        return f"{country_ko}가 고용량 핵연료 재처리 역량 확대를 추진하고 있습니다."

    if technology == "SMR":
        if has_country:
            return f"{country_ko}에서 SMR 개발 움직임이 확대되고 있습니다."
        return "SMR 관련 개발 움직임이 확대되고 있습니다."

    if technology == "Fusion":
        if has_country:
            return f"{country_ko}에서 핵융합 관련 활동이 증가하고 있습니다."
        return "핵융합 관련 공급망과 개발 활동이 증가하고 있습니다."

    if technology == "Uranium":
        if has_country:
            return f"{country_ko}가 우라늄 및 원자력 역량 확대 의지를 보이고 있습니다."
        return "우라늄 관련 원자력 역량 확대 움직임이 나타나고 있습니다."

    if _has_keyword(text, "capacity") and has_country:
        return f"{country_ko}가 원자력 역량 확대를 추진하고 있습니다."

    if _has_keyword(text, "proposal") or _has_keyword(text, "project"):
        if has_country and has_technology:
            return f"{country_ko}에서 {technology_ko} 프로젝트 추진 움직임이 나타나고 있습니다."
        if has_technology:
            return f"{technology_ko} 관련 프로젝트 활동이 진전되고 있습니다."

    if _has_keyword(text, "component") and has_country:
        return f"{country_ko}의 원전 프로젝트가 주요 부품 단계에서 진전을 보이고 있습니다."

    if has_category and category == "Policy":
        if has_country:
            return f"{country_ko}에서 원자력 정책 또는 계획 관련 움직임이 나타나고 있습니다."
        return "원자력 정책 관련 움직임이 증가하고 있습니다."

    if has_category and category == "Investment":
        if has_country:
            return f"{country_ko}의 원자력 분야에서 투자 또는 프로젝트 활동이 나타나고 있습니다."
        if has_technology:
            return f"{technology_ko} 분야에서 투자 또는 프로젝트 활동이 나타나고 있습니다."
        return "원자력 분야에서 투자 또는 프로젝트 활동이 나타나고 있습니다."

    if has_category and category == "Incident":
        if has_country:
            return f"{country_ko}에서 원자력 안전 또는 운영 관련 이슈가 감지됐습니다."
        return "원자력 안전 또는 운영 관련 이슈가 감지됐습니다."

    if has_technology:
        return f"{technology_ko} 관련 원자력 활동이 증가하고 있습니다."

    if has_country:
        return f"{country_ko}에서 새로운 원자력 산업 움직임이 나타나고 있습니다."

    return f"새로운 원자력 산업 신호가 감지됐습니다: {title}"


def get_top_changes(limit=5):
    unique_articles = {}

    for article in _dashboard_articles():
        event_key = article.get("event_key") or article.get("link")
        current = unique_articles.get(event_key)

        if current is None:
            unique_articles[event_key] = article
            continue

        current_importance = current.get("analysis", {}).get("importance") or 0
        article_importance = article.get("analysis", {}).get("importance") or 0

        if article_importance > current_importance:
            unique_articles[event_key] = article

    sorted_articles = sorted(
        unique_articles.values(),
        key=lambda item: item.get("analysis", {}).get("importance") or 0,
        reverse=True,
    )

    top_changes = []

    for article in sorted_articles[:limit]:
        analysis = article.get("analysis", {})
        category, _ = _resolved_category(article)
        country = _resolved_country(article)
        technology = _resolved_technology(article)

        top_changes.append({
            "title": article["title"],
            "summary": _change_summary(article),
            "display_summary_ko": _display_summary_ko(article),
            "category": category,
            "country": country,
            "technology": technology,
            "importance": analysis.get("importance"),
            "event_key": article.get("event_key"),
        })

    return top_changes


def get_daily_dashboard():
    return {
        "today_changes": get_today_changes(),
        "top_technologies": get_top_technologies(),
        "top_countries": get_top_countries(),
        "top_changes": get_top_changes(),
    }
