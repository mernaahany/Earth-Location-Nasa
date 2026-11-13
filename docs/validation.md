# Serper refactor validation

Executed on Python 3.10.2:

```text
python -m unittest discover -s tests -v
Ran 54 tests - OK
```

The suite is offline and spends no API credits. It covers request headers/body, timeouts, HTTP/API/malformed-response errors, credential precedence/redaction, disabled redirects, query context, filters, canonical deduplication, call budgets, pending evidence, numerical checks, ranking and feedback persistence. The Ellesmere CLI subprocess uses --offline and temporary output/storage.

A live test used the existing local credential and two calls. Sandboxed networking could not connect; the permitted outside-sandbox retry succeeded. The first mission's site search retained zero of eight results. Its target search retained three and rejected five. The second mission's two scopes were explicitly budget_exhausted.

The live output is examples/output.json. This smoke test demonstrates authentication, parsing and filtering, not scientific verification. Live results can change. No detection precision/recall or scientific accuracy metrics were inferred.
