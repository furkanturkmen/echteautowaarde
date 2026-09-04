# Architecture

## Shape

A modular monolith split into two locally running applications:

```
apps/web  (Next.js)  ──HTTP──▶  apps/api  (FastAPI)  ──▶  SQLite (data/automotive.db)
                                     │
                                     └──▶  Ollama (optional, local)
```

No cloud services, no message broker, no cache server, no background worker
infrastructure. Everything a developer needs runs on one machine.

## Backend layout (`apps/api/echte_auto_waarde/`)

| Package | Responsibility |
|---|---|
| `config.py` | Settings with local-first defaults, `EAW_` env prefix |
| `db/` | Declarative base, engine, session dependency, SQLite pragmas |
| `models/` | SQLAlchemy ORM models (persistence only) |
| `schemas/` | Pydantic request/response models (API contract) |
| `domain/` | Normalization, comparable engine, valuation, confidence — pure logic |
| `services/` | Orchestration between persistence, domain and adapters |
| `data_sources/` | `DataSourceAdapter` (market listings) and `VehicleSpecificationSource` (plate enrichment) implementations |
| `ai/` | Provider abstraction, Ollama client, prompt, grounding check |
| `api/routes/` | Thin FastAPI routers; no business rules |

The domain layer holds the valuable logic and is deliberately free of FastAPI
and database concerns so it can be unit-tested directly.

## Frontend layout (`apps/web/src/`)

| Path | Responsibility |
|---|---|
| `app/` | App Router pages and layouts |
| `lib/` | API client and formatting helpers |

The frontend never reproduces valuation logic. It renders structured backend
results and formats them for a Dutch consumer. Route structure keeps future
public SEO pages (`/autowaarde`, `/merken/bmw/3-serie`, …) possible without a
rewrite, and the canonical base URL stays configuration rather than a hardcoded
domain.

## Boundaries

| Backend owns | Frontend owns |
|---|---|
| Normalization, data access, comparable search, similarity, valuation, adjustments, confidence, deal classification, AI context | Input, rendering, interaction, formatting, visualization |

## Database

SQLite via SQLAlchemy 2.0, migrated with Alembic (`render_as_batch=True` so
column changes work on SQLite). Models avoid SQLite-only constructs, so moving
to another relational database later stays possible without a rewrite. The
database URL comes from application settings, including inside Alembic, so there
is one source of truth.

Money is stored as integer cents in EUR. Timestamps are stored in UTC and
formatted for Dutch display in the frontend.

## AI

Ollama sits behind an `AIProvider` abstraction and is optional by design. If it
is unavailable, `/health` reports the AI component as unavailable while overall
status stays `ok`, and valuation, comparison and market statistics continue to
work.

The assistant explains a stored valuation and never produces one. The server
loads that valuation and builds the structured context itself, so client input
cannot become AI context, and every euro amount in an answer is verified against
the valuation before it reaches the interface. See
[`local-ai.md`](local-ai.md).

## Market evidence

Two markets can exist in one database: the synthetic demo market and whatever
real listings were imported. They never mix in a valuation — `domain/evidence.py`
holds the rule and `services/comparables.py` applies it once, in the candidate
query.

Imports go through the existing adapter architecture:
`CsvImportDataSource` → `ingest()` → listings, snapshots and an `ImportRun`.
Validation completes before anything is written, the whole import is one
transaction, and only a `COMPLETED` full snapshot may mark absent listings
`REMOVED` — which means "not observed", never "sold".

## Network

One outbound call exists in the whole application: a plate lookup may ask the
Dutch open vehicle register for specifications. It is behind
`VehicleSpecificationSource`, has an explicit timeout, and every failure
degrades to the manual route. Everything else — comparables, valuation,
confidence, the local AI — runs without a network. Ollama is local.

## Local workflow

`scripts/setup.ps1` prepares a machine, `scripts/dev-api.ps1` and
`scripts/dev-web.ps1` run the two processes, and `scripts/verify.ps1` runs the
checks that must pass before a commit: ruff, ruff format, mypy and pytest on the
backend, then lint, `tsc --noEmit` and a production build on the frontend. There
is no CI; these run locally.

## What is deliberately absent

Microservices, Kubernetes, Redis, Celery, hosted search, vector databases,
authentication, payments, analytics, hosted monitoring and CI pipelines. Tests,
linting, type checks and builds all run locally.
