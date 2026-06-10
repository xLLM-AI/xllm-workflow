# Accuracy Artifact Schema

Accuracy validation should preserve enough evidence to distinguish model
quality, sampling randomness, request formatting, and framework regressions.

Recommended directory:

```text
runs/accuracy/<run_id>/
  manifest.md
  request_config.json
  dataset_config.json
  raw_predictions.jsonl
  failed_cases.jsonl
  score.json
  report.md
  service_log_excerpt.txt
```

Validation levels:

| Level | Scope | Purpose |
|---|---|---|
| L1 | One prompt | Check whether output is readable and on-topic |
| L2 | 5-10 deterministic prompts | Smoke test obvious precision regressions |
| L3 | Dataset subset first N cases | Find stable bad cases for A/B |
| L4 | One full task | Validate localized regression, such as one CEval category |
| L5 | Full dataset | Final merge or release evidence |

`request_config.json` should include:

```json
{
  "api_url": "",
  "model": "",
  "temperature": 0.0,
  "top_p": null,
  "top_k": null,
  "max_tokens": null,
  "stream": true,
  "seed": null,
  "extra_body": {}
}
```

`score.json` should include:

```json
{
  "run_id": "",
  "dataset": "",
  "subsets": [],
  "limit": null,
  "num_total": null,
  "num_correct": null,
  "score": null,
  "failed_case_count": null,
  "status": "pass"
}
```

Rules:

- Deterministic regression checks should prefer `temperature=0.0`; if sampling
  is required by the benchmark, record `top_p`, `top_k`, seed, and decoding
  template details.
- Keep raw predictions and failed cases. A single stable bad case is often more
  useful than a large score table.
- Do not upgrade L1/L2 smoke results into a full precision conclusion.
