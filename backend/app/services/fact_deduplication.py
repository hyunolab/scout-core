import logging
import re
import time
from collections import Counter

from app.services.fact_normalization import build_canonical_fact_signature
from app.services.fact_similarity import calculate_fact_similarity

logger = logging.getLogger(__name__)

CLASSIFICATION_THRESHOLDS = {
    "exact": 1.0,
    "high": 0.88,
    "possible": 0.72,
    "unlikely": 0.50,
}

REASON_MESSAGES = {
    "same_subject": "Canonical subjects match.",
    "same_action": "Both Facts describe the same normalized action.",
    "technology_overlap": "Both Facts refer to overlapping technologies.",
    "same_entities": "Canonical entity sets match.",
    "entity_overlap": "Canonical entity sets overlap.",
    "organization_overlap": "Both Facts reference overlapping organizations.",
    "high_object_overlap": "Core object terms strongly overlap.",
    "partial_object_overlap": "Core object terms partially overlap.",
    "close_observation_dates": "The Facts were observed close together.",
    "generic_subject_penalty": "One Fact uses a generic industry subject.",
    "status_stage_difference": "The Facts describe different lifecycle stages.",
    "different_capacity": "The Facts contain different capacity values.",
    "different_country": "The Facts refer to different countries.",
    "different_object": "The Facts refer to different core objects.",
}

STATUS_STAGE_GROUPS = [
    {"planned", "proposed"},
    {"approved", "funded", "contracted", "selected"},
    {"under_construction", "in_progress", "testing"},
    {"operating", "completed"},
    {"delayed", "cancelled"},
]


def _status_stage(status):
    for index, group in enumerate(STATUS_STAGE_GROUPS):
        if status in group:
            return index
    return None


def _capacity_values(text):
    return set(re.findall(r"\b\d+(?:\.\d+)?\s*(?:mw|mwe|gw|gwe)\b", str(text).lower()))


def detect_dedup_conflicts(fact_a, fact_b):
    canonical_a = build_canonical_fact_signature(fact_a)
    canonical_b = build_canonical_fact_signature(fact_b)
    conflicts = []

    stage_a = _status_stage(canonical_a["status"])
    stage_b = _status_stage(canonical_b["status"])
    if stage_a is not None and stage_b is not None and stage_a != stage_b:
        conflicts.append("status_stage_difference")

    capacities_a = _capacity_values(fact_a.get("object", ""))
    capacities_b = _capacity_values(fact_b.get("object", ""))
    if capacities_a and capacities_b and capacities_a != capacities_b:
        conflicts.append("different_capacity")

    if (
        canonical_a["country"] != "unknown"
        and canonical_b["country"] != "unknown"
        and canonical_a["country"] != canonical_b["country"]
    ):
        conflicts.append("different_country")

    if (
        canonical_a["technologies"]
        and canonical_b["technologies"]
        and not set(canonical_a["technologies"]) & set(canonical_b["technologies"])
    ):
        conflicts.append("different_technology")

    return {
        "has_conflict": bool(conflicts),
        "conflicts": conflicts,
    }


def _reason_messages(reason_codes):
    return [
        {
            "code": code,
            "message": REASON_MESSAGES.get(code, code.replace("_", " ")),
        }
        for code in sorted(set(reason_codes))
    ]


def classify_duplicate_candidate(fact_a, fact_b):
    similarity = calculate_fact_similarity(fact_a, fact_b)
    conflicts = detect_dedup_conflicts(fact_a, fact_b)
    score = similarity["score"]

    if fact_a.get("fact_key") and fact_a.get("fact_key") == fact_b.get("fact_key"):
        classification = "exact"
    elif similarity["canonical_a"]["signature_key"] == similarity["canonical_b"]["signature_key"]:
        classification = "exact"
    elif conflicts["has_conflict"]:
        classification = "different"
    elif score >= CLASSIFICATION_THRESHOLDS["high"]:
        classification = "high"
    elif score >= CLASSIFICATION_THRESHOLDS["possible"]:
        classification = "possible"
    elif score >= CLASSIFICATION_THRESHOLDS["unlikely"]:
        classification = "unlikely"
    else:
        classification = "different"

    merge_recommended = classification in {"exact", "high"} and not conflicts["has_conflict"]
    reason_codes = similarity["reasons"] + conflicts["conflicts"]

    return {
        "classification": classification,
        "similarity_score": score,
        "similarity": similarity,
        "merge_recommended": merge_recommended,
        "auto_merge_eligible": False,
        "reasons": _reason_messages(reason_codes),
        "conflicts": conflicts["conflicts"],
    }


def build_dedup_preview(base_fact, candidate_facts, min_score=0.5, include_different=False):
    base_canonical = build_canonical_fact_signature(base_fact)
    candidates = []

    for candidate_fact in candidate_facts:
        if candidate_fact["id"] == base_fact["id"]:
            continue
        classification = classify_duplicate_candidate(base_fact, candidate_fact)
        if classification["similarity_score"] < min_score:
            continue
        if classification["classification"] == "different" and not include_different:
            continue
        candidates.append(
            {
                "fact": candidate_fact,
                "canonical": classification["similarity"]["canonical_b"],
                "similarity_score": classification["similarity_score"],
                "similarity_components": classification["similarity"]["components"],
                "classification": classification["classification"],
                "merge_recommended": classification["merge_recommended"],
                "auto_merge_eligible": classification["auto_merge_eligible"],
                "reasons": classification["reasons"],
                "conflicts": classification["conflicts"],
            }
        )

    candidates.sort(key=lambda item: item["similarity_score"], reverse=True)

    return {
        "fact_id": base_fact["id"],
        "base_fact": base_fact,
        "base_canonical": base_canonical,
        "candidates": candidates,
        "database_modified": False,
    }


def scan_all_duplicate_candidates(facts, min_score=0.72, limit=100):
    start = time.perf_counter()
    pairs = []
    pairs_compared = 0

    for index, fact_a in enumerate(facts):
        for fact_b in facts[index + 1:]:
            pairs_compared += 1
            classification = classify_duplicate_candidate(fact_a, fact_b)
            if classification["similarity_score"] < min_score:
                continue
            if classification["classification"] == "different":
                continue
            pairs.append(
                {
                    "fact_id_a": fact_a["id"],
                    "fact_id_b": fact_b["id"],
                    "similarity_score": classification["similarity_score"],
                    "similarity_components": classification["similarity"]["components"],
                    "classification": classification["classification"],
                    "merge_recommended": classification["merge_recommended"],
                    "auto_merge_eligible": False,
                    "reasons": classification["reasons"],
                    "conflicts": classification["conflicts"],
                }
            )

    pairs.sort(key=lambda item: item["similarity_score"], reverse=True)
    limited_pairs = pairs[:limit]
    classification_counts = Counter(pair["classification"] for pair in limited_pairs)
    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)

    logger.info(
        "Fact dedup scan facts=%s compared=%s returned=%s elapsed_ms=%s",
        len(facts),
        pairs_compared,
        len(limited_pairs),
        elapsed_ms,
    )

    return {
        "facts_scanned": len(facts),
        "pairs_compared": pairs_compared,
        "duplicate_candidates": len(limited_pairs),
        "classification_counts": {
            "exact": classification_counts.get("exact", 0),
            "high": classification_counts.get("high", 0),
            "possible": classification_counts.get("possible", 0),
            "unlikely": classification_counts.get("unlikely", 0),
        },
        "pairs": limited_pairs,
        "execution_ms": elapsed_ms,
        "database_modified": False,
    }
