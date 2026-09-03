# Echte Auto Waarde — Project Specification

This file is the authoritative specification for this repository. When product
direction is unclear, return to the core question:

> **"What evidence can we show the consumer to help answer: what should I actually pay for this car?"**

---

## 1. Project identity

| Item | Value |
|---|---|
| Product name | **Echte Auto Waarde** |
| Domain | EchteAutoWaarde.nl (not deployed during MVP) |
| Repo slug | `echte-auto-waarde` |
| Tagline | **Ontdek wat je écht zou moeten betalen.** |
| Supporting message | Vergelijk de markt. Ken de waarde. Betaal eerlijk. |

Never invent alternative product names (CarValue, AutoPrice, AutoWise, CarLens,
VehicleAI, …). Use **Echte Auto Waarde** consistently in UI, docs, metadata,
README, examples and the seed/demo experience.

**What it is:** an automotive market intelligence and valuation application with
an AI interface. **What it is not:** a chatbot about cars. The core application
must remain fully useful with AI completely disabled.

---

## 2. Repository status

The GitHub repository already exists and is intentionally empty. Do **not**
create another repository. Inspect git config and remotes before repository
decisions.

- Create `.gitignore`, README and docs as part of the project.
- Do **not** add a LICENSE yet — the licensing model is undecided because the
  project may become commercial. Open-source dependencies are fine provided
  their licenses stay compatible with that possibility.
- Do not push, force-push, delete branches, modify remotes, or perform
  destructive git operations unless explicitly instructed. Local commits on
  request are fine.
- Commits and pull requests carry no AI/assistant attribution of any kind.

---

## 3. Non-negotiable: zero cost, local-first

The project must cost **€0 to develop** and **€0/month to run**. This overrides
architectural convenience.

Never introduce anything that requires payment, a credit card, a paid API key,
cloud infrastructure, a managed database, hosted AI, paid automotive/VIN data,
paid search, or that creates recurring cost. No quiet "free tier" cloud
dependencies.

**Rule: if it can run locally, run it locally.**

The core application keeps working offline once dependencies, models and local
datasets are installed. Internet may be used only for installing packages,
downloading open-source models, retrieving explicitly supported public/open
datasets, optional RDW enrichment, and future manually triggered imports. The
valuation engine never depends on an internet connection. No telemetry, no
third-party analytics.

### Forbidden for the MVP

AWS · Azure · GCP · Vercel · Netlify · Render · Railway · Fly.io · Supabase ·
Firebase · Neon · PlanetScale · hosted PostgreSQL/MySQL · MongoDB Atlas · Redis
Cloud · Elasticsearch Cloud · Algolia · Pinecone · hosted vector DBs · OpenAI /
Anthropic / Gemini / any paid AI API · paid automotive, VIN or license-plate
APIs · SaaS analytics · Sentry or hosted monitoring · hosted auth · CI/CD
services. **No GitHub Actions for the MVP** — tests, lint, typecheck and builds
run locally.

### Do not overengineer

No microservices, Kubernetes, message brokers, Kafka, RabbitMQ, Redis,
distributed caching/tracing, service meshes, event-driven complexity, or a
database per domain. Build a clean modular monolith that stays extensible
without pretending to operate at enterprise scale.

---

## 4. Technology stack (authoritative)

| Layer | Choice |
|---|---|
| Frontend | Next.js (App Router) · React · TypeScript · Tailwind CSS · shadcn/ui where useful, strictly as customizable component primitives rather than a default visual theme (see §16) |
| Backend | Python · FastAPI · Pydantic · SQLAlchemy |
| Database | **SQLite** at `data/automotive.db` |
| Migrations | Alembic, committed to the repo, no database server |
| AI | **Ollama**, local model, behind an `AIProvider` abstraction |
| Auth / payments / Redis / cloud / CI | **None** |

Keep business logic out of route handlers; use service/domain modules. Do not
replace SQLite with PostgreSQL "because it is more production ready" — design
the SQLAlchemy models so a later migration stays possible without building it
now.

**Ollama:** communicate with a locally running instance. Model choice is
configuration, not hardcoded (Qwen, Llama, Mistral, Gemma, … all acceptable).
No hosted fallback. If Ollama is unavailable, valuation, comparison and market
statistics must still work and the UI shows that AI advice is temporarily
unavailable.

Docker is optional and must never become the only supported workflow. Native
local development stays straightforward; instructions must be Windows-friendly.

---

## 5. Product

Echte Auto Waarde helps a Dutch consumer answer **"Wat is deze auto écht
waard?"** and especially **"Wat zou jij voor deze auto betalen?"**

It never returns just a number. It shows:

1. which comparable cars were found
2. why they are comparable
3. how similar they are
4. how their prices differ
5. which specifications/options matter
6. how the valuation was calculated
7. how confident the system is
8. what a sensible purchase/negotiation price is

Formula: **vehicle data + comparable market data + deterministic valuation +
explainability + local AI interface.**

Target user: Dutch consumers buying or evaluating used cars. Sellers, dealers,
fleets and lease companies are possible later — do not optimise the MVP for
enterprise. Consumer usability comes first.

### Input

- **A.** Dutch license plate (e.g. `K-123-AB`)
- **B.** Manual vehicle input
- **C.** Advertisement URL — *future*; do not build scraping for it now
- **D.** Asking price (essential: asking price vs estimated market value vs
  recommended purchase price)

### Priorities under tension

| Tension | Winner |
|---|---|
| AI feature vs better market comparison | market comparison |
| Fancy UI vs valuation transparency | transparency |
| More features vs better comparable data | comparable data |
| Future scalability vs simple reliable local MVP | simple local MVP (unless it creates a serious architectural dead end) |

---

## 6. Language rule

Consumer UI is **Dutch**. Code, API fields, variable names and developer
documentation are **English**. Maintain this separation consistently.

| UI (Dutch) | Code (English) |
|---|---|
| Geschatte marktwaarde | `estimatedMarketValue` |
| Vergelijkbare auto's | `comparableVehicles` |
| Prijsadvies | `recommendedPurchasePrice` |
| Betrouwbaarheid | `confidenceScore` |
| Vraagprijs | `askingPrice` |

Consumer terminology: **Autowaarde**, **Vraagprijs**, **Goede koop**, **Eerlijke
prijs**, **Aan de dure kant**, **Vergelijkbare auto's**, **Prijsadvies**,
**Marktvergelijking**, **Vraag AI**. Avoid unnecessary technical jargon in the
consumer UI, and do not overuse slogans in the interface.

---

## 7. Data sources

All external data lives behind adapters. Domain and valuation engines never
depend on a specific external website.

`DataSourceAdapter` → `SyntheticDataSource` (MVP), `CsvImportDataSource`
(optional), `RdwDataSource` (later), `MarketplaceDataSource` (future),
`ManualImportDataSource`.

### Scraping rule

Do **not** scrape commercial marketplaces during the MVP — no Marktplaats,
AutoScout24, Gaspedaal, AutoTrack, dealer sites or similar — unless explicitly
instructed later after the legal, contractual and technical constraints have
been reviewed. Never bypass authentication, CAPTCHAs, anti-bot systems, rate
limits or access controls, and never rotate identities to evade restrictions.
The architecture allows legitimate market-data adapters later; the MVP never
depends on unauthorised scraping.

### RDW

RDW Open Data is an **optional vehicle specification enrichment** source (plate
lookup, make, trade name, registration, fuel, characteristics, catalog price,
technical attributes). RDW is **not** a source of current used-car asking
prices — marketplace/comparable pricing is a separate concern. It stays behind
an adapter, and the application remains usable with manual or seeded data if
RDW is unavailable.

### Synthetic dataset

~100 clearly synthetic listings, deterministically generated so tests stay
reproducible. At minimum BMW 3 Series / 330e, Volkswagen Golf, Mercedes-Benz
C-Class, Audi A4, Tesla Model 3. Vary year, mileage, asking price, trim, engine,
fuel, transmission, power, drivetrain, body type, options, seller type,
location, listing date and price changes, with enough similar vehicles to form
meaningful comparable groups. Never copy real marketplace listings. Never blur
synthetic and real market data.

---

## 8. Domain model

Design at minimum these concepts. Add fields that contribute to matching,
valuation or display — not every conceivable field.

- **Vehicle** — id, licensePlate, make, model, generation, bodyType, fuelType,
  transmission, engineDescription, engineDisplacement, powerKw, powerHp,
  drivetrain, year, firstRegistrationDate, mileage, trim, color, doors, seats,
  catalogPrice, sourceMetadata
- **VehicleSpecification** — structured technical attributes that do not belong
  on the basic vehicle entity
- **VehicleOptionDefinition** — canonical option definition with aliases
  (panoramic roof, adaptive cruise, heated/ventilated seats, leather, 360
  camera, reversing camera, parking sensors, premium audio, head-up display,
  electric/memory seats, tow bar, matrix LED, adaptive suspension, …)
- **VehicleOption** — vehicle ↔ normalized option, keeping raw source text
- **Seller** — id, sellerType (`PRIVATE` / `DEALER` / `UNKNOWN`), name, city;
  fictional identities in synthetic data
- **Listing** — id, vehicleId, sellerId, dataSourceId, externalReference,
  askingPrice, url, status, firstSeenAt, lastSeenAt, createdAt, updatedAt
- **ListingSnapshot** — observedAt, askingPrice, mileage, status, rawMetadata.
  Never overwrite history when a listing changes.
- **DataSource** — `SYNTHETIC`, `CSV_IMPORT`, `RDW`, `MANUAL`, future adapters
- **Valuation** — id, targetVehicleId, createdAt, estimatedMarketValue,
  recommendedBuyPriceLow, recommendedBuyPriceHigh, confidenceScore,
  comparableCount, algorithmVersion
- **ComparableResult** — listing, similarityScore, reasons, differences,
  adjusted-price contribution

### Listing lifecycle

States: `ACTIVE`, `PRICE_REDUCED`, `REMOVED`, `LIKELY_SOLD`, `RELISTED`,
`UNKNOWN`. A disappeared listing is **not** automatically sold — only use
`LIKELY_SOLD` with an explicit heuristic. Keep observed facts separate from
inferred states.

### Money and time

Money: integer cents internally, currency **EUR**, no floating-point money
maths, no premature multi-currency. Time: store UTC, display Dutch-friendly
formats. Historical observation times matter for future analytics.

---

## 9. Normalization

Implement normalization before sophisticated valuation: make, model, generation
where possible, body type, fuel type, transmission, drivetrain, trim and option
names. `BMW` / `bmw` / `B.M.W.` normalize identically; `Automaat` / `Automatic`
/ `AUTO` map to one canonical transmission. Keep raw values for traceability.

**Options are strategically important.** `Adaptive Cruise Control` / `ACC` /
`adaptieve cruise` map to one canonical option through a maintainable alias
taxonomy. Initial options include M Sport, AMG Line, S line, R-Line, panoramic
roof, adaptive cruise, 360 camera, reversing camera, leather, heated seats,
premium audio, head-up display, electric seats, matrix/adaptive LED, tow bar.
Options are not equally valuable, and option importance must be configurable.

**Trim/package** materially influences value and must survive normalization —
an appearance package is not a performance model: `BMW 330e M Sport` is **not**
`BMW M3`.

**Vehicle fingerprint:** a normalized representation (make, model, generation,
body type, fuel, transmission, engine, power, drivetrain, year, mileage, trim,
options) that the comparable engine works from. It need not be one serialized
string.

---

## 10. Comparable engine

One of the core assets. It is deterministic, transparent, testable,
configurable and explainable. **Never use an LLM to decide which vehicles are
comparable. Do not start with machine learning.**

**Filtering:** start with hard/near-hard filters (same make, same model,
compatible generation, body type, fuel/powertrain, transmission where
important), then score the remainder. Avoid filters so strict they return zero
comparables; implement widening:

1. same model + generation + powertrain
2. same model + generation, broader engine range
3. same model, nearby years

Any widening used must be visible in the result.

**Similarity score:** pick one scale (0.00–1.00 or 0–100) and stay consistent.
Weighted factors: make/model, generation, body type, fuel/powertrain, engine,
power, transmission, drivetrain, year difference, mileage difference, trim,
option overlap. Weights are configurable and documented — never unexplained
magic constants.

**Explanation:** every comparable returns structured reasons and differences
(same model and generation, same PHEV powertrain, same M Sport trim, 1 year
newer, 14.000 km lower, lacks panoramic roof, …). The frontend turns these into
Dutch text.

**User-selectable importance:** architect so a user can later mark what matters
(exact trim, panoramic roof required, transmission must match, mileage may
differ, options less important). No advanced weighting UI is required on the
first screen, but do not design it out.

---

## 11. Valuation engine

Deterministic and fully separate from the AI layer. **The LLM never invents a
value.**

```
vehicle → normalize → find candidates → similarity → drop weak candidates
→ remove extreme outliers → weighted market statistics → transparent adjustments
→ estimated market value → recommended purchase range → confidence → deal class
```

Baseline methodology: find comparables → drop below minimum similarity → detect
price outliers → weight by similarity → robust weighted central price (prefer
robust statistics over an arithmetic mean) → transparent adjustments →
estimated market value → purchase range → confidence. Document every formula.

- **Outliers:** transparent method (IQR, MAD or percentile trimming) suited to
  small groups; document the choice; never silently drop most of the data;
  expose internal debugging information.
- **Mileage:** conservative, configurable, capped to prevent absurd
  corrections; may become model/category dependent later. Document the
  assumption; do not pretend the first model is universally accurate.
- **Year/age:** conservative, and avoid double-counting depreciation that
  comparable prices already capture.
- **Options:** meaningful but never original retail prices — used-market option
  value differs. Conservative configurable heuristics. Options affect
  similarity too, not only the final price.

**Market statistics** accompany every valuation: comparable count, min/max/median
asking price, weighted median, average mileage, average year, price dispersion,
similarity statistics.

**`estimatedMarketValue`** is the best estimate from current comparable data —
never implied certainty (`Geschatte marktwaarde`, not `Exacte waarde`).

**Recommended purchase price** (`recommendedBuyPriceLow` /
`recommendedBuyPriceHigh`) answers "Wat zou jij betalen?". It may sit below the
estimated market value depending on strategy; document the derivation; never
arbitrary negotiation advice.

**Deal classification** is owned by the backend/domain layer, centralised, with
configurable documented thresholds:

| Code | Dutch label |
|---|---|
| `EXCELLENT_DEAL` | Zeer goede deal |
| `GOOD_DEAL` | Goede koop |
| `FAIR_PRICE` | Eerlijke prijs |
| `EXPENSIVE` | Aan de dure kant |
| `VERY_EXPENSIVE` | Erg duur |

Thresholds never scattered across frontend and backend.

**Algorithm version:** a simple identifier (e.g. `valuation-v0.1`) stored with
results so versions stay comparable later. No model registry.

---

## 12. Confidence

Every valuation includes a confidence score, never random, derived from
measurable factors: number of comparables, average similarity, price
dispersion, freshness of observations, missing vehicle fields, option
completeness, data-source quality, and how much widening was required. A low
comparable count must reduce confidence. Document the calculation.

Return **structured confidence factors**, positive and negative (e.g. "28 strong
comparables", "narrow price distribution" vs "option data incomplete", "some
listings older than preferred"), so the frontend and AI can explain uncertainty.

**Insufficient data:** never fabricate a valuation. Return a structured
insufficient-data result or a much lower confidence, and explain which criteria
caused the shortage. UI wording: *"We hebben te weinig vergelijkbare auto's om
met voldoende zekerheid een waarde te bepalen."*

---

## 13. AI layer

AI is the conversational explanation and purchase-advice interface on top of
structured valuation data — not the valuation engine. It receives structured
context produced by the deterministic backend and answers questions such as
"Wat zou jij betalen?", "Waarom vind je deze auto duur?", "Is €26.500 een goed
bod?", "Hoeveel verschil maakt M Sport?", "Waarom is de betrouwbaarheid maar
71%?".

**Guardrails.** Never fabricate listings, market prices, options, mileage,
specifications, valuation results, comparable counts or confidence scores. If
information is unavailable, say so. If confidence is low, communicate
uncertainty. Always distinguish **vraagprijs** from **geschatte marktwaarde**
from **aanbevolen aankoop-/onderhandelingsprijs** — never interchangeable.

**Personality.** Dutch, practical, concise, transparent, non-salesy, skeptical
when evidence is weak, easy to understand, light on jargon. Style example (the
numbers always come from backend context):

> "Ik zou voor deze auto ongeveer €25.800 tot €26.500 proberen te betalen. De
> vraagprijs van €27.500 ligt iets boven vergelijkbare 330e's met een
> vergelijkbare kilometerstand. De M Sport-uitvoering helpt de waarde, maar het
> verschil wordt niet volledig gerechtvaardigd door de opties."

**Abstraction.** `AIProvider` interface, `OllamaProvider` implementation. No
Ollama-specific request formats leak into the rest of the application.
Configuration covers base URL, model name, timeout and an enable/disable flag,
with sensible local defaults. No hosted provider implementations unless
explicitly requested.

---

## 14. API

Initial endpoints (routes may be refined, naming stays consistent, Pydantic
request/response models throughout, OpenAPI generated by FastAPI):

```
GET  /health
GET  /vehicles/{id}
GET  /vehicles/plate/{plate}
POST /vehicles/manual
POST /comparables/search
POST /valuations
GET  /valuations/{id}
POST /ai/chat
GET  /listings/{id}
GET  /listings/{id}/history
GET  /market/stats
```

A valuation response conceptually contains: target vehicle, asking price if
supplied, `estimatedMarketValue`, `recommendedBuyPriceLow` / `High`,
`dealClassification`, `confidenceScore`, `confidenceFactors`, `comparableCount`,
`marketStatistics`, `adjustments`, `comparables`, `algorithmVersion`.

Adjustments are structured, e.g. `type: MILEAGE`, `amount: -650`,
`reason: "Vehicle has approximately 18,000 km more than the comparable group median."`
Never return a single unexplained number.

**Boundary.** The frontend never reproduces valuation logic. Backend owns
normalization, data access, comparable search, similarity, valuation,
confidence, deal classification and AI context. Frontend owns input, rendering,
interaction, formatting and visualisation.

---

## 15. Frontend

**Homepage** communicates the value proposition immediately: brand, headline
*Ontdek wat je écht zou moeten betalen.*, supporting copy *Controleer de waarde
van een auto en vergelijk hem met soortgelijke occasions.*, primary input
**Kenteken**, alternative **Auto handmatig invoeren**, optional **Vraagprijs**,
CTA **Bekijk echte autowaarde**. Not a generic AI chatbot.

**Valuation result** is the most important screen, in priority order: vehicle
identity → estimated market value → asking price → recommended purchase range →
deal classification → confidence → comparable vehicles → explanation → AI
conversation. The valuation number is visually prominent; AI complements rather
than dominates.

**Comparable table** is a core requirement — users inspect the actual dataset
the algorithm used. Columns such as similarity, make/model, year, mileage, trim,
engine/powertrain, important options, asking price, price difference, seller
type, observed date, with useful sorting/filtering. Never hide the evidence
behind AI prose.

**Comparable detail** answers "Why is this vehicle comparable?" with same/
different breakdowns (94% match · same model, generation, powertrain,
transmission, M Sport · +11.000 km, 1 year older, no panoramic roof). This is
central to product trust.

**Feel:** trustworthy, modern, clean, data-driven, automotive, consumer-friendly,
transparent. Generous whitespace, clear hierarchy. Avoid looking like a used-car
dealership, an enterprise dashboard, a generic chatbot, a crypto dashboard or a
cheap kenteken-report site.

**Responsive:** mobile-first enough that the core experience works on phones
(responsive cards, horizontal scroll or condensed columns for the table) without
sacrificing desktop data density.

**Accessibility:** semantic HTML, keyboard usability, labels, contrast, focus
states, accessible form controls. No formal certification effort for the MVP,
but no obvious accessibility problems.

---

## 16. Styling & design system

Authoritative for all frontend work. Reread this section before implementing any
UI (Phase 6). The frontend follows the real backend data model and valuation
output — never invented data used to make a design look complete.

### Styling stack

**Tailwind CSS is the primary styling system.** **shadcn/ui is used selectively
as a source of customizable component primitives** — buttons, inputs, dialogs,
dropdowns, tabs, tooltips, sheets, tables, form controls — and never as the
visual identity of Echte Auto Waarde. Customize every primitive with Tailwind so
the product develops its own recognizable design language.

The result must not look like a default shadcn dashboard, an admin panel,
enterprise SaaS, a generic AI application, a Bootstrap website, a traditional
dealership site, or an obviously AI-generated template.

### Design direction

Echte Auto Waarde should feel like **a polished, modern Dutch consumer fintech
product applied to automotive market data** — closer to a trustworthy financial
valuation product than to a used-car marketplace.

Visual qualities: premium, trustworthy, calm, modern, data-driven, precise,
transparent, consumer-friendly. The product handles prices and valuations, so
**visual trust matters more than visual spectacle**: prefer simplicity, strong
typography and clear hierarchy over decoration.

### Color

Predominantly light interface: warm off-white / very light gray page background,
white content surfaces, deep navy primary brand color, near-black primary text,
muted gray secondary text, subtle neutral borders.

Starting palette (refine if a better cohesive palette emerges — these are not
immutable): primary/navy `#14213D`, background `#F7F8FA`, surface `#FFFFFF`,
primary text `#111827`, muted text `#6B7280`.

Semantic colors, used carefully: green = attractive market position, amber =
caution / somewhat expensive, red = clearly expensive. **Never communicate deal
status by color alone.**

Centralize important colors as CSS variables / design tokens integrated with
Tailwind. Never scatter hardcoded colors through components.

Avoid: excessive gradients, purple/blue "AI startup" gradients, neon colors,
black/red racing themes, carbon-fiber effects, glowing elements.

### Typography

Typography is one of the strongest parts of the design. Use a clean modern
sans-serif with excellent readability and build a strong hierarchy between
homepage headline, vehicle identity, valuation amount, section headings,
supporting statistics, body text and metadata.

Financial values must be exceptionally scannable — `€27.300` carries
substantially more visual weight than the label `Geschatte marktwaarde`. Use
tabular numbers for prices, mileage, statistics and tables. Avoid unnecessary
font variations and excessive weights.

### Spacing, cards and surfaces

Generous whitespace; do not fill every empty area; the product should feel calm.
Use a consistent Tailwind spacing scale with clear vertical separation between
major sections. Dense evidence such as the comparable table may be more compact,
but the page overall must not feel crowded.

Do **not** put every piece of information in a card — use cards only for
meaningful grouping or hierarchy. Cards: white/subtle surface, subtle neutral
border, restrained shadow, moderate radius, comfortable internal spacing. Avoid
giant radii everywhere, nested cards, glassmorphism, floating translucent
panels, heavy shadows and dashboard grids of many cards. Important information
may sit directly on the page when that gives a stronger hierarchy.

### Buttons

Primary actions (e.g. **Bekijk echte autowaarde**) are immediately recognizable,
confident, simple and premium. Prefer rounded rectangles — not fully pill-shaped
buttons everywhere. Secondary actions stay visually quieter. Clear hover,
active, focus and disabled states throughout.

### Dutch license plate input

The license plate becomes a recognizable Echte Auto Waarde interface element:
where appropriate the input is visually recognizable as a Dutch plate (yellow
surface, dark characters, subtle blue EU/NL section). It must stay polished
rather than gimmicky, and never sacrifice accessibility, readability, keyboard
input or responsive behaviour for visual realism.

### Homepage

Relatively minimal. The primary journey is immediately obvious: **kenteken →
vraagprijs → echte autowaarde**. The hero communicates *Ontdek wat je écht zou
moeten betalen.*, supporting copy stays concise, and the plate/value input is
visually central. Not a generic landing-page template with unnecessary sections.

### Valuation result hierarchy

The most important screen: a consumer understands the key result in roughly
**five seconds**. Priority order:

1. vehicle identity
2. estimated market value
3. recommended purchase range
4. asking price
5. deal classification
6. confidence
7. market position
8. comparable vehicles
9. valuation explanation
10. AI assistance

Never give every metric equal visual weight. Design the layout properly rather
than copying the conceptual sketch in §15.

### Market position visualization

A simple, instantly understandable visualization of where the evaluated vehicle
sits relative to comparable market prices (e.g. a `Goed geprijsd — Marktconform
— Duur` scale, or a price axis with the vehicle positioned on it). Every
position and range shown must derive from actual valuation/market data — never a
misleading visualization.

### Deal status and confidence

Deal classifications get clear but restrained treatment: text label, semantic
color, optionally a subtle icon — never color alone, and never styled as
promotional sales badges. They represent analysis, not marketing.

Confidence is visible but secondary to the valuation (e.g. `89% betrouwbaarheid`),
inspectable so users see why it is high or low, and visually reads as a
data-quality measurement rather than an arbitrary AI score — it comes from the
deterministic backend model.

### Comparable vehicles

Comparables are the evidence, so treat their presentation accordingly. Desktop:
a high-quality structured table/comparison experience. Mobile: either carefully
designed responsive comparable cards or a deliberately designed horizontally
scrollable table, whichever gives better usability.

Information may include similarity, make/model, year, mileage, trim, relevant
options, asking price, price difference, seller type and observation date.
Similarity stays visually scannable without overpowering price information.
Never hide evidence behind AI-generated summaries.

Opening a comparable clearly separates **Overeenkomsten** from **Verschillen**
(e.g. same generation, 330e plug-in hybride, M Sport, automaat vs 11.000 km
minder, 1 jaar nieuwer, heeft panoramadak, geen premium audio), easy to scan, so
the consumer understands why the vehicle was selected.

### Price explanation

Where structured backend adjustments exist, show them understandably —
marktbasis, each correction with its signed amount and reason, then the
estimated market value. Only display real backend adjustments; never fabricate
adjustments to fill the interface.

### AI interface

AI must not visually dominate. The homepage is never a ChatGPT-style interface.
The product experience is **vehicle → market → valuation → evidence**, with AI
afterwards as an assistance and explanation layer answering questions like "Wat
zou jij bieden?", "Waarom is deze auto duur?", "Is €26.000 een realistisch
bod?", "Waarom is de betrouwbaarheid maar 71%?".

The AI interface belongs to the same product visually. No purple AI gradients,
glowing AI buttons, robot imagery, giant chat boxes or sparkle effects
everywhere; a small subtle sparkle icon is acceptable where it aids recognition.

### Icons, charts, animation

Icons: **Lucide React**, consistent sizes and stroke, used sparingly — not next
to every label, and no mixing icon libraries without genuine need.

Charts: prefer **Recharts**, but do not install it until a real visualization
requires it. Charts stay simple, readable, responsive and consumer-friendly —
not an enterprise analytics dashboard. Candidates: comparable price
distribution, market position, historical asking-price movement, mileage vs
asking price — built only when the data genuinely supports them.

Animation: native CSS/Tailwind transitions first; subtle, purposeful and fast
(expanding comparable details, a restrained result reveal, market-position
movement, dialogs/sheets, interaction feedback). Introduce Motion/Framer Motion
only for a real UX need. Avoid excessive entrance animations, parallax, bouncing
UI, constant movement, decorative animation, and anything that delays access to
valuation information.

### Responsive

Intentionally designed for desktop, tablet and mobile — never a shrunken desktop
layout. Mobile priority: vehicle identity → estimated market value →
recommended purchase price → asking price → deal status → confidence → market
position → comparables → explanation → AI. Desktop may expose more market
evidence simultaneously.

### Reusable components and tokens

Extract components only where genuine repetition exists and clarity improves —
no large generic component framework. Likely candidates: `MoneyValue`,
`DealBadge`, `ConfidenceIndicator`, `LicensePlateInput`, `MarketPosition`,
`VehicleSummary`, `ComparableRow`, `ComparableCard`, `StatDisplay`.

Centralize design decisions as tokens (CSS variables integrated with Tailwind):
brand colors, background, surfaces, primary text, muted text, borders, semantic
positive/warning/negative states, radius, shadows. Future brand refinement must
not require editing dozens of components.

### Avoid generic generated UI

Do not default to the standard AI-generated landing pattern (navbar → giant hero
→ three feature cards → random statistics → testimonials → pricing → FAQ → giant
final CTA) unless those sections genuinely serve the product.

**Never fabricate** testimonials, review scores, customer numbers, counts of
analyzed vehicles, press or partner logos, marketplace coverage, awards or user
statistics. Trust comes from transparent data and understandable valuation
evidence.

### Avoid automotive clichés

No giant supercar hero photography, red/black racing themes, carbon-fiber
textures, speedometer graphics, aggressive italic typography, racing stripes or
gratuitous car silhouettes. The automotive identity comes from vehicle
information, license plates, market data, valuation and tasteful details.

### Visual product principle

The valuation and its supporting evidence are the visual product; AI is only the
assistance layer. The interface communicates *"We can show you why this car is
worth approximately this amount"* — not *"Our AI knows what your car is worth."*

### Design quality check

Before considering a major screen complete: (1) is the most important
information understandable in ~5 seconds? (2) is the estimated market value
visually dominant? (3) is the recommended purchase price immediately
understandable? (4) is the asking price easy to compare? (5) is deal status
clear without being promotional? (6) is confidence visible and understandable?
(7) can users inspect the evidence? (8) does it feel trustworthy? (9) does it
look like a consumer product rather than an admin dashboard? (10) does it avoid
looking generically AI-generated? (11) is the product still useful without AI?
(12) does the mobile experience feel intentionally designed? (13) are monetary
values and differences easy to scan? (14) does it feel recognizably like Echte
Auto Waarde?

If not, refine the design before adding decorative features.

---

## 17. SEO (architecture only)

The MVP runs locally and needs no deployment, but structure the frontend so
public SEO pages can be added later without a rewrite. Future topics:
autowaarde, autowaarde berekenen, wat is mijn auto waard, auto waarde,
marktwaarde auto, occasion waarde, auto prijs vergelijken, occasion vergelijken,
wat moet ik voor een auto betalen, auto kopen prijs, dagwaarde auto, kenteken
autowaarde.

Potential future routes: `/autowaarde`, `/autowaarde-berekenen`,
`/auto-vergelijken`, `/merken/bmw`, `/merken/bmw/3-serie`,
`/autowaarde/bmw/3-serie/330e`.

Do **not** generate hundreds of thin SEO pages or keyword-stuff during the MVP;
future pages must carry genuine market information. Metadata uses the official
brand consistently, e.g. title *Autowaarde berekenen & auto's vergelijken |
Echte Auto Waarde*, description *Ontdek wat een auto écht waard is. Vergelijk
soortgelijke auto's op prijs, kilometerstand, uitvoering en opties en krijg een
transparant prijsadvies.* Never hardcode the production domain — use
configuration for the canonical base URL.

---

## 18. Transparency principle

"Echte" creates a strong expectation of honesty. Never present an estimate as
absolute fact.

- ✗ "Deze auto is exact €27.340 waard."
- ✓ "Op basis van 31 vergelijkbare auto's schatten we de marktwaarde op ongeveer €27.300."

Show wherever possible: comparable count, similarity, market distribution,
relevant differences, adjustments, confidence. Trust comes from evidence.

**Do not fake completeness.** If something is heuristic, say so. If data is
synthetic, label it. If confidence is weak, show it. If a source is
unavailable, degrade gracefully. Never build a fake implementation of future
scope that looks real.

---

## 19. Privacy, security, configuration

No authentication, no payments, no accounts, no user tracking, no analytics for
the MVP. Avoid unnecessary personal data. License plates are vehicle
identifiers — treat stored data thoughtfully and never infer or attempt to
identify vehicle owners.

Security: validate API input, avoid unsafe file access and command injection,
never execute LLM-generated code, do not trust imported CSV blindly, set
reasonable request limits, keep secrets out of git. No enterprise security
infrastructure.

Configuration via environment variables with a committed `.env.example` and no
committed secrets: database path, API URL, Ollama URL, Ollama model, AI enabled
flag, optional RDW settings, canonical URL later. Local defaults work with
minimal configuration.

Observability: structured local logs and useful development errors only. No
hosted monitoring, no unnecessary logging of sensitive data.

Search stays SQLite queries plus application filtering — no Elasticsearch,
OpenSearch or Algolia. Caching, if ever needed, is in-process, filesystem or
SQLite — no Redis. Background work, if ever needed, uses FastAPI background
tasks, asyncio, local scripts or SQLite-backed job state — no Celery.

---

## 20. Testing

Valuation logic must be trustworthy. Backend uses **pytest**, prioritising:
normalization, option aliases, candidate filtering, similarity scoring, widening
rules, outlier handling, weighted statistics, valuation adjustments, deal
classification and confidence scoring. Frontend gets focused tests where
valuable — valuation tests matter more than visual snapshots, and coverage
percentage is not a goal.

Fixtures are deterministic. Important valuation tests show input → selected
comparables → adjustments → expected result. Core tests run offline and never
depend on live external APIs.

---

## 21. Project structure

```
apps/web     Next.js frontend
apps/api     FastAPI backend
data/        SQLite database and local development data
docs/        Project documentation
scripts/     Local helper scripts
CLAUDE.md    This specification
README.md    Main documentation
```

Refine internal structure as needed; do not add complexity purely to match this
example.

### Documentation

Maintain `README.md` plus `docs/product.md`, `docs/architecture.md`,
`docs/data-model.md`, `docs/valuation.md`, `docs/data-sources.md`,
`docs/local-ai.md`. Documentation evolves with the implementation — no large
theoretical documents disconnected from the code.

- **README** covers what the product is, MVP status, architecture overview,
  requirements, local setup (Windows-friendly), frontend/backend startup,
  database setup, seed data, Ollama setup, testing, project structure,
  limitations and a data-source disclaimer. It must state clearly that
  synthetic market data is unsuitable for real purchase decisions.
- **docs/data-sources.md** separates vehicle specification data from marketplace
  pricing data and documents each adapter's purpose, cost, license/terms, access
  method, refresh behaviour and limitations.
- **docs/valuation.md** explains filtering, widening, similarity scoring,
  weights, outlier handling, weighted price calculation, mileage/age/option
  adjustments, purchase range, deal classification, confidence scoring,
  limitations and the algorithm version — enough that a developer understands a
  valuation without reading every line of code.

---

## 22. Code quality

Prefer readable code, explicit names, small focused functions, type hints,
testable services and clear domain boundaries. Avoid giant service classes and
route handlers, premature patterns, excessive generic abstractions, unexplained
magic constants and copy-pasted business rules. Business-rule constants live in
configuration or domain modules.

Comments explain valuation assumptions, statistical decisions, non-obvious
normalization and important tradeoffs — not obvious code.

### Dependency checklist

Before adding a significant dependency: Is it needed? Free? Local? Does it
require an account or credit card? Does it send data externally? Is its license
compatible with possible commercial use? Is something already in the stack
sufficient? Reject anything conflicting with zero-cost/local-first. Prefer
mature, actively maintained libraries.

### Error handling

Useful errors for: insufficient comparables, invalid manual vehicle data,
unknown license plate, RDW unavailable, Ollama unavailable, unsupported import.
**AI failure must never cause valuation failure.**

---

## 23. Machine learning and the data moat

Do not start with machine learning. First build and validate normalized data,
comparable selection, similarity, robust statistics, deterministic valuation,
confidence and explainability. Only once sufficient historical data exists
should local ML (scikit-learn, LightGBM, CatBoost, XGBoost) be considered, and
any model must stay explainable enough for the product. ML improves the
valuation engine; it never replaces transparency.

Listing snapshots are a long-term asset: design them so future analytics can
derive days on market, price reductions, relisting, price trends, supply, market
velocity and probable sale behaviour. Synthetic MVP data proves none of these
signals — the schema simply must accept real observations later.

The moat is normalized vehicle data × historical market observations ×
high-quality comparable selection × valuation methodology × explainability. The
AI model is not the moat.

When real marketplace data becomes legitimately available, replacing or
supplementing the synthetic adapter must not require rewriting the vehicle
domain, normalization, comparable engine, valuation engine, API, frontend or AI
layer.

Monetization is out of scope now, but avoid decisions that make future
commercial use unnecessarily hard. Future ideas (real-time comparison,
historical analysis, saved vehicles, alerts, seller valuation, dealer analytics,
purchase reports, richer advisor, market trend pages) are not current scope.

---

## 24. Implementation order

**Phase 1 — Foundation.** Inspect repo and git state · `.gitignore` · project
structure · initial documentation · Next.js frontend · FastAPI backend · SQLite
· SQLAlchemy + migrations · health endpoint.

**Phase 2 — Domain.** Core models · normalization · option taxonomy ·
deterministic synthetic seed of ~100 listings.

**Phase 3 — Comparables.** Candidate filtering · similarity scoring · widening/
fallback · structured explanations · tests.

**Phase 4 — Valuation.** Market statistics · outlier handling · weighted central
valuation · mileage/year adjustments · trim/option adjustments · estimated
market value · purchase range · deal classification · confidence · tests.

**Phase 5 — API.** Vehicle · comparable · valuation · listing/history · market
statistics endpoints.

**Phase 6 — Frontend.** Homepage/input flow · manual vehicle form · valuation
result · market statistics · comparable table · comparable detail · responsive.

**Phase 7 — Local AI.** `AIProvider` · `OllamaProvider` · structured valuation
context · chat endpoint · AI interface · graceful handling when Ollama is down.

**Phase 8 — Optional open data.** Evaluate an RDW adapter, add it only if it
stays free and compatible, keep the manual/synthetic fallback.

**Phase 9 — Polish.** README and docs · local startup scripts · verify
fresh-machine setup · run all tests · frontend lint/typecheck/build · remove
dead code and unused dependencies.

### First vertical slice

A synthetic BMW 330e is selected or entered, and the application loads the
vehicle, finds comparable 330e listings, calculates similarity, shows the
relevant comparables, calculates market statistics, an estimated value, a
recommended purchase range and confidence, and shows why. Build this **before**
significant AI effort; then connect Ollama to explain the same result.

### MVP success criteria

A developer runs everything locally and can open Echte Auto Waarde, select or
enter a vehicle, optionally enter an asking price, receive comparables, inspect
similarity, receive an estimated market value and purchase range, see the deal
classification and confidence, understand the reasoning, and ask the local AI
about the result — with no cloud, paid APIs, hosted databases, paid AI,
marketplace scraping, authentication or subscriptions.

### Known limitation

The initial dataset is synthetic, so the MVP valuation is **not real Dutch
market advice** and demo data is labelled as such. The first MVP validates
architecture, UX, comparable methodology, valuation methodology, explainability
and local AI integration. Real accuracy can only be judged with legitimate real
market data.

---

## 25. Working style

Before a significant phase: inspect existing code, understand the architecture,
summarise what must change, make a short plan, implement, run relevant tests,
fix failures, and update documentation where architecture or behaviour changed.

Do **not** ask for confirmation on routine implementation decisions already
covered by this specification.

**Do ask** before: introducing a paid service · changing the core stack ·
introducing cloud infrastructure · implementing questionable marketplace
scraping · destructive git changes · changing licensing · fundamentally changing
valuation methodology without documenting why.
