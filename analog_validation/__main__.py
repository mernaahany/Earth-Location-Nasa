"""JSON file boundary for review and eventual application integration."""

import argparse
import json
from pathlib import Path

from .adapter import from_site_record
from .engine import validate
from .models import Constraint, Feature, Mission
from .retrieval import SearchFilters
from .serper import SerperSearch
from .store import Store


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate existing analog candidates; scores must be higher-is-better")
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--db", type=str)
    parser.add_argument("--query", help="Override the mission search query in the input JSON")
    parser.add_argument("--domains", nargs="+", help="Allowed source hostnames")
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--max-search-calls", type=int, default=8)
    parser.add_argument("--timeout", type=float, default=20)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--offline", action="store_true", help="Skip search explicitly; evidence remains unresolved")
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    missions = tuple(Mission(**{**m, "objectives": tuple(m["objectives"]),
                               "constraints": tuple(Constraint(**c) for c in m.get("constraints", []))})
                     for m in payload["missions"])
    requests = tuple(from_site_record(
        candidate["site"], target_id=payload["target"]["id"], body=payload["target"]["body"],
        query=args.query or payload.get("query", ""),
        missions=missions, original_similarity=candidate.get("original_similarity"),
        units=candidate.get("units"), metadata=candidate.get("metadata"),
        feature_contributions=candidate.get("feature_contributions"),
        correlations=tuple(candidate.get("correlations", [])),
        upstream_version=payload.get("upstream_version", "unspecified"),
        target_conditions=tuple(payload["target"].get("conditions", [])),
        target_features={k: Feature(**v) for k, v in payload["target"].get("features", {}).items()})
        for candidate in payload["candidates"])
    configured = payload.get("search", {})
    filters = SearchFilters(tuple(args.domains or configured.get("allowed_domains", SearchFilters().allowed_domains)), args.limit)
    budget = 0 if args.offline else args.max_search_calls
    try:
        provider = SerperSearch.from_env(args.env_file, timeout=args.timeout) if budget else None
        run = validate(requests, provider=provider, filters=filters, max_search_calls=budget)
    except ValueError as exc:
        parser.error(str(exc))
    if args.db:
        store = Store(args.db)
        try:
            store.save_run(run)
        finally:
            store.close()
    args.output.write_text(json.dumps(run, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")


if __name__ == "__main__":
    main()
