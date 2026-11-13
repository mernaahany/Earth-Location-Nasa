"""Query and mission driven search, with explicit source and relevance filtering."""

from dataclasses import dataclass, replace
from hashlib import sha256
import re
from typing import Literal, Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .models import Mission, SearchEvidence, ValidationRequest

OBJECTIVE_TERMS = {
    "navigation": ("navigation", "rover", "traversability", "mobility", "terrain"),
    "solar_power": ("solar", "power", "energy", "panel", "battery"),
    "dust_mitigation": ("dust", "regolith", "abrasion", "electrostatic"),
    "ice_extraction": ("ice", "water", "excavation", "drilling", "volatile"),
    "thermal": ("thermal", "temperature", "cryogenic", "heat"),
    "habitat": ("habitat", "habitation", "radiation", "life support"),
    "geology": ("geology", "geological", "mineral", "rock", "regolith", "sampling"),
    "astrobiology": ("astrobiology", "biosignature", "contamination", "microbial"),
}
BODY_TERMS = {"moon": ("moon", "lunar"), "mars": ("mars", "martian")}


@dataclass(frozen=True)
class SearchFilters:
    allowed_domains: tuple[str, ...] = ("nasa.gov", "esa.int", "usgs.gov")
    limit: int = 8

    def __post_init__(self):
        if isinstance(self.limit, bool) or not isinstance(self.limit, int) or not 1 <= self.limit <= 10:
            raise ValueError("Search result limit must be in [1, 10]")
        if not self.allowed_domains or len(self.allowed_domains) > 10:
            raise ValueError("Supply 1–10 allowed source domains")
        if any(not re.fullmatch(r"(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}", d)
               for d in self.allowed_domains):
            raise ValueError("Allowed domains must be lowercase hostnames, without schemes or paths")


class SearchProvider(Protocol):
    def search(self, query: str, *, limit: int) -> list[SearchEvidence]: ...


class SearchError(Exception):
    """Safe provider error; never include credentials or authenticated response bodies."""


def canonical_url(value: str, domains: tuple[str, ...]) -> str | None:
    try:
        url = urlsplit(value)
        host = (url.hostname or "").lower().rstrip(".")
        if (url.scheme != "https" or url.username or url.password or url.port not in (None, 443)
                or not any(host == d or host.endswith("." + d) for d in domains)):
            return None
        query = urlencode([(k, v) for k, v in parse_qsl(url.query, keep_blank_values=True)
                           if not k.lower().startswith("utm_") and k.lower() not in ("gclid", "fbclid")])
        return urlunsplit(("https", host, url.path or "/", query, ""))
    except ValueError:
        return None


def contains(text: str, terms: tuple[str, ...]) -> bool:
    return any(re.search(r"\b" + re.escape(term) + r"\b", text, re.IGNORECASE) for term in terms)


def mission_terms(mission: Mission) -> tuple[str, ...]:
    return tuple(dict.fromkeys(term for objective in mission.objectives
                               for term in OBJECTIVE_TERMS.get(objective, (objective.replace("_", " "),))))


def build_query(request: ValidationRequest, mission: Mission, scope: str, filters: SearchFilters) -> str:
    context = (request.original_payload.get("name", request.site_id) if scope == "earth_site"
               else f"({' OR '.join(BODY_TERMS[request.body])}) {' '.join(request.target_conditions)}")
    objectives = " OR ".join(mission_terms(mission))
    domains = " OR ".join(f"site:{domain}" for domain in filters.allowed_domains)
    return f"{' '.join(request.query.split())} {context} ({objectives}) ({domains})"


def retrieve(request: ValidationRequest, mission: Mission, scope: Literal["earth_site", "planetary_target"],
             provider: SearchProvider, filters: SearchFilters) -> dict:
    query = build_query(request, mission, scope, filters)
    report = {"site_id": request.site_id, "mission_id": mission.id, "scope": scope,
              "query": query, "status": "ok", "evidence": [], "rejected": 0}
    try:
        candidates = provider.search(query, limit=filters.limit)
    except (SearchError, TimeoutError, ConnectionError, OSError) as exc:
        report.update(status="search_failed", error=str(exc) if isinstance(exc, SearchError)
                      else f"Search failed: {type(exc).__name__}")
        return report
    seen = set()
    site = request.original_payload.get("name", request.site_id)
    for candidate in candidates[:filters.limit]:
        url = canonical_url(candidate.source_url, filters.allowed_domains)
        text = f"{candidate.title} {candidate.snippet}"
        relevant = contains(text, mission_terms(mission))
        if scope == "planetary_target":
            relevant = relevant and contains(text, BODY_TERMS[request.body])
        else:
            relevant = relevant and contains(text, (site, request.site_id))
        if not url or url in seen or not relevant:
            report["rejected"] += 1
            continue
        seen.add(url)
        report["evidence"].append(replace(candidate, id=sha256(url.encode()).hexdigest()[:20], source_url=url, query=query,
                                           verification_status="pending_review"))
    if not report["evidence"]:
        report["status"] = "no_matching_evidence"
    return report
