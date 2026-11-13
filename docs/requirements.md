# Serper refactor requirement coverage

| Requirement | Implementation and reason | Validation |
|---|---|---|
| Search instead of KB | Removed knowledge.py, ScientificFact, seed retrieval and facts=; search is the default path. | No runtime seed imports. |
| Query and mission | Required query plus objective vocabulary and mission-linked reports. | Query context and mission filtering tests. |
| Earth and planetary matching | Separate site and target scopes. | Site/body relevance tests. |
| Serper | Standard-library POST client, typed organic results, timeout and size bounds. | Mocked protocol tests and successful live smoke run. |
| Source filtering | JSON/CLI/Python allowed domains; strict local URL checks. | Lookalike host, scheme, port and credential tests. |
| No duplicates | URL normalization, per-search/run deduplication and query cache. | Tracking URL duplicate tests. |
| Bounded calls | Explicit budgets, empty/error/exhausted statuses; no retries. | Call-budget and error tests. |
| Scientific safeguards | Pending-review snippets never become engineering thresholds. | Spoofed verification and malicious snippet tests. |
| Preserve scores and feedback | Existing deterministic numerical checks, ranking and SQLite flow retained. | Regression, persistence and CLI tests. |
| Credentials | Environment/.env loading, SEARCH_API compatibility, safe errors and blocked redirects. | Precedence, redaction and redirect tests. |

Remaining scope: full-page scientific verification, physical simulators, independent expert evaluation and the unavailable original application/API integration. Search candidates alone cannot establish analog equivalence. Routing examples are guidance, not evidence or an independent evaluation dataset.
