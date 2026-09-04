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

A license plate can be enriched from the Dutch open vehicle register: it fills
in what the register knows about the car (make, model, body, first registration,
fuel, power, displacement, doors, seats, colour, catalogue price) and asks the
user for what it does not — mileage, uitvoering and transmission are not in the
register, and are never guessed. This is the only outbound call the application
makes and it is **off by default** (`EAW_RDW_ENABLED=true` switches it on); with
it off or unreachable, the manual route works unchanged. The register is a
specification source and supplies no market data whatsoever.

Because the demo market invents plates, a demo car never answers for a typed
plate — it is offered as an example and valued by id instead.

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
GET  /vehicles/plate/{plate}/lookup   local first, then the open vehicle register
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

In a hurry: `scripts\setup.ps1` does everything in this section (virtual
environment, dependencies, migrations, demo data, `npm install`), and
`scripts\dev-api.ps1` / `scripts\dev-web.ps1` start the two processes. The steps
below are what those scripts run, one at a time.

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

### 5. Plate enrichment (optional)

A Dutch plate can be enriched from the open vehicle register. It is **off by
default**, because it is the only outbound call the application can make:

```powershell
$env:EAW_RDW_ENABLED = "true"      # or put EAW_RDW_ENABLED=true in .env
```

With it on, an unknown plate is looked up and the manual form opens prefilled
with what the register knows. With it off, unreachable, or given a plate that is
not a passenger car, the manual route works exactly as before. No account and no
key are needed, and nothing else in the application touches the network. See
[`docs/data-sources.md`](docs/data-sources.md).


### 6. Importing real market data (optional)

The demo market is invented. Real asking prices enter through a CSV file that
you are entitled to use — your own inventory, a licensed extract, an export you
were given. Nothing is fetched and no marketplace is contacted.

```powershell
cd apps\api
.\.venv\Scripts\python.exe -m echte_auto_waarde.import_market `
  --file ..\..\docs\examples\market-import-example.csv `
  --source-key import:dealer-example --scope bmw-3-serie --dry-run
```

Drop `--dry-run` to write it, and add `--mode full-snapshot` when the file is
the complete picture of that scope. Then value real vehicles against it:

```powershell
$env:EAW_MARKET_MODE = "REAL"
```

In `REAL` mode a real vehicle is valued on imported evidence only; the demo
examples keep using the demo market, and a shortage of real comparables is
reported as insufficient data rather than filled with invented listings.

**You are responsible for having the right to use any file you import.** A
listing that stops appearing is recorded as removed, never as sold, and an
asking price is never a sale price. See
[`docs/data-sources.md`](docs/data-sources.md) for the column contract.

### 7. Measuring the engine against imported data (optional)

With real data imported, the valuation engine can be measured against it
offline. Every listing is valued against every other listing but itself, and the
estimate is compared with the asking price that was observed:

```powershell
cd apps\api
.\.venv\Scripts\python.exe -m echte_auto_waarde.evaluate_market --source-key import:dealer-example
```

This reports **deviation from observed asking prices**, which is a coherence
check — not accuracy. We have no sale prices, so no result here is a measure of
correctness, and nothing is tuned automatically. Evaluation stores nothing and
leaves consumer valuation history untouched. See
[`docs/valuation.md`](docs/valuation.md).

### Configuration

Copy `.env.example` to `.env` (backend) and `apps/web/.env.example` to
`apps/web/.env.local` (frontend) if you need to override defaults. Backend
settings use the `EAW_` prefix. Every setting has a working local default, so
both files are optional.

## Testing

`scripts\verify.ps1` runs every check below in one go. Individually:

```powershell
cd apps\api
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\ruff.exe format --check .
.\.venv\Scripts\python.exe -m mypy echte_auto_waarde
.\.venv\Scripts\python.exe -m pytest
```

```powershell
cd apps\web
npm run lint
npx tsc --noEmit
npm run build
```

The backend suite runs entirely offline against an in-memory database: no test
needs Ollama, the vehicle register, or an internet connection. It covers
normalization and the option taxonomy, comparable filtering, similarity and
widening, valuation adjustments, outlier handling, deal classification,
confidence, the API contract, plate enrichment, and the AI layer's degraded
modes and grounding check.

The frontend has no test runner; adding one would mean a new dependency, so its
logic is covered through the API and by the type checker instead.


## Project structure

```
apps/api     FastAPI backend (domain, valuation engine, API)
apps/web     Next.js frontend
data/        Local SQLite database and development data (not committed)
docs/        Product, architecture, data model, valuation and data-source docs
scripts/     Local helper scripts (setup, dev servers, verification)
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
- A capped pilot reads a few listings from two dealers' own public inventory
  pages (robots-checked, 20 per run, facts only, no contact details). It is a
  development pilot, not a partnership and not risk-free; recurring collection
  belongs in a permission or feed arrangement.
- No marketplace data is collected. Commercial marketplaces are not scraped —
  their terms forbid it, AutoScout24's robots.txt refuses this class of agent
  outright, and CJEU C-202/12 concerned these exact Dutch car sites. Real data
  enters by import instead.
- Imported prices are observed asking prices. A removed listing is not a sale,
  and no sale price is ever recorded or inferred.
- Optional RDW enrichment covers vehicle specifications only — never prices.
- Valuation adjustments are conservative documented heuristics, not a trained
  model.
- The AI explains a finished valuation and never produces one. Its numeric
  check verifies that every euro amount came from the engine; it does not
  fact-check the reasoning around those amounts.
- Listings that disappear are never treated as sold. `LIKELY_SOLD` exists in the
  model and no heuristic sets it.
- No authentication, accounts, payments, analytics or telemetry exist, and no
  cloud service is required to run any part of this.
