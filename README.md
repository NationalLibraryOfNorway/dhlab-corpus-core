# DH-lab core API

The core of the DH-lab API — corpus building, concordances, collocations, word totals and n-grams — as a
FastAPI application.

- **v1** mirrors the corresponding endpoints of the current DH-lab API (same paths, same requests, same response
  shapes). It is mounted directly at the root, without a version prefix, so existing clients keep working unchanged.
- **v2**, under `/v2`, is the renewed API: row oriented responses, strict validation and explicit limits.

Experimental and non-core features of the current API (NER, geo data, image search, word bank, dispersion, …) are
deliberately left out.

## Differences from the current DH-lab API

**What is the same:** the core endpoints are available at the same paths, take the same requests and return the
same response shapes, so existing clients can use this API without changes.

**What is different:**

- **Scope.** Only the core functionality is included. Experimental and unrelated endpoints are gone.
- **Validation.** Requests are validated before anything is run. Invalid input gives a `422` that says what is
  wrong, and a malformed search expression gives a `400`; the current API answers `500` in both cases.
- **A new version alongside the old.** The endpoints under `/v2` return lists of records instead of pandas-style
  tables, identify documents by dhlabid, reject out-of-range values instead of silently adjusting them, and can
  give reproducible samples with a `seed`.
- **Code.** FastAPI instead of Flask, with database access, business logic and REST endpoints in separate layers.
  Shards are queried in threads rather than process pools, and pandas is no longer a dependency.
- **Configuration.** Settings come from environment variables or a git-ignored `.env` file, not from a
  `config.py` in the repository.
- **Tests.** An automated test suite runs against a small public domain test database.

The details are listed under [Endpoints](#endpoints).

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
├── v1/             same API as the current one
│   ├── datatypes.py   request/response models (validation)
│   ├── legacy.py      v1 parameter semantics and pandas-shaped results
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

## Databases

The collection is a set of read-only SQLite files in `DATABASE_DIR`. The API uses these tables:

| File             | Table               | Contents                                                                         |
|------------------|---------------------|----------------------------------------------------------------------------------|
| `urns.db`        | `urns`              | One row per document: dhlabid (`urn_seq`), URN, doctype and its shard (`db_path`) |
| `metadata.db`    | `metadata_core`     | One row per document: dhlabid, URN, title, authors, year, publisher, …           |
|                  | `metadata_core_fts` | The same metadata as a full-text (FTS5) index, used for building corpora          |
| `alto_<from>_<to>.db` | `ft`           | The text, one row per token in reading order; used for collocations               |
|                  | `ft_para`           | Full-text index with one row per paragraph; used for concordances                 |
|                  | `ft_para_trigram`   | Character trigram version of `ft_para` (not present in every shard)               |
|                  | `ft_doc_metadata`   | Full-text index of each document's text together with its metadata; used when a corpus is built with a `fulltext` filter |
|                  | `unigram`           | Frequency of each word per document; used for n-grams                             |
|                  | `totals`            | Frequency of each word in the shard; source for `grand_total.db`                  |
| `grand_total.db` | `grand_total`       | Frequency of each word in the whole collection; used for totals                   |

Each `alto_*.db` file is a *shard* holding the documents with dhlabids in the range given by its name. The shards
contain a few more tables (`ft_doc`, `urncount`, `bigram`, …) that this API does not use, and the same goes for the
`hyph_*.db` files.

The integer dhlabid has different column names in different places: `dhlabid` in `metadata.db`, `urn_seq` in
`urns.db` and `ft_doc_metadata`, and `urn` in the other shard tables. Only the text column `urn` in `urns.db`,
`metadata.db` and `ft_doc_metadata` is an actual URN. `repository.py` hides this from the rest of the code.

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
