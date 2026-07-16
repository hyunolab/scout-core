from app.services.fact_extraction import is_unknown


def evaluate_rule_fact_quality(candidate_fact):
    score = candidate_fact.get("confidence", 0.4)
    reasons = []

    if candidate_fact.get("action") == "reported":
        score -= 0.12
        reasons.append("generic_action")
    if candidate_fact.get("status") == "unknown":
        score -= 0.1
        reasons.append("unknown_status")
    if candidate_fact.get("fact_type") == "industry_signal":
        score -= 0.1
        reasons.append("generic_fact_type")
    if candidate_fact.get("subject") == "Global nuclear industry":
        score -= 0.12
        reasons.append("generic_subject")
    if is_unknown(candidate_fact.get("country")):
        score -= 0.08
        reasons.append("unknown_country")
    if is_unknown(candidate_fact.get("technology")):
        score -= 0.08
        reasons.append("unknown_technology")
    if is_unknown(candidate_fact.get("organization")):
        score -= 0.04
        reasons.append("unknown_organization")

    score = round(min(max(score, 0.0), 1.0), 2)
    return {
        "score": score,
        "needs_ai": score < 0.7,
        "reasons": reasons,
    }


def should_use_ai_extraction(article, rule_facts):
    scores = [evaluate_rule_fact_quality(fact) for fact in rule_facts]
    reasons = []

    for score in scores:
        reasons.extend(score["reasons"])

    text = " ".join(
        [
            article.get("title") or "",
            article.get("analysis", {}).get("summary") or "",
        ]
    ).lower()
    if any(word in text for word in [" and ", ";", " partnership ", " agreement "]):
        reasons.append("possible_multiple_facts")

    quality_score = min((score["score"] for score in scores), default=0.0)
    use_ai = quality_score < 0.7 or "possible_multiple_facts" in reasons

    return {
        "use_ai": use_ai,
        "quality_score": quality_score,
        "reasons": sorted(set(reasons)),
    }

