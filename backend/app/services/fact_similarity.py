import re
from datetime import date
from difflib import SequenceMatcher

from app.services.fact_normalization import build_canonical_fact_signature

SIMILARITY_WEIGHTS = {
    "subject": 0.20,
    "action": 0.15,
    "object": 0.30,
    "technology": 0.15,
    "country": 0.08,
    "organization": 0.07,
    "temporal": 0.05,
}

ACTION_GROUPS = [
    {"proposed", "planning", "announced"},
    {"approved", "selected", "signed", "funded"},
    {"started_construction", "operating", "completed"},
    {"delayed", "cancelled"},
]


def _token_set(value):
    return {
        token
        for token in re.findall(r"[a-z0-9]+", str(value).lower())
        if len(token) > 1
    }


def _jaccard(values_a, values_b):
    set_a = set(values_a)
    set_b = set(values_b)
    if not set_a and not set_b:
        return 0.0
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def calculate_subject_similarity(canonical_a, canonical_b):
    subject_a = canonical_a["subject"]
    subject_b = canonical_b["subject"]
    if subject_a == subject_b:
        return 1.0, ["same_subject"]
    org_score = calculate_entity_similarity(
        canonical_a["organizations"],
        canonical_b["organizations"],
    )[0]
    if org_score > 0:
        return max(0.8, org_score), ["organization_overlap"]
    if canonical_a["country"] == canonical_b["country"] and canonical_a["country"] != "unknown":
        return 0.7, ["same_country_subject"]
    if "Global nuclear industry" in {subject_a, subject_b}:
        if canonical_a["country"] == canonical_b["country"] and canonical_a["country"] != "unknown":
            return 0.5, ["generic_subject_penalty", "same_country_subject"]
        return 0.35, ["generic_subject_penalty"]
    return 0.0, []


def calculate_action_similarity(canonical_a, canonical_b):
    action_a = canonical_a["action"]
    action_b = canonical_b["action"]
    if action_a == action_b:
        return 1.0, ["same_action"]
    if "reported" in {action_a, action_b}:
        return 0.35, ["generic_action"]
    if any(action_a in group and action_b in group for group in ACTION_GROUPS):
        return 0.7, ["related_action_group"]
    return 0.1, []


def calculate_object_similarity(canonical_a, canonical_b):
    object_a = canonical_a["object"]
    object_b = canonical_b["object"]
    if object_a and object_a == object_b:
        return 1.0, ["same_object"]
    tokens_a = _token_set(object_a)
    tokens_b = _token_set(object_b)
    jaccard = _jaccard(tokens_a, tokens_b)
    sequence = SequenceMatcher(None, object_a.lower(), object_b.lower()).ratio()
    score = max(jaccard, sequence * 0.8)
    reasons = []
    if score >= 0.75:
        reasons.append("high_object_overlap")
    elif score >= 0.45:
        reasons.append("partial_object_overlap")
    return round(score, 2), reasons


def calculate_entity_similarity(values_a, values_b):
    score = _jaccard(values_a, values_b)
    if score == 1.0:
        return 1.0, ["same_entities"]
    if score > 0:
        return round(score, 2), ["entity_overlap"]
    return 0.0, []


def calculate_country_similarity(canonical_a, canonical_b):
    country_a = canonical_a["country"]
    country_b = canonical_b["country"]
    if country_a == country_b and country_a != "unknown":
        return 1.0, ["same_country"]
    if "unknown" in {country_a, country_b}:
        return 0.4, ["unknown_country"]
    return 0.0, []


def calculate_temporal_similarity(canonical_a, canonical_b):
    if not canonical_a["time"] or not canonical_b["time"]:
        return 0.3, ["missing_date"]
    try:
        date_a = date.fromisoformat(canonical_a["time"])
        date_b = date.fromisoformat(canonical_b["time"])
    except ValueError:
        return 0.3, ["missing_date"]
    days = abs((date_a - date_b).days)
    if days <= 7:
        return 1.0, ["close_observation_dates"]
    if days <= 30:
        return 0.8, ["close_observation_dates"]
    if days <= 90:
        return 0.5, ["moderate_observation_gap"]
    if days <= 180:
        return 0.3, ["long_observation_gap"]
    return 0.0, ["distant_observation_dates"]


def calculate_fact_similarity(fact_a, fact_b):
    canonical_a = build_canonical_fact_signature(fact_a)
    canonical_b = build_canonical_fact_signature(fact_b)

    subject_score, subject_reasons = calculate_subject_similarity(canonical_a, canonical_b)
    action_score, action_reasons = calculate_action_similarity(canonical_a, canonical_b)
    object_score, object_reasons = calculate_object_similarity(canonical_a, canonical_b)
    technology_score, technology_reasons = calculate_entity_similarity(
        canonical_a["technologies"],
        canonical_b["technologies"],
    )
    country_score, country_reasons = calculate_country_similarity(canonical_a, canonical_b)
    organization_score, organization_reasons = calculate_entity_similarity(
        canonical_a["organizations"],
        canonical_b["organizations"],
    )
    temporal_score, temporal_reasons = calculate_temporal_similarity(canonical_a, canonical_b)

    score = (
        subject_score * SIMILARITY_WEIGHTS["subject"]
        + action_score * SIMILARITY_WEIGHTS["action"]
        + object_score * SIMILARITY_WEIGHTS["object"]
        + technology_score * SIMILARITY_WEIGHTS["technology"]
        + country_score * SIMILARITY_WEIGHTS["country"]
        + organization_score * SIMILARITY_WEIGHTS["organization"]
        + temporal_score * SIMILARITY_WEIGHTS["temporal"]
    )

    return {
        "score": round(score, 2),
        "components": {
            "subject": round(subject_score, 2),
            "action": round(action_score, 2),
            "object": round(object_score, 2),
            "technology": round(technology_score, 2),
            "country": round(country_score, 2),
            "organization": round(organization_score, 2),
            "temporal": round(temporal_score, 2),
        },
        "reasons": (
            subject_reasons
            + action_reasons
            + object_reasons
            + technology_reasons
            + country_reasons
            + organization_reasons
            + temporal_reasons
        ),
        "canonical_a": canonical_a,
        "canonical_b": canonical_b,
    }
