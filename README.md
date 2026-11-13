# Search-driven Earth-Moon-Mars validation

Validation now searches with **Serper** using the user query, mission, Earth site and planetary context. The curated knowledge module and `facts=` API have been removed. Original similarity scores, deterministic constraints and feedback persistence remain intact.

## Run

Python 3.10+; no external runtime dependencies. Set `SERPER_API_KEY` in your environment or a local `.env`. The existing `SEARCH_API` name is supported. Environment values override file values; keys are never placed in output. Git ignores `.env` files.

```powershell
python -m analog_validation examples/ellesmere.json --output examples/output.json
```

Override query and filters:

```powershell
python -m analog_validation examples/ellesmere.json --query "polar rover terrain and ice field testing" --domains nasa.gov esa.int usgs.gov --limit 8 --max-search-calls 8 --timeout 20 --output examples/output.json --db validation.sqlite
```

Offline validation and tests:

```powershell
python -m unittest discover -s tests -v
python -m analog_validation examples/ellesmere.json --offline --output examples/offline-output.json
```

The example's missions and target are illustrative. Its original score, feature units and equipment limits were not supplied; they remain unknown.

## Python integration

```python
from analog_validation import SerperSearch, SearchFilters, from_site_record, validate
from analog_validation.models import Mission

request = from_site_record(
    existing_site_record,
    query="polar rover terrain analog validation",
    target_id="selected-target-id",
    body="moon",
    target_conditions=("polar",),
    missions=(Mission("navigation-test", ("navigation",)),),
    original_similarity=existing_score,
)
run = validate(
    (request,),
    provider=SerperSearch.from_env(),
    filters=SearchFilters(("nasa.gov", "esa.int", "usgs.gov"), limit=8),
    max_search_calls=8,
)
```

Without a provider, `validate` automatically creates `SerperSearch.from_env()` when its budget is positive. A missing key fails explicitly. Set `max_search_calls=0` to deliberately skip search. The original application/API was not supplied and still needs integration.

Breaking changes: the adapter requires `query`; `validate(facts=...)` is removed. Runs replace KB snapshots with `retrieval_mode`, `search_filters`, `search_reports`, `search_digest` and `pending_evidence`. Old SQLite run snapshots remain readable.

## Search and filtering

Each site/mission produces two scopes:

1. Earth-site search: user query + site name + mission terms + allowed source domains.
2. Planetary-target search: user query + Moon/Mars synonyms + target conditions + mission terms + allowed source domains.

This avoids requiring one page to discuss both an Earth location and its planetary counterpart. Mission IDs stay in reports rather than becoming arbitrary query terms. Site names and query text are sent to Serper; raw feature values and equipment dictionaries are not. Keep secrets and private details out of the query.

The client uses `POST https://google.serper.dev/search`, JSON `q` and `num`, and an `X-API-KEY` header. It reads organic title/link/snippet/position records and adds UTC timestamps. See the official [Serper service](https://serper.dev/) and [playground](https://serper.dev/playground).

Local filtering applies even when the query uses site operators:

- HTTPS URLs must match an exact allowed host or subdomain. Lookalikes, URL credentials and nonstandard ports are rejected.
- Title/snippet must mention at least one selected mission term.
- Target results must also mention the requested planet or its synonym.
- Site results must mention the site name or ID.
- Canonical URLs remove tracking parameters and fragments for deduplication.

The objective vocabulary covers navigation, solar power, dust mitigation, ice extraction, thermal testing, habitats, geology and astrobiology. Unknown objectives use their text. These are search terms, not scientific facts. Lexical filtering may miss synonyms, full-text-only mentions or other languages; empty results are reported explicitly.

Default budget: eight actual calls across the run (configurable 0-32), up to eight results per call (configurable 1-10), 20-second timeout (maximum 60). Identical queries within a scope share a per-run cache. Budgets apply in input order. Exhaustion, errors and empty results appear in reports. No automatic retries, hidden pagination or fallback KB.

## Scientific safeguards

Every search result remains `pending_review`, even when a custom provider labels it verified. Search relevance is not scientific verification. Findings cite the source and require full-source inspection; snippets cannot generate numerical thresholds, score penalties or simulation claims. Full-page extraction/verification is not implemented.

Numerical checks compare referenced mission limits against unit-aware measurement intervals. Inputs require units, source, observation period and absolute uncertainty bounds. Coarse terrain cannot confirm a fine-scale violation. Missing values never become zero. Scores must be comparable and higher-is-better within a shared target/configuration.

Nominal ranking moves confirmed hard violations behind other candidates while preserving scores; stress-test order is preserved. Suitability and other calibrated scientific scores remain null without a justified transformation. Search and unresolved states cannot certify physical equivalence.

## Persistence and scope

Runs save input snapshots, reports, timestamps, filters, evidence, calculations and ranking reasons. The search digest fingerprints captured reports; future live results and timestamps may differ. `Store` persists feedback and referenced reviews without silently rewriting facts or scores. Host authentication is still required.

No traction, energy-generation, shadowing, communications, crater or autonomous-learning model is bundled. These require validated models and expert evaluation.

See [requirements](docs/requirements.md), [source notes](docs/sources.md) and [validation](docs/validation.md).
