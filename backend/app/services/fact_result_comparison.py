from app.services.fact_quality import evaluate_rule_fact_quality


def _score_ai_fact(fact):
    score = fact.get("confidence", 0.4)
    if fact.get("validation_status") == "valid":
        score += 0.1
    if fact.get("validation_status") == "warning":
        score -= 0.05
    if fact.get("validation_status") == "invalid":
        score -= 0.3
    if fact.get("evidence_sentence"):
        score += 0.08
    if fact.get("subject") == "Global nuclear industry":
        score -= 0.1
    return round(min(max(score, 0.0), 1.0), 2)


def compare_rule_and_ai_facts(rule_facts, ai_facts):
    rule_scores = [
        evaluate_rule_fact_quality(fact)["score"]
        for fact in rule_facts
    ]
    ai_scores = [_score_ai_fact(fact) for fact in ai_facts]
    rule_score = round(max(rule_scores), 2) if rule_scores else 0.0
    ai_score = round(max(ai_scores), 2) if ai_scores else 0.0

    reasons = []
    if len(ai_facts) > len(rule_facts):
        reasons.append("AI extracted more independent facts")
    if ai_facts and all(fact.get("evidence_sentence") for fact in ai_facts):
        reasons.append("AI provided evidence sentences")
    if ai_score > rule_score:
        reasons.append("AI score is higher than rule score")

    recommended_source = "ai" if ai_score > rule_score else "rule"
    recommended_facts = ai_facts if recommended_source == "ai" else rule_facts

    return {
        "recommended_source": recommended_source,
        "rule_score": rule_score,
        "ai_score": ai_score,
        "recommended_facts": recommended_facts,
        "reasons": reasons,
    }

