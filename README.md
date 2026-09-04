# Echte Auto Waarde

**Ontdek wat je écht zou moeten betalen.**

Echte Auto Waarde is a local, zero-cost automotive market comparison and
valuation application for Dutch consumers. It answers *"wat is deze auto écht
waard?"* — and especially *"wat zou jij voor deze auto betalen?"* — by comparing
a vehicle against similar vehicles and showing the evidence behind the estimate:
which cars were compared, how similar they are, which adjustments were applied
and how confident the result is.

The deterministic valuation engine produces every number. The local AI only
explains those numbers in plain Dutch; it never invents a value, and the
application stays fully usable with AI switched off.

> ⚠️ **The MVP market data is entirely synthetic.** It is generated for
> development and testing only, and is **not suitable for real purchase
> decisions or real market advice**.

---

## Status

The backend is complete and covered by tests: domain model, normalization and
option taxonomy, a deterministic synthetic market of 122 fictional listings, the
comparable engine (filtering, similarity, widening, structured explanations),
the valuation engine (robust statistics, outlier handling, transparent
adjustments, purchase range, deal classification, confidence) and the HTTP API.

The Dutch consumer interface is built: license-plate or manual entry, a stable
valuation result page, the market-position view, the comparable evidence table
with per-car Overeenkomsten/Verschillen, and the valuation build-up.

The local AI explanation layer answers questions about a finished valuation,
using only that valuation's own data. Every euro amount in an answer is checked
against the figures the engine produced — a numeric check, not a verification of
the explanation itself. It is optional in the strongest sense:
with no model installed, everything else works exactly as before.

### Screens

```
/                        kenteken -> vraagprijs -> waardering
/handmatig               manual vehicle entry
/waardebepaling/{id}     stored valuation with all of its evidence
```

### API

```
GET  /health                      component status (AI may be down; that is fine)
GET  /vehicles/{id}               vehicle with normalized specification and options
GET  /vehicles/plate/{plate}      local plate lookup
POST /vehicles/manual             manual vehicle entry, normalized on the way in
POST /comparables/search          the comparable evidence, without a valuation
POST /valuations                  valuation with evidence, adjustments, confidence
GET  /valuations/{id}             a stored valuation and the evidence behind it
GET  /listings/{id}               one market listing
GET  /listings/{id}/history       observed price history of a listing
GET  /market/stats                what the local dataset contains
GET  /market/examples             real vehicles from the local dataset to start from
GET  /options                     the canonical option taxonomy
POST /ai/chat                     ask about a stored valuation (local model, optional)
GET  /ai/valuations/{id}/suggestions   example questions this valuation can answer
```

## Architecture

| Layer | Technology |
|---|---|
| Frontend | Next.js (App Router) · React · TypeScript · Tailwind CSS |
| Backend | Python · FastAPI · Pydantic · SQLAlchemy |
| Database | SQLite (`data/automotive.db`), Alembic migrations |
| Local AI | Ollama, behind an `AIProvider` abstraction (optional) |

Everything runs on one machine. No cloud services, no paid APIs, no hosted
database, no authentication, no CI. See [`docs/architecture.md`](docs/architecture.md).

## Requirements

- **Python 3.11+** (developed on 3.13)
- **Node.js 20+** (developed on 22) and npm
- **Ollama** — optional, only for AI explanations

## Local setup

All commands below are written for Windows PowerShell; they work unchanged in
bash apart from the virtual-environment activation path.

### 1. Backend

```powershell
cd apps\api
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\alembic.exe upgrade head        # creates data/automotive.db
.\.venv\Scripts\python.exe -m uvicorn echte_auto_waarde.main:app --reload --port 8000
```

API docs: <http://localhost:8000/docs> · health: <http://localhost:8000/health>

### 2. Frontend

```powershell
cd apps\web
npm install
npm run dev
```

Frontend: <http://localhost:3000>

### 3. Seed data

```powershell
cd apps\api
.\.venv\Scripts\python.exe -m echte_auto_waarde.seed --reset
```

This generates 122 fictional listings across BMW 3 Serie (330e / 320i / 320d),
Volkswagen Golf (Mk8 1.5 TSI / 2.0 TDI / GTE and Mk7 1.2 TSI / 1.4 TSI /
1.6 TDI), Mercedes-Benz C-Klasse, Audi A4 and Tesla Model 3, including
observation history and price reductions. It is deterministic per seed
(`--seed 42` gives a different but equally reproducible market) and needs no
network access.

Every listing, seller and price is invented. The dataset exists to exercise the
comparable and valuation methodology; it is not a picture of the Dutch market
and must not be used for real purchase decisions.

### 4. Local AI (optional)

```powershell
ollama pull qwen2.5:7b-instruct
ollama serve
```

`ollama list` shows what is installed. The model must follow instructions in
Dutch — code models such as `qwen2.5-coder` stay safe but refuse questions the
data does answer. Nothing is downloaded by the application itself.

If Ollama is not running or the configured model is missing, valuation,
comparison and market statistics keep working, `/health` stays `ok`, and the
result page shows a short note in place of the question box. See
[`docs/local-ai.md`](docs/local-ai.md) for the grounding rules and the numeric
check that verifies every amount an answer mentions.

### Configuration

Copy `.env.example` to `.env` (backend) and `apps/web/.env.example` to
`apps/web/.env.local` (frontend) if you need to override defaults. Backend
settings use the `EAW_` prefix. Every setting has a working local default, so
both files are optional.

## Testing

```powershell
cd apps\api
.\.venv\Scripts\python.exe -m pytest
```

Backend tests run offline and cover normalization, comparable selection,
similarity, valuation adjustments, deal classification and confidence as those
parts land.

Frontend checks:

```powershell
cd apps\web
npm run lint
npx tsc --noEmit
npm run build
```

## Project structure

```
apps/api     FastAPI backend (domain, valuation engine, API)
apps/web     Next.js frontend
data/        Local SQLite database and development data (not committed)
docs/        Product, architecture, data model, valuation and data-source docs
scripts/     Local helper scripts
CLAUDE.md    Authoritative project specification
```

## Documentation

- [`docs/product.md`](docs/product.md) — what the product does and for whom
- [`docs/architecture.md`](docs/architecture.md) — how the pieces fit together
- [`docs/data-model.md`](docs/data-model.md) — entities and their relationships
- [`docs/valuation.md`](docs/valuation.md) — comparable selection and valuation methodology
- [`docs/data-sources.md`](docs/data-sources.md) — where data comes from, and what it is not
- [`docs/local-ai.md`](docs/local-ai.md) — the local AI layer and its guardrails

## Limitations

- Market data is synthetic; the valuation validates the methodology, not real
  Dutch market prices.
- No marketplace data is collected. Commercial marketplaces are not scraped.
- Optional RDW enrichment covers vehicle specifications only — never prices.
- Valuation adjustments are conservative documented heuristics, not a trained
  model.
