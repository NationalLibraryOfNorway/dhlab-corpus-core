# DH-lab core API

The core of the DH-lab API — corpus building, concordances, collocations, word totals and n-grams — as a
FastAPI application. It serves two versions side by side:

- **v1**, at the root, has the same paths, requests and response shapes as the current DH-lab API.
- **v2**, under `/v2`, is the renewed API.

## Setup

You need [python](https://www.python.org/) and [pdm](https://pdm-project.org/en/latest/).

```bash
pdm install
cp .env.example .env   # then adjust
```

Settings are read from environment variables or from `.env`, which is git-ignored so that paths and deployment
details stay out of the repository.

| Variable       | Default   | Meaning                                                                    |
|----------------|-----------|----------------------------------------------------------------------------|
| `DATABASE_DIR` | `./db/ft` | Directory with `urns.db`, `metadata.db`, `grand_total.db` and `alto_*.db`  |
| `MAX_WORKERS`  | `8`       | Maximum number of shards queried concurrently                              |
| `ROOT_PATH`    | *(empty)* | URL prefix when served behind a reverse proxy                              |

`grand_total.db` is derived from the shards, and must be rebuilt when they change:

```bash
pdm run python scripts/make_grand_total.py <database_dir>
```

## Run

```bash
pdm run fastapi dev          # development server, interactive docs at http://127.0.0.1:8000/docs
pdm run pytest tests         # tests
```

The tests run against a small test database with public domain documents only, see
[tests/data/README.md](tests/data/README.md). Point `DATABASE_DIR` at `./tests/data/db` to try the request examples
in the interactive docs.

## Endpoints

| v1                                                             | v2                      |
|----------------------------------------------------------------|-------------------------|
| `POST /build_corpus`                                           | `POST /v2/corpus`       |
| `POST /conc`, `POST /conccount`                                | `POST /v2/concordance`  |
| `POST /urncolldist`, `POST /urncolldist_urn`                   | `POST /v2/collocations` |
| `GET /totals/{top_words}`                                      | `GET /v2/totals?limit=` |
| `POST /ngram_book`, `/ngram_periodicals`, `/ngram_newspapers`  | `POST /v2/ngram`        |

Requests and responses are documented in the interactive docs.

### What v2 changes

- Responses are lists of records instead of pandas' `{column: {index: value}}` layout, and empty metadata values
  are `null`. Collocations are returned as JSON, not as a JSON string inside JSON.
- Unknown fields, out-of-range values and missing corpora are rejected with `422` instead of being silently
  ignored or adjusted.
- Documents are identified by dhlabid: a corpus is given as `dhlabids` (v1 also accepts URNs). The URN is still
  part of the metadata that is returned.
- A corpus may hold at most 30 000 documents per request (v1 silently samples larger ones).
- Year ranges are inclusive in both ends, and dates are ISO dates.
- Collocation windows stop at document boundaries, and collocates come with a plain mean distance.
- Random sampling (`corpus`, `concordance`) is reproducible when the request has a `seed`.
- There is one n-gram endpoint with a `doctype` parameter, returning one series per word.

## Differences from the current DH-lab API

- **Scope.** Only the core functionality is included. Experimental and unrelated endpoints (NER, geo data, image
  search, word bank, dispersion, …) are left out.
- **Code.** FastAPI instead of Flask, with database access, business logic and REST endpoints in separate layers.
  Shards are queried in threads rather than process pools, and pandas is no longer a dependency.
- **Configuration.** Settings come from the environment or `.env`, not from a `config.py` in the repository.
- **Tests.** There is an automated test suite.

v1 keeps the behaviour of the current API where clients can observe it, including its quirks (e.g. `to_year` is
exclusive when `from_year` is also given, and collocations are a JSON string). It differs in these ways:

- Invalid requests (wrong types, no corpus) give `422` and malformed search expressions give `400`. Both gave `500`.
- `build_corpus` with no filters, or with only `limit` or `order_by`, returns documents instead of failing.
- `build_corpus` with a dotted `ddk` such as `"839.82"` works. The punctuation used to be stripped, so it never
  matched.
- `build_corpus` row indexes are always `0..n-1`.
- Collocation and n-gram requests that select no documents return an empty result instead of failing.
- `ngram_periodicals` honours `ddk`.
- N-grams are computed from `metadata_core` in `metadata.db` rather than the `metaindex_*` tables.

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
contain a few more tables (`ft_doc`, `urncount`, `bigram`, …) that this API does not use. The indexing pipeline also
writes `hyph_*.db` files, which this API does not use either; they are not part of the test database.

The integer dhlabid has different column names in different places: `dhlabid` in `metadata.db`, `urn_seq` in
`urns.db` and `ft_doc_metadata`, and `urn` in the other shard tables. Only the text column `urn` in `urns.db`,
`metadata.db` and `ft_doc_metadata` is an actual URN. `repository.py` hides this from the rest of the code.
