from collections import Counter, defaultdict

from app.database.timeline_repository import (
    get_active_facts_with_articles,
    update_fact_event_date,
)
from app.services.fact_extraction import is_unknown, normalize_text
from app.services.fact_normalization import (
    normalize_fact_country,
    normalize_fact_organization,
    normalize_fact_technology,
)
from app.services.timeline_dates import (
    get_timeline_bucket,
    normalize_event_date,
    resolve_fact_event_date,
)


VALID_DIMENSIONS = {"technology", "country", "organization"}
VALID_GRAINS = {"year", "month", "day"}
DIMENSION_RESPONSE_KEYS = {
    "technology": "technologies",
    "country": "countries",
    "organization": "organizations",
}


def split_dimension_values(value):
    if is_unknown(value):
        return []

    values = []
    for part in str(value).split(";"):
        cleaned = normalize_text(part)
        if cleaned and not is_unknown(cleaned) and cleaned not in values:
            values.append(cleaned)
    return sorted(values, key=str.lower)


def normalize_dimension_value(dimension, value):
    if dimension == "technology":
        return normalize_fact_technology(value)
    if dimension == "organization":
        return normalize_fact_organization(value)
    if dimension == "country":
        countries = []
        for part in split_dimension_values(value):
            country = normalize_fact_country(part)
            if country != "unknown" and country not in countries:
                countries.append(country)
        if not countries:
            country = normalize_fact_country(value)
            if country != "unknown":
                countries.append(country)
        return sorted(countries, key=str.lower)
    raise ValueError("invalid_dimension")


def get_fact_dimensions(fact):
    return {
        "technologies": normalize_dimension_value("technology", fact.get("technology")),
        "countries": normalize_dimension_value("country", fact.get("country")),
        "organizations": normalize_dimension_value("organization", fact.get("organization")),
    }


def _resolved_fact(fact):
    resolved = resolve_fact_event_date(fact, fact.get("linked_articles", []))
    output = {
        "fact_id": fact["id"],
        "event_date": resolved["event_date"],
        "date_precision": resolved["date_precision"],
        "date_source": resolved["date_source"],
        "event_date_confidence": resolved["confidence"],
        "subject": fact.get("subject"),
        "action": fact.get("action"),
        "object": fact.get("object"),
        "summary": fact.get("summary"),
        "fact_type": fact.get("fact_type"),
        "status": fact.get("status"),
        "country": fact.get("country"),
        "technology": fact.get("technology"),
        "organization": fact.get("organization"),
        "importance": fact.get("importance") or 0,
        "confidence": fact.get("confidence") or 0,
        "evidence_count": fact.get("evidence_count") or 0,
    }
    output["dimensions"] = get_fact_dimensions(fact)
    return output


def _date_start(event_date, precision):
    if not event_date:
        return None
    if precision == "year":
        return f"{event_date[:4]}-01-01"
    if precision == "month":
        return f"{event_date[:7]}-01"
    return event_date[:10]


def _date_end(event_date, precision):
    if not event_date:
        return None
    if precision == "year":
        return f"{event_date[:4]}-12-31"
    if precision == "month":
        return f"{event_date[:7]}-31"
    return event_date[:10]


def _recent_sort_value(event_date):
    if not event_date:
        return 0
    digits = event_date.replace("-", "")
    return int(digits.ljust(8, "0")[:8])


def _passes_date_range(fact, date_from=None, date_to=None):
    if not date_from and not date_to:
        return True
    start = _date_start(fact.get("event_date"), fact.get("date_precision"))
    end = _date_end(fact.get("event_date"), fact.get("date_precision"))
    if not start or not end:
        return False
    if date_from:
        parsed_from = normalize_event_date(date_from)
        if not parsed_from["event_date"]:
            raise ValueError("date_parse_failed")
        if end < _date_start(parsed_from["event_date"], parsed_from["date_precision"]):
            return False
    if date_to:
        parsed_to = normalize_event_date(date_to)
        if not parsed_to["event_date"]:
            raise ValueError("date_parse_failed")
        if start > _date_end(parsed_to["event_date"], parsed_to["date_precision"]):
            return False
    return True


def _validate_date_range(date_from=None, date_to=None):
    if not date_from or not date_to:
        return

    parsed_from = normalize_event_date(date_from)
    parsed_to = normalize_event_date(date_to)
    if not parsed_from["event_date"] or not parsed_to["event_date"]:
        raise ValueError("date_parse_failed")

    from_start = _date_start(parsed_from["event_date"], parsed_from["date_precision"])
    to_end = _date_end(parsed_to["event_date"], parsed_to["date_precision"])
    if from_start and to_end and from_start > to_end:
        raise ValueError("invalid_date_range")


def _sort_facts(facts):
    return sorted(
        facts,
        key=lambda fact: (
            _date_start(fact.get("event_date"), fact.get("date_precision")) or "9999-99-99",
            -(fact.get("importance") or 0),
            -(fact.get("confidence") or 0),
            -(fact.get("evidence_count") or 0),
            -(fact.get("fact_id") or 0),
        ),
    )


def _dimension_key(dimension):
    if dimension == "technology":
        return "technologies"
    if dimension == "country":
        return "countries"
    if dimension == "organization":
        return "organizations"
    raise ValueError("invalid_dimension")


def _load_timeline_facts(include_merged=False):
    return [_resolved_fact(fact) for fact in get_active_facts_with_articles(include_merged=include_merged)]


def get_dimension_list(dimension=None, limit=100):
    if dimension and dimension not in VALID_DIMENSIONS:
        raise ValueError("invalid_dimension")

    facts = _load_timeline_facts()
    dimensions = dimension and [dimension] or ["technology", "country", "organization"]
    response = {}

    for item in dimensions:
        key = _dimension_key(item)
        stats = {}
        for fact in facts:
            for name in fact["dimensions"][key]:
                current = stats.setdefault(
                    name,
                    {
                        "name": name,
                        "fact_count": 0,
                        "evidence_count_total": 0,
                        "first_event_date": None,
                        "last_event_date": None,
                    },
                )
                current["fact_count"] += 1
                current["evidence_count_total"] += fact["evidence_count"]
                event_date = fact.get("event_date")
                if event_date:
                    if current["first_event_date"] is None or event_date < current["first_event_date"]:
                        current["first_event_date"] = event_date
                    if current["last_event_date"] is None or event_date > current["last_event_date"]:
                        current["last_event_date"] = event_date

        rows = sorted(
            stats.values(),
            key=lambda row: (
                -row["fact_count"],
                row["last_event_date"] is None,
                -_recent_sort_value(row["last_event_date"]),
                row["name"].lower(),
            ),
        )[:limit]
        response[DIMENSION_RESPONSE_KEYS[item]] = rows

    return response


def get_dimension_timeline(
    dimension,
    name,
    grain="year",
    date_from=None,
    date_to=None,
    limit=100,
    include_unknown_dates=False,
    include_coarse_dates=False,
):
    if dimension not in VALID_DIMENSIONS:
        raise ValueError("invalid_dimension")
    if grain not in VALID_GRAINS:
        raise ValueError("invalid_grain")
    _validate_date_range(date_from=date_from, date_to=date_to)

    target_values = {value.lower() for value in normalize_dimension_value(dimension, name)}
    if not target_values:
        target_values = {normalize_text(name).lower()}

    key = _dimension_key(dimension)
    matched = []
    unknown = []
    for fact in _load_timeline_facts():
        values = {value.lower() for value in fact["dimensions"][key]}
        if target_values.isdisjoint(values):
            continue
        if not _passes_date_range(fact, date_from=date_from, date_to=date_to):
            continue
        if not fact.get("event_date"):
            unknown.append(fact)
            if include_unknown_dates:
                matched.append(fact)
            continue
        matched.append(fact)

    buckets = defaultdict(list)
    for fact in matched:
        period = get_timeline_bucket(
            fact.get("event_date"),
            fact.get("date_precision"),
            grain=grain,
            include_coarse_dates=include_coarse_dates,
        )
        if period is None and include_unknown_dates:
            period = "unknown"
        if period is not None:
            buckets[period].append(fact)

    bucket_rows = []
    for period in sorted(buckets):
        facts = _sort_facts(buckets[period])[:limit]
        bucket_rows.append(
            {
                "period": period,
                "fact_count": len(facts),
                "evidence_count_total": sum(fact["evidence_count"] for fact in facts),
                "facts": facts,
            }
        )

    dated_facts = [fact for fact in matched if fact.get("event_date")]
    response = {
        "dimension": dimension,
        "name": next(iter(target_values)).upper() if name.upper() == "SMR" else name,
        "grain": grain,
        "total_facts": len(matched),
        "facts_without_dates": len(unknown),
        "evidence_count_total": sum(fact["evidence_count"] for fact in matched),
        "first_event_date": min((fact["event_date"] for fact in dated_facts), default=None),
        "last_event_date": max((fact["event_date"] for fact in dated_facts), default=None),
        "buckets": bucket_rows,
    }

    if dimension == "country":
        response["top_technologies"] = _top_related(matched, "technologies")
    if dimension == "organization":
        response["top_technologies"] = _top_related(matched, "technologies")
        response["top_countries"] = _top_related(matched, "countries")

    return response


def _top_related(facts, dimension_key, limit=5):
    counter = Counter()
    evidence_counter = Counter()
    for fact in facts:
        for value in fact["dimensions"][dimension_key]:
            counter[value] += 1
            evidence_counter[value] += fact["evidence_count"]
    return [
        {
            "name": name,
            "fact_count": count,
            "evidence_count_total": evidence_counter[name],
        }
        for name, count in counter.most_common(limit)
    ]


def get_timeline_summary(date_from=None, date_to=None, grain="year"):
    if grain not in VALID_GRAINS:
        raise ValueError("invalid_grain")
    _validate_date_range(date_from=date_from, date_to=date_to)

    facts = []
    for fact in _load_timeline_facts():
        if _passes_date_range(fact, date_from=date_from, date_to=date_to):
            facts.append(fact)

    technology_names = set()
    country_names = set()
    organization_names = set()
    year_counts = Counter()

    for fact in facts:
        technology_names.update(fact["dimensions"]["technologies"])
        country_names.update(fact["dimensions"]["countries"])
        organization_names.update(fact["dimensions"]["organizations"])
        period = get_timeline_bucket(fact.get("event_date"), fact.get("date_precision"), grain=grain)
        if period:
            year_counts[period] += 1

    return {
        "total_active_facts": len(facts),
        "facts_with_dates": sum(1 for fact in facts if fact.get("event_date")),
        "facts_without_dates": sum(1 for fact in facts if not fact.get("event_date")),
        "technology_count": len(technology_names),
        "country_count": len(country_names),
        "organization_count": len(organization_names),
        "top_technologies": _top_related(facts, "technologies"),
        "top_countries": _top_related(facts, "countries"),
        "top_organizations": _top_related(facts, "organizations"),
        "year_counts": [
            {"year": period, "fact_count": count}
            for period, count in sorted(year_counts.items())
        ],
    }


def backfill_fact_event_dates(dry_run=True, force=False):
    facts = get_active_facts_with_articles()
    source_counts = Counter()
    candidates = []
    dates_resolved = 0
    dates_unknown = 0
    facts_to_update = 0

    for fact in facts:
        resolved = resolve_fact_event_date(fact, fact.get("linked_articles", []))
        source_counts[resolved["date_source"]] += 1
        if resolved["event_date"]:
            dates_resolved += 1
        else:
            dates_unknown += 1

        should_update = bool(resolved["event_date"]) and (
            force or not fact.get("event_date")
        )
        if should_update:
            facts_to_update += 1
            if not dry_run:
                update_fact_event_date(
                    fact["id"],
                    resolved["event_date"],
                    resolved["date_precision"],
                    resolved["date_source"],
                    resolved["confidence"],
                )

        candidates.append(
            {
                "fact_id": fact["id"],
                "current_event_date": fact.get("event_date"),
                "resolved_event_date": resolved["event_date"],
                "date_precision": resolved["date_precision"],
                "date_source": resolved["date_source"],
                "will_update": should_update,
            }
        )

    return {
        "dry_run": dry_run,
        "force": force,
        "facts_scanned": len(facts),
        "dates_resolved": dates_resolved,
        "dates_unknown": dates_unknown,
        "facts_to_update": facts_to_update,
        "source_counts": dict(source_counts),
        "database_modified": not dry_run and facts_to_update > 0,
        "candidates": candidates,
    }
