import re
from datetime import datetime
from email.utils import parsedate_to_datetime

from app.services.fact_extraction import is_unknown, normalize_text

ORGANIZATION_ALIASES = {
    "DOE": [
        "DOE",
        "US DOE",
        "U.S. DOE",
        "Department of Energy",
        "US Department of Energy",
        "United States Department of Energy",
    ],
    "NRC": [
        "NRC",
        "US NRC",
        "U.S. NRC",
        "Nuclear Regulatory Commission",
        "US Nuclear Regulatory Commission",
    ],
    "IAEA": ["IAEA", "International Atomic Energy Agency"],
    "KHNP": ["KHNP", "Korea Hydro & Nuclear Power", "Korea Hydro and Nuclear Power"],
    "KEPCO": ["KEPCO", "Korea Electric Power Corporation"],
    "EDF": ["EDF", "Electricite de France", "Electricité de France"],
    "Orano": ["Orano", "Orano Group"],
    "Rosatom": ["Rosatom", "ROSATOM", "State Atomic Energy Corporation Rosatom"],
    "Westinghouse": ["Westinghouse", "Westinghouse Electric Company"],
    "Holtec": ["Holtec", "Holtec International"],
    "Cameco": ["Cameco", "Cameco Corporation"],
    "Centrus": ["Centrus", "Centrus Energy"],
    "TerraPower": ["TerraPower", "Terra Power"],
    "X-energy": ["X-energy", "X Energy", "X-Energy"],
    "GE Hitachi": ["GE Hitachi", "GEH", "GE Hitachi Nuclear Energy"],
    "Rolls-Royce SMR": ["Rolls-Royce SMR", "Rolls Royce SMR", "Rolls-Royce"],
    "Framatome": ["Framatome"],
    "Urenco": ["Urenco", "URENCO"],
    "CNNC": ["CNNC", "China National Nuclear Corporation"],
    "CGN": ["CGN", "China General Nuclear"],
    "JAEA": ["JAEA", "Japan Atomic Energy Agency"],
    "MHI": ["Mitsubishi Heavy Industries", "MHI"],
    "OPG": ["Ontario Power Generation", "OPG"],
}

COUNTRY_ALIASES = {
    "USA": ["United States", "U.S.", "US", "USA", "America", "American"],
    "UK": ["United Kingdom", "UK", "Britain", "British"],
    "France": ["France", "French"],
    "Korea": ["South Korea", "Republic of Korea", "Korea", "Korean"],
    "China": ["China", "Chinese"],
    "Russia": ["Russia", "Russian"],
    "Japan": ["Japan", "Japanese"],
    "Canada": ["Canada", "Canadian"],
    "India": ["India", "Indian"],
    "Poland": ["Poland", "Polish"],
    "Ukraine": ["Ukraine", "Ukrainian"],
    "Czechia": ["Czech Republic", "Czechia", "Czech"],
    "Finland": ["Finland", "Finnish"],
    "Sweden": ["Sweden", "Swedish"],
    "Romania": ["Romania", "Romanian"],
    "UAE": ["United Arab Emirates", "UAE", "Emirati"],
    "Germany": ["Germany", "German"],
    "Belgium": ["Belgium", "Belgian"],
    "Netherlands": ["Netherlands", "Dutch"],
    "Switzerland": ["Switzerland", "Swiss"],
}

ACTION_ALIASES = {
    "approved": ["approved", "authorized", "authorised", "granted approval", "licensed", "permitted"],
    "planning": ["planning", "plans", "planned", "aims", "seeking", "intends"],
    "proposed": ["proposed", "submitted", "filed", "applied", "proposal submitted"],
    "announced": ["announced", "unveiled", "disclosed", "revealed"],
    "funded": ["funded", "financing approved", "grant awarded", "investment committed", "awarded funding"],
    "signed": ["signed", "contracted", "agreement signed", "entered agreement"],
    "selected": ["selected", "chosen", "designated", "awarded preferred bidder"],
    "partnered": ["partnered", "partnership", "collaborated", "cooperation agreement"],
    "started_construction": ["started_construction", "construction started", "broke ground", "groundbreaking", "began construction"],
    "testing": ["testing", "demonstrated", "trialled", "trialed", "began testing"],
    "operating": ["operating", "entered operation", "commercial operation", "commissioned", "grid connected"],
    "completed": ["completed", "finished", "delivered"],
    "delayed": ["delayed", "postponed", "deferred"],
    "cancelled": ["cancelled", "canceled", "abandoned", "terminated"],
    "expanding": ["expanding", "expansion", "increased capacity", "capacity expansion"],
    "confirmed": ["confirmed", "reaffirmed", "verified"],
    "reported": ["reported"],
}

TECHNOLOGY_ALIASES = {
    "SMR": ["SMR", "SMRs", "small modular reactor", "small modular reactors"],
    "TRISO": ["TRISO", "TRISO fuel", "tri-structural isotropic fuel", "tristructural isotropic fuel"],
    "Fast Reactor": ["fast reactor", "fast neutron reactor", "fast breeder reactor"],
    "Molten Salt Reactor": ["molten salt reactor", "MSR", "molten salt reactors"],
    "Reprocessing": ["reprocessing", "fuel reprocessing", "nuclear fuel reprocessing", "spent fuel reprocessing"],
    "Nuclear Fuel": ["nuclear fuel", "reactor fuel", "fuel fabrication"],
    "Uranium": ["uranium", "uranium mining", "uranium production", "uranium supply"],
    "HALEU": ["HALEU", "high-assay low-enriched uranium"],
    "LEU": ["LEU", "low-enriched uranium"],
    "MOX": ["MOX", "mixed oxide fuel"],
    "RepU": ["RepU", "reprocessed uranium"],
    "Enrichment": ["uranium enrichment", "enrichment"],
    "Conversion": ["uranium conversion", "conversion plant"],
    "Spent Fuel": ["spent fuel", "spent nuclear fuel", "used nuclear fuel"],
    "Dry Storage": ["dry storage", "dry cask storage", "spent fuel dry storage"],
    "Geological Disposal": ["geological disposal", "deep geological repository", "final repository"],
    "Waste Management": ["nuclear waste management", "radioactive waste management"],
    "Fusion": ["fusion", "nuclear fusion"],
    "AP1000": ["AP1000"],
    "APR1400": ["APR1400", "APR-1400"],
    "EPR": ["EPR"],
    "BWRX-300": ["BWRX-300", "BWRX 300"],
    "Natrium": ["Natrium"],
    "NuScale": ["NuScale"],
    "CANDU": ["CANDU"],
    "PWR": ["PWR"],
    "BWR": ["BWR"],
    "HTGR": ["HTGR"],
    "Microreactor": ["Microreactor", "Micro-reactor"],
}

GENERIC_SUBJECTS = {"global nuclear industry", "nuclear industry", "industry"}
OBJECT_STOPWORDS = {
    "the", "a", "an", "of", "for", "to", "in", "on", "with", "and",
    "new", "project", "programme", "program", "large", "high", "capacity",
}


def _normalize_match_text(value):
    return re.sub(r"[^a-z0-9]+", " ", normalize_text(value).lower()).strip()


def _alias_lookup(value, alias_map):
    normalized = _normalize_match_text(value)
    if not normalized:
        return None
    for canonical, aliases in alias_map.items():
        if normalized == _normalize_match_text(canonical):
            return canonical
        if any(normalized == _normalize_match_text(alias) for alias in aliases):
            return canonical
    return None


def _split_multi_value(value):
    if is_unknown(value):
        return []
    return [part.strip() for part in str(value).split(";") if part.strip()]


def _normalize_multi_value(value, alias_map):
    values = []
    for part in _split_multi_value(value):
        canonical = _alias_lookup(part, alias_map) or normalize_text(part)
        if canonical not in values:
            values.append(canonical)
    return sorted(values, key=str.lower)


def normalize_fact_organization(value):
    return _normalize_multi_value(value, ORGANIZATION_ALIASES)


def normalize_fact_technology(value):
    return _normalize_multi_value(value, TECHNOLOGY_ALIASES)


def normalize_fact_country(value):
    if is_unknown(value):
        return "unknown"
    return _alias_lookup(value, COUNTRY_ALIASES) or normalize_text(value)


def normalize_fact_action(value):
    if is_unknown(value):
        return "reported"
    canonical = _alias_lookup(value, ACTION_ALIASES)
    return canonical or _normalize_match_text(value).replace(" ", "_") or "reported"


def normalize_fact_subject(fact):
    organizations = normalize_fact_organization(fact.get("organization"))
    if organizations:
        return "; ".join(organizations)

    country = normalize_fact_country(fact.get("country"))
    if country != "unknown":
        return country

    subject = normalize_text(fact.get("subject"))
    if _normalize_match_text(subject) in GENERIC_SUBJECTS or not subject:
        return "Global nuclear industry"

    subject_orgs = normalize_fact_organization(subject)
    if subject_orgs:
        return "; ".join(subject_orgs)
    return _alias_lookup(subject, COUNTRY_ALIASES) or subject


def _replace_technology_aliases(text):
    output = text
    for canonical, aliases in sorted(TECHNOLOGY_ALIASES.items(), key=lambda item: -len(item[0])):
        for alias in sorted(aliases, key=len, reverse=True):
            output = re.sub(
                r"(?i)(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])",
                canonical,
                output,
            )
    return output


def _remove_alias_tokens(text, values, alias_map):
    output = text
    for value in values:
        aliases = alias_map.get(value, [value]) + [value]
        for alias in sorted(aliases, key=len, reverse=True):
            output = re.sub(
                r"(?i)(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])",
                " ",
                output,
            )
    return output


def normalize_fact_object(fact):
    text = normalize_text(fact.get("object"))
    if not text:
        return ""

    technologies = normalize_fact_technology(fact.get("technology"))
    organizations = normalize_fact_organization(fact.get("organization"))
    country = normalize_fact_country(fact.get("country"))
    action = normalize_fact_action(fact.get("action"))

    text = _replace_technology_aliases(text)
    text = _remove_alias_tokens(text, organizations, ORGANIZATION_ALIASES)
    if country != "unknown":
        text = _remove_alias_tokens(text, [country], COUNTRY_ALIASES)

    action_aliases = ACTION_ALIASES.get(action, [action]) + [action.replace("_", " ")]
    for alias in sorted(action_aliases, key=len, reverse=True):
        text = re.sub(
            r"(?i)(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])",
            " ",
            text,
        )

    clean_tokens = []
    text = text.replace("-", " ")
    for token in re.findall(r"[A-Za-z0-9]+", text):
        if token.lower() in OBJECT_STOPWORDS:
            continue
        clean_tokens.append(token)

    normalized = " ".join(clean_tokens)
    normalized = normalized.replace("facility", "plant")
    normalized = normalized.replace("fuel demonstration", "demonstration")
    normalized = normalized.replace("demonstration project", "demonstration")
    normalized = normalized.replace("project proposal", "proposal")
    normalized = re.sub(r"\s+", " ", normalized).strip()

    for technology in technologies:
        if technology in normalized:
            normalized = normalized.replace(technology, technology)

    return normalized


def normalize_fact_time(value):
    if not value:
        return None
    try:
        if "," in value:
            return parsedate_to_datetime(value).date().isoformat()
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date().isoformat()
    except (TypeError, ValueError, IndexError):
        return None


def build_canonical_fact_signature(fact):
    subject = normalize_fact_subject(fact)
    action = normalize_fact_action(fact.get("action"))
    technologies = normalize_fact_technology(fact.get("technology"))
    organizations = normalize_fact_organization(fact.get("organization"))
    country = normalize_fact_country(fact.get("country"))
    normalized_object = normalize_fact_object(fact)
    time_value = normalize_fact_time(fact.get("first_seen_at") or fact.get("last_seen_at"))

    signature_key = "|".join(
        [
            subject,
            action,
            normalized_object,
            ";".join(technologies),
            country,
        ]
    )

    return {
        "subject": subject,
        "action": action,
        "object": normalized_object,
        "country": country,
        "technologies": technologies,
        "organizations": organizations,
        "fact_type": fact.get("fact_type") or "industry_signal",
        "status": fact.get("status") or "unknown",
        "time": time_value,
        "signature_key": signature_key,
    }
