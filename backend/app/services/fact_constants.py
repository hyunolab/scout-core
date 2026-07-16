ALLOWED_FACT_TYPES = {
    "policy",
    "technology",
    "investment",
    "regulation",
    "incident",
    "construction",
    "operation",
    "fuel_cycle",
    "waste_management",
    "decommissioning",
    "supply_chain",
    "industry_signal",
}

ALLOWED_STATUSES = {
    "planned",
    "proposed",
    "approved",
    "funded",
    "contracted",
    "selected",
    "under_construction",
    "in_progress",
    "testing",
    "operating",
    "completed",
    "delayed",
    "cancelled",
    "confirmed",
    "unknown",
}

ALLOWED_EXTRACTION_METHODS = {
    "rule",
    "ai",
    "hybrid",
    "manual",
}

ALLOWED_VALIDATION_STATUSES = {
    "valid",
    "warning",
    "invalid",
    "pending",
}

FACT_TYPE_LABELS = {
    "policy": "Policy",
    "technology": "Technology",
    "investment": "Investment",
    "regulation": "Regulation",
    "incident": "Incident",
    "construction": "Construction",
    "operation": "Operation",
    "fuel_cycle": "Fuel Cycle",
    "waste_management": "Waste Management",
    "decommissioning": "Decommissioning",
    "supply_chain": "Supply Chain",
    "industry_signal": "Industry Signal",
}

MAX_AI_PROMPT_CONTENT_CHARS = 10000

