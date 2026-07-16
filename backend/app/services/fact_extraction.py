import re


UNKNOWN_VALUES = {"", "unknown", None}

COUNTRY_PATTERNS = {
    "USA": [
        "United States",
        "U.S.",
        "U.S",
        "US",
        "USA",
        "American",
        "DOE",
        "NRC",
    ],
    "UK": ["United Kingdom", "UK", "British"],
    "France": ["France", "French"],
    "Korea": ["South Korea", "Republic of Korea", "Korea", "Korean", "KHNP"],
    "China": ["China", "Chinese"],
    "Russia": ["Russia", "Russian", "Rosatom"],
    "Japan": ["Japan", "Japanese"],
    "Canada": ["Canada", "Canadian"],
    "India": ["India", "Indian"],
    "Poland": ["Poland", "Polish"],
    "Ukraine": ["Ukraine", "Ukrainian"],
    "Czech Republic": ["Czech Republic", "Czechia", "Czech"],
    "Finland": ["Finland", "Finnish"],
    "Sweden": ["Sweden", "Swedish"],
    "Romania": ["Romania", "Romanian"],
    "UAE": ["United Arab Emirates", "UAE", "Emirati"],
}

TECHNOLOGY_PATTERNS = {
    "SMR": ["SMR", "small modular reactor", "small modular reactors"],
    "TRISO": ["TRISO"],
    "Fast Reactor": ["Fast Reactor", "Fast Breeder Reactor"],
    "Molten Salt Reactor": ["Molten Salt Reactor"],
    "AP1000": ["AP1000"],
    "APR1400": ["APR1400", "APR-1400"],
    "EPR": ["EPR"],
    "BWRX-300": ["BWRX-300", "BWRX 300"],
    "Natrium": ["Natrium"],
    "NuScale": ["NuScale"],
    "Fusion": ["Fusion"],
    "Reprocessing": ["Reprocessing", "Fuel Reprocessing"],
    "MOX": ["MOX"],
    "RepU": ["RepU", "Reprocessed Uranium"],
    "Enrichment": ["Enrichment"],
    "Conversion": ["Conversion"],
    "Uranium": ["Uranium"],
    "Nuclear Fuel": ["Nuclear Fuel"],
    "Fuel Cycle": ["Fuel Cycle"],
    "Spent Fuel": ["Spent Fuel", "Spent Nuclear Fuel"],
    "Dry Storage": ["Dry Storage"],
    "Geological Disposal": ["Geological Disposal"],
    "Waste Management": ["Waste Management", "Radioactive Waste"],
    "Decommissioning": ["Decommissioning", "Dismantling"],
    "HALEU": ["HALEU", "High-Assay Low-Enriched Uranium"],
    "LEU": ["LEU", "Low-Enriched Uranium"],
    "CANDU": ["CANDU"],
    "PWR": ["PWR", "Pressurized Water Reactor"],
    "BWR": ["BWR", "Boiling Water Reactor"],
    "HTGR": ["HTGR", "High Temperature Gas Reactor"],
    "Microreactor": ["Microreactor", "Micro-reactor"],
}

ORGANIZATION_PATTERNS = {
    "DOE": ["DOE", "Department of Energy"],
    "NRC": ["NRC", "Nuclear Regulatory Commission"],
    "IAEA": ["IAEA"],
    "Westinghouse": ["Westinghouse"],
    "Holtec": ["Holtec"],
    "EDF": ["EDF"],
    "Orano": ["Orano"],
    "Rosatom": ["Rosatom"],
    "KHNP": ["KHNP"],
    "KEPCO": ["KEPCO"],
    "Doosan Enerbility": ["Doosan Enerbility"],
    "TerraPower": ["TerraPower"],
    "X-energy": ["X-energy", "X Energy"],
    "BWXT": ["BWXT"],
    "Cameco": ["Cameco"],
    "Centrus": ["Centrus"],
    "NuScale": ["NuScale"],
    "GE Hitachi": ["GE Hitachi"],
    "Rolls-Royce SMR": ["Rolls-Royce SMR", "Rolls Royce SMR"],
    "Framatome": ["Framatome"],
    "Urenco": ["Urenco"],
    "CNNC": ["CNNC"],
    "CGN": ["CGN"],
    "JAEA": ["JAEA"],
    "Mitsubishi Heavy Industries": ["Mitsubishi Heavy Industries"],
    "Ontario Power Generation": ["Ontario Power Generation", "OPG"],
    "Bruce Power": ["Bruce Power"],
    "Bechtel": ["Bechtel"],
    "Polskie Elektrownie Jadrowe": [
        "Polskie Elektrownie Jadrowe",
        "Polskie Elektrownie Jądrowe",
        "PEJ",
    ],
}

ORG_COUNTRY = {
    "DOE": "USA",
    "NRC": "USA",
    "KHNP": "Korea",
    "KEPCO": "Korea",
    "Rosatom": "Russia",
    "EDF": "France",
    "Orano": "France",
    "Framatome": "France",
    "CNNC": "China",
    "CGN": "China",
    "JAEA": "Japan",
    "Ontario Power Generation": "Canada",
    "Bruce Power": "Canada",
    "Polskie Elektrownie Jadrowe": "Poland",
}

ACTION_RULES = [
    ("started_construction", ["breaks ground", "construction begins"]),
    ("operating", ["commercial operation", "enters operation", "operates"]),
    ("approved", ["approves", "approved", "authorizes", "licensed", "grants"]),
    ("submitted", ["submit", "submitted", "files", "filed"]),
    ("proposed", ["proposes", "proposal"]),
    ("funded", ["funding", "funds", "awards"]),
    ("invested", ["invests", "investment", "financing"]),
    ("signed", ["signs", "signed", "agreement", "contract"]),
    ("started", ["begins", "starts", "commenced", "launches construction"]),
    ("completed", ["completes", "completed", "finishes"]),
    ("delayed", ["delays", "delayed", "postpones"]),
    ("cancelled", ["cancels", "cancelled", "canceled", "abandons"]),
    ("selected", ["selects", "selected", "chooses"]),
    ("partnered", ["partners", "partnership", "collaborates"]),
    ("testing", ["tests", "testing", "demonstration", "trial"]),
    ("expanding", ["expands", "expansion", "increases capacity"]),
    ("confirmed", ["confirms", "confirmed"]),
    ("announced", ["announces", "announced", "unveils", "launches"]),
    ("planning", ["planning", "plans", "aims", "seeks"]),
]

STATUS_BY_ACTION = {
    "planning": "planned",
    "proposed": "proposed",
    "submitted": "proposed",
    "approved": "approved",
    "funded": "funded",
    "invested": "funded",
    "signed": "contracted",
    "selected": "selected",
    "started_construction": "under_construction",
    "started": "in_progress",
    "testing": "testing",
    "operating": "operating",
    "completed": "completed",
    "delayed": "delayed",
    "cancelled": "cancelled",
    "expanding": "in_progress",
    "confirmed": "confirmed",
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


def is_unknown(value):
    if value is None:
        return True

    return str(value).strip().lower() in UNKNOWN_VALUES


def normalize_text(text):
    if text is None:
        return ""

    return re.sub(r"\s+", " ", str(text)).strip()


def normalize_for_match(text):
    normalized = normalize_text(text).lower()
    return re.sub(r"[^a-z0-9]+", " ", normalized)


def first_known(*values, default="unknown"):
    for value in values:
        if not is_unknown(value):
            return normalize_text(value)

    return default


def _has_phrase(text, phrase):
    if not phrase:
        return False

    pattern = r"(?<![a-z0-9])" + re.escape(phrase.lower()) + r"(?![a-z0-9])"
    return re.search(pattern, text.lower()) is not None


def _extract_matches(text, patterns):
    matches = []
    for canonical, aliases in patterns.items():
        if any(_has_phrase(text, alias) for alias in aliases):
            matches.append(canonical)

    return matches


def _join_unique(values):
    unique = []
    for value in values:
        if value and value not in unique:
            unique.append(value)

    return "; ".join(unique) if unique else "unknown"


def get_article_text(article):
    analysis = article.get("analysis", {})
    title = article.get("title", "")
    summary = analysis.get("summary") or ""
    return normalize_text(f"{title} {summary}")


def extract_organizations(text, article):
    analysis = article.get("analysis", {})
    article_org = analysis.get("organization")
    if not is_unknown(article_org):
        return normalize_text(article_org)

    return _join_unique(_extract_matches(text, ORGANIZATION_PATTERNS))


def extract_country(text, article, organizations=None):
    analysis = article.get("analysis", {})
    article_country = analysis.get("country")
    if not is_unknown(article_country):
        return normalize_text(article_country)

    countries = _extract_matches(text, COUNTRY_PATTERNS)

    if organizations and not is_unknown(organizations):
        for organization in organizations.split("; "):
            country = ORG_COUNTRY.get(organization)
            if country and country not in countries:
                countries.append(country)

    return countries[0] if countries else "unknown"


def extract_technologies(text, article):
    analysis = article.get("analysis", {})
    article_technology = analysis.get("technology")
    if not is_unknown(article_technology):
        return normalize_text(article_technology)

    return _join_unique(_extract_matches(text, TECHNOLOGY_PATTERNS))


def extract_action(text):
    normalized = normalize_for_match(text)
    for action, phrases in ACTION_RULES:
        if any(_has_phrase(normalized, phrase) for phrase in phrases):
            return action

    return "reported"


def extract_status(text, action):
    if "shutdown" in normalize_for_match(text) and action == "reported":
        return "unknown"

    return STATUS_BY_ACTION.get(action, "unknown")


def extract_fact_type(text, article, technology, action, status):
    analysis = article.get("analysis", {})
    article_category = analysis.get("category")
    if not is_unknown(article_category):
        normalized = normalize_for_match(article_category).replace(" ", "_")
        if normalized in FACT_TYPE_LABELS:
            return normalized

    normalized = normalize_for_match(text)
    technology_text = normalize_for_match(technology)

    if any(term in normalized for term in ["incident", "accident", "safety failure"]):
        return "incident"
    if any(term in normalized for term in ["license", "approval", "regulator", "nrc"]):
        return "regulation"
    if action in {"funded", "invested", "signed"}:
        return "investment"
    if any(term in normalized for term in ["investment", "funding", "contract", "financing"]):
        return "investment"
    if action in {"started_construction"}:
        return "construction"
    if any(term in normalized for term in ["construction", "build", "groundbreaking"]):
        return "construction"
    if status == "operating" or any(
        term in normalized
        for term in ["commercial operation", "startup", "grid connection"]
    ):
        return "operation"
    if any(
        term in technology_text or term in normalized
        for term in [
            "reprocessing",
            "mox",
            "repu",
            "enrichment",
            "conversion",
            "uranium",
            "nuclear fuel",
            "fuel cycle",
        ]
    ):
        return "fuel_cycle"
    if any(
        term in technology_text or term in normalized
        for term in ["spent fuel", "storage", "disposal", "waste"]
    ):
        return "waste_management"
    if any(term in normalized for term in ["decommissioning", "dismantling"]):
        return "decommissioning"
    if not is_unknown(technology) or any(
        term in normalized for term in ["reactor", "test", "demonstration", "development"]
    ):
        return "technology"
    if any(
        term in normalized
        for term in ["government", "policy", "strategy", "plan", "legislation"]
    ):
        return "policy"

    return "industry_signal"


def extract_subject(organization, country):
    if not is_unknown(organization):
        return organization
    if not is_unknown(country):
        return country
    return "Global nuclear industry"


def extract_object(title, subject, action):
    object_text = normalize_text(title)
    if not object_text:
        return "nuclear industry signal"

    subject_parts = []
    if not is_unknown(subject):
        subject_parts.extend(subject.split("; "))

    for subject_part in subject_parts:
        object_text = re.sub(
            r"(?i)\b" + re.escape(subject_part) + r"\b",
            "",
            object_text,
            count=1,
        )

    action_words = [action.replace("_", " ")]
    for rule_action, phrases in ACTION_RULES:
        if rule_action == action:
            action_words.extend(phrases)
    action_words.extend(["announces", "announced", "unveils", "launches"])

    for action_word in sorted(action_words, key=len, reverse=True):
        object_text = re.sub(
            r"(?i)\b" + re.escape(action_word) + r"\b",
            "",
            object_text,
            count=1,
        )

    object_text = object_text.replace("'", "").replace('"', "")
    object_text = object_text.strip(" :-,.")
    object_text = re.sub(r"(?i)^(and|to|for|on|the)\s+", "", object_text)
    object_text = normalize_text(object_text)

    return object_text or normalize_text(title)


def calculate_rule_confidence(
    country,
    technology,
    organization,
    action,
    status,
    fact_type,
    object_used_fallback,
):
    confidence = 0.4

    if not is_unknown(country):
        confidence += 0.1
    if not is_unknown(technology):
        confidence += 0.15
    if not is_unknown(organization):
        confidence += 0.15
    if action != "reported":
        confidence += 0.15
    if status != "unknown":
        confidence += 0.1
    if fact_type != "industry_signal":
        confidence += 0.1
    if not object_used_fallback:
        confidence += 0.1

    return round(min(max(confidence, 0.4), 0.9), 2)


def build_candidate_fact(article):
    text = get_article_text(article)
    title = normalize_text(article.get("title", ""))
    analysis = article.get("analysis", {})
    summary = first_known(analysis.get("summary"), title, default=title)

    organization = extract_organizations(text, article)
    country = extract_country(text, article, organization)
    technology = extract_technologies(text, article)
    action = extract_action(text)
    status = extract_status(text, action)
    fact_type = extract_fact_type(text, article, technology, action, status)
    category = FACT_TYPE_LABELS.get(fact_type, "Industry Signal")
    subject = extract_subject(organization, country)
    object_value = extract_object(title, subject, action)
    object_used_fallback = object_value == title

    return {
        "subject": subject,
        "action": action,
        "object": object_value,
        "fact_type": fact_type,
        "status": status,
        "country": country,
        "technology": technology,
        "organization": organization,
        "category": category,
        "importance": analysis.get("importance") or 3,
        "confidence": calculate_rule_confidence(
            country,
            technology,
            organization,
            action,
            status,
            fact_type,
            object_used_fallback,
        ),
        "summary": summary,
        "evidence_count": 1,
        "first_seen_at": article.get("published"),
        "last_seen_at": article.get("published"),
    }


def extract_candidate_fact_from_article(article):
    return build_candidate_fact(article)
