"""Adapter for the supplied Earth-site record; never infer units or similarity."""

from copy import deepcopy
from typing import Any

from .models import Feature, Mission, ValidationRequest, finite


def from_site_record(record: dict[str, Any], *, target_id: str, body: str,
                     query: str,
                     missions: tuple[Mission, ...], original_similarity: float | None = None,
                     units: dict[str, str] | None = None,
                     target_features: dict[str, Feature] | None = None,
                     metadata: dict[str, dict[str, Any]] | None = None,
                     feature_contributions: dict[str, float] | None = None,
                     correlations: tuple[dict[str, Any], ...] = (),
                     target_conditions: tuple[str, ...] = (),
                     upstream_version: str = "unspecified") -> ValidationRequest:
    units, metadata = units or {}, metadata or {}
    lat, lon = record["lat"], record["lon"]
    finite(lat)
    finite(lon)
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ValueError("Invalid site coordinates")
    features = {}
    for group in ("climate", "terrain"):
        evidence = record.get("evidence", {}).get(group, {})
        for name, value in record.get(group, {}).items():
            key = f"{group}.{name}"
            features[key] = Feature(
                value=value, unit=units.get(key), source=evidence.get("source", ""),
                quality=evidence.get("class", ""), limitations=evidence.get("uncertainty", ""),
                **metadata.get(key, {}))
    return ValidationRequest(
        site_id=record["id"], geometry={"type": "Point", "coordinates": [lon, lat]},
        target_id=target_id, body=body, missions=missions,
        original_similarity=original_similarity, earth_features=features,
        target_features=target_features or {}, feature_contributions=feature_contributions or {},
        correlations=correlations, original_payload=deepcopy(record), upstream_version=upstream_version,
        target_conditions=target_conditions, query=query)
