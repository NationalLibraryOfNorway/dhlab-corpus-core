# DH-lab core API

The core of the DH-lab API — corpus building, concordances, collocations, word totals and n-grams — as a
FastAPI application.

- **v1** mirrors the corresponding endpoints of the current DH-lab API (same paths, same requests, same response
  shapes). It is mounted directly at the root, without a version prefix, so existing clients keep working unchanged.
- **v2**, under `/v2`, is the renewed API: row oriented responses, strict validation and explicit limits.

Experimental and non-core features of the current API (NER, geo data, image search, word bank, dispersion, …) are
deliberately left out.

## Setup

You need [python](https://www.python.org/) and [pdm](https://pdm-project.org/en/latest/).

```bash
pdm install
cp .env.example .env   # then adjust
```

Configuration is read from environment variables or `.env` (which is git-ignored, so paths and deployment details
stay out of the repository). See [`.env.example`](.env.example).

| Variable       | Default   | Meaning                                                                    |
|----------------|-----------|----------------------------------------------------------------------------|
| `DATABASE_DIR` | `./db/ft` | Directory with `urns.db`, `metadata.db`, `grand_total.db` and `alto_*.db`  |
| `MAX_WORKERS`  | `8`       | Maximum number of shards queried concurrently                              |
| `ROOT_PATH`    | *(empty)* | URL prefix when served behind a reverse proxy                              |

`grand_total.db` (word totals for the whole collection) is derived from the shards:

```bash
pdm run python scripts/make_grand_total.py <database_dir>
```

## Run

```bash
pdm run fastapi dev          # development, interactive docs at http://127.0.0.1:8000/docs
pdm run pytest tests         # tests, against the public domain test database in tests/data
```

## Code organisation

```
src/dhlab_core_api/
├── app.py          make_app(): wires config → repository → service → routers
├── config.py       settings from environment / .env
├── repository.py   database access: all SQL and knowledge of files and tables
├── service.py      business logic: sampling, limits, aggregation across shards
├── errors.py       errors that cross the layers
├── v1/             legacy API
│   ├── datatypes.py   request/response models (validation)
│   ├── legacy.py      legacy parameter semantics and pandas-shaped results
│   └── routes.py      REST endpoints
└── v2/             renewed API
    ├── datatypes.py   request/response models (validation)
    ├── mapping.py     translation between models and the service
    └── routes.py      REST endpoints
```

Routes only translate between HTTP and the service; the service never sees SQL or HTTP; the repository never sees
request models. Both API versions share the same service and repository.

Shards are queried concurrently in threads (SQLite releases the GIL), replacing the process pools of the old API.
All databases are opened read-only.

## Endpoints

| v1 (as in the current API)                                    | v2                      |
|---------------------------------------------------------------|-------------------------|
| `POST /build_corpus`                                       | `POST /v2/corpus`       |
| `POST /conc`, `POST /conccount`                         | `POST /v2/concordance`  |
| `POST /urncolldist`, `POST /urncolldist_urn`            | `POST /v2/collocations` |
| `GET /totals/{top_words}`                                  | `GET /v2/totals?limit=` |
| `POST /ngram_book`, `/ngram_periodicals`, `/ngram_newspapers` | `POST /v2/ngram`     |

### What v2 changes

- Responses are lists of records instead of pandas' `{column: {index: value}}` layout; empty metadata values are
  `null`. Collocations are returned as JSON, not as a JSON string inside JSON.
- Unknown fields, out-of-range values and missing corpora are rejected with `422` instead of being silently
  ignored or clamped. Malformed search expressions give `400` instead of `500`.
- Year ranges are inclusive in both ends; dates are ISO dates.
- Documents are identified by dhlabid: a corpus is given as `dhlabids` (v1 also accepts URNs). The URN is still part of
  the metadata that is returned.
- A corpus may hold at most 30 000 documents per request (v1 silently samples larger ones).
- Collocation windows stop at document boundaries, and collocates come with a plain mean distance.
- Random sampling (`corpus`, `concordance`) is reproducible when the request has a `seed`.
- One n-gram endpoint with a `doctype` parameter; one series per word.

### Where v1 differs from the current API

v1 keeps the current API's quirks where clients can observe them (e.g. `to_year` being exclusive when `from_year` is
also given, and collocations being a JSON string). The known differences:

- Invalid requests (wrong types, no corpus) give `422`, malformed search expressions `400` — both were `500`.
- `build_corpus` with no filters, or with only `limit`/`order_by`, returns documents instead of failing.
- `build_corpus` with a dotted `ddk` such as `"839.82"` works (the punctuation used to be stripped, so it never
  matched). Row indexes are always `0..n-1`.
- Collocation and n-gram requests that select no documents return an empty result instead of failing.
- `ngram_periodicals` honours `ddk`.
- N-grams are computed from `metadata_core` in `metadata.db` rather than the `metaindex_*` tables.
- `totals` reads `grand_total.db` as before; the file is now built by `scripts/make_grand_total.py`.

## Test database

See [tests/data/README.md](tests/data/README.md). It contains only documents in the public domain.
