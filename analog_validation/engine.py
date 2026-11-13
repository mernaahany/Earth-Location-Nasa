"""Post-score orchestration. Unknowns remain unknown and scores stay upstream-owned."""

from dataclasses import asdict
from hashlib import sha256
import json
from uuid import uuid4

from .models import (ConflictFinding, MissionValidationResult, RankingAdjustment,
                     ValidationRequest)
from .retrieval import SearchFilters, SearchProvider, build_query, retrieve
from .serper import SerperSearch
from .tools import TOOLS

ENGINE_VERSION = "2-serper"


def validate(requests: tuple[ValidationRequest, ...], *, provider: SearchProvider | None = None,
             filters: SearchFilters | None = None, max_search_calls: int = 8) -> dict:
    if not requests or len({r.site_id for r in requests}) != len(requests):
        raise ValueError("Provide nonempty unique site records")
    if isinstance(max_search_calls, bool) or not isinstance(max_search_calls, int) or not 0 <= max_search_calls <= 32:
        raise ValueError("Search call budget must be in [0, 32]")
    filters = filters or SearchFilters()
    # Ranking is valid only within the same target and exact mission configuration.
    target_contexts = {json.dumps({"id": r.target_id, "body": r.body, "features":
                                   {k: asdict(v) for k, v in r.target_features.items()},
                                   "conditions": sorted(r.target_conditions)}, sort_keys=True) for r in requests}
    if len(target_contexts) != 1:
        raise ValueError("Batch ranking requires identical target context")
    configurations = {}
    for request in requests:
        for mission in request.missions:
            config = json.dumps(asdict(mission), sort_keys=True, allow_nan=False)
            if mission.id in configurations and configurations[mission.id] != config:
                raise ValueError("Same mission ID has inconsistent configurations")
            configurations[mission.id] = config
    if provider is None and max_search_calls:
        provider = SerperSearch.from_env()
    results, pending, search_calls, search_reports = [], {}, 0, []
    cache = {}
    for request in requests:
        for mission in request.missions:
            findings, missing = [], list(request.original_payload.get("missing", []))
            def add(category, claim, *, status="insufficient_evidence", mechanism="Missing or inadequate measurement provenance.",
                    path="review", sources=(), evidence_ids=(), required=(), limitations="No numeric adjustment is justified.",
                    action="Obtain the missing evidence and revalidate.", calculation=None, simulation=None,
                    hard=False, applicability="Selected site and mission."):
                findings.append(ConflictFinding(
                    f"{request.site_id}:{mission.id}:{len(findings) + 1}", mission.id, request.body,
                    category, path, status, claim, mechanism, applicability, sources, evidence_ids,
                    required, limitations, "mission_suitability; stress-test value needs separate evaluation",
                    action, calculation, simulation, hard))

            for scope in ("earth_site", "planetary_target"):
                query = build_query(request, mission, scope, filters)
                key = (scope, query)
                if key in cache:
                    report = {**cache[key], "site_id": request.site_id, "mission_id": mission.id}
                elif search_calls < max_search_calls:
                    search_calls += 1
                    report = retrieve(request, mission, scope, provider, filters)
                    cache[key] = report
                else:
                    report = {"site_id": request.site_id, "mission_id": mission.id, "scope": scope,
                              "query": query, "status": "budget_exhausted", "evidence": [], "rejected": 0}
                search_reports.append({**report, "evidence": [asdict(e) for e in report["evidence"]]})
                if report["status"] != "ok":
                    add("insufficient_evidence", f"{scope}: {report.get('error', report['status'])}",
                        action="Refine the query, source filters, or search budget, then rerun.")
                for evidence in report["evidence"]:
                    pending[evidence.source_url] = asdict(evidence)
                    add("search_evidence", f"Search candidate: {evidence.title}", status="requires_review",
                        sources=(evidence.source_url,), evidence_ids=(evidence.id,),
                        applicability=f"{scope}; mission {mission.id}.",
                        mechanism="Search relevance is not scientific verification.",
                        limitations="Search snippet only; the underlying source has not been verified.",
                        action="Inspect the cited source and verify mechanism, measurement scope, and mission applicability.")

            for name, feature in request.earth_features.items():
                absent = [key for key, value in (("source", feature.source), ("unit", feature.unit),
                                                 ("uncertainty", feature.uncertainty), ("period", feature.period))
                          if value is None or value == ""]
                if absent:
                    fields = tuple(f"{name}.{field}" for field in absent)
                    missing.extend(fields)
                    add("data_quality_conflict", f"Incomplete metadata for {name}.", required=fields)
                if mission.required_resolution_m is not None and name.startswith("terrain."):
                    if feature.resolution_m is None or feature.resolution_m > mission.required_resolution_m:
                        add("data_quality_conflict", f"{name} does not resolve the required mission scale.",
                            required=(f"terrain resolution <= {mission.required_resolution_m} m",))
            if request.original_payload.get("sar"):
                add("data_quality_conflict", "SAR browse texture is contextual, not a calibrated local backscatter measurement.",
                    limitations=request.original_payload["sar"].get("uncertainty", "Calibration and AOI support require verification."),
                    action="Obtain calibrated geolocated AOI data before using SAR as a physical measurement.")
            if "thermal" in mission.objectives and "climate.tempMean" in request.earth_features:
                add("data_quality_conflict", "Climate mean temperature cannot establish surface thermal extrema.",
                    required=("surface thermal cycle", "equipment operating limits"),
                    action="Obtain surface temperature observations and a mission-specific thermal model.")
            if "ice_extraction" in mission.objectives and "ice" in request.original_payload.get("tags", []):
                add("insufficient_evidence", "The site ice tag is not a local ice abundance or accessibility measurement.",
                    required=("local ice assay", "depth profile", "access route"))
            if len(request.missions) > 1:
                add("mission_compatibility", "Independent mission checks do not establish compatibility of shared-site operations.",
                    status="potential_conflict", required=("cross-mission operating and contamination requirements",),
                    action="Review operational interactions before scheduling simultaneous tests.")
            if request.correlations:
                add("correlation_mismatch", "Feature correlation alone does not establish a causal physical mechanism.",
                    status="potential_conflict", action="Validate each relationship using a scoped physical model or experiment.")
            for item in missing[:]:
                # Preserve upstream known gaps explicitly; never convert them into numeric zeros.
                if item in request.original_payload.get("missing", []):
                    add("insufficient_evidence", f"Upstream evidence gap: {item}", required=(item,))
            if not mission.constraints:
                missing.append("mission-specific referenced equipment constraints")
                add("insufficient_evidence", "No numerical mission constraints supplied.",
                    required=("mission-specific referenced equipment constraints",))
            for constraint in mission.constraints:
                features = request.earth_features if constraint.domain == "earth" else request.target_features
                feature = features.get(constraint.feature)
                if (feature is not None and constraint.feature.startswith("terrain.")
                        and mission.required_resolution_m is not None
                        and (feature.resolution_m is None or feature.resolution_m > mission.required_resolution_m)):
                    feature = None  # A coarse sample cannot confirm a fine-scale hard violation.
                calculation = TOOLS["constraint_interval_v1"](feature, constraint)
                missing.extend(calculation.missing)
                add("numeric_constraint", f"{constraint.id}: {calculation.outcome}",
                    path="quantitative", status=calculation.status, calculation=calculation,
                    mechanism="Bounded measurement interval compared to a configured mission requirement.",
                    applicability=f"{constraint.domain} domain; mission {mission.id}, version {mission.version}.",
                    sources=(constraint.source,), required=(constraint.feature,),
                    hard=constraint.hard and calculation.outcome == "fail",
                    action="Inspect margin bounds and configured mission limit.")
            hard_failure = any(f.hard_violation for f in findings)
            unresolved = any(f.status in ("insufficient_evidence", "requires_review", "potential_conflict") for f in findings)
            eligibility = "violates_constraints" if hard_failure else "unresolved" if unresolved else "within_checked_constraints"
            results.append(MissionValidationResult(
                request.site_id, mission.id, request.original_similarity, None, None, None,
                "requires_review" if hard_failure else "insufficient_evidence" if eligibility == "unresolved" else "model_predicted",
                eligibility, findings, sorted(set(missing))))
    for mission_id in sorted(configurations):
        group = [r for r in results if r.mission_id == mission_id]
        # This adapter requires higher-is-better scores. Missing scores retain input order.
        before = sorted(group, key=lambda r: (r.original_similarity is None,
                                              -(r.original_similarity or 0)))
        original_ranks = {r.site_id: index for index, r in enumerate(before, 1)}
        purpose = json.loads(configurations[mission_id])["purpose"]
        after = sorted(before, key=lambda r: purpose == "nominal" and r.eligibility == "violates_constraints")
        for index, result in enumerate(after, 1):
            result.ranking = RankingAdjustment(
                "hard_constraint_partition_v1" if purpose == "nominal" else "preserve_stress_test_order_v1",
                "Nominal policy places confirmed hard violations after other candidates; unresolved means unvalidated."
                if purpose == "nominal" else "Stress-test order preserved; a hazard is not an automatic penalty.",
                original_ranks[result.site_id], index,
                "Intervals crossing a limit remain unknown. Within each group the original order is stable; no score penalty.")
    search_digest = sha256(json.dumps(search_reports, sort_keys=True).encode()).hexdigest()
    return {
        "run_id": str(uuid4()), "engine_version": ENGINE_VERSION, "retrieval_mode": "serper_search",
        "search_digest": search_digest, "search_filters": asdict(filters), "search_reports": search_reports,
        "input_snapshot": [asdict(r) for r in requests],
        "search_calls": search_calls, "pending_evidence": list(pending.values()),
        "results": [asdict(r) for r in results],
    }
