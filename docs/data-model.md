# Data model

Entities live in `apps/api/echte_auto_waarde/models/`. Persistence uses
SQLAlchemy 2.0 declarative models with Alembic migrations.

*Status: implemented.*

## Conventions

- **Money**: integer cents, EUR. No floating-point money arithmetic.
- **Time**: UTC in the database, Dutch formatting in the frontend.
- **Raw values**: normalization keeps the original source text alongside the
  canonical value so any mapping stays traceable.
- **History**: observations are appended, never overwritten.

## Entities

### Vehicle

The vehicle/specification identity: `licensePlate`, `make`, `model`,
`generation`, `bodyType`, `fuelType`, `transmission`, `engineDescription`,
`engineDisplacement`, `powerKw`, `powerHp`, `drivetrain`, `year`,
`firstRegistrationDate`, `mileage`, `trim`, `color`, `doors`, `seats`,
`catalogPrice`, `sourceMetadata`.

Fields exist because they contribute to matching, valuation or display — not for
completeness.

### VehicleSpecification

Structured technical attributes that do not belong on the basic vehicle entity.

### VehicleOptionDefinition

The canonical definition of an option plus its aliases. One canonical option per
real-world feature: `Adaptive Cruise Control`, `ACC` and `adaptieve cruise` all
resolve to the same definition. Options carry configurable importance — they are
not equally valuable.

### VehicleOption

Association between a vehicle and a canonical option, retaining the raw source
text.

### Seller

`sellerType` (`PRIVATE` / `DEALER` / `UNKNOWN`), name, city. Synthetic sellers
are fictional.

### Listing

A market offering: `vehicleId`, `sellerId`, `dataSourceId`, `externalReference`,
`askingPrice`, `url`, `status`, `firstSeenAt`, `lastSeenAt`, timestamps.

### ListingSnapshot

An observation of a listing at a point in time: `observedAt`, `askingPrice`,
`mileage`, `status`, `rawMetadata`. Snapshots are the long-term asset — they are
what eventually allows days-on-market, price reductions, relisting behaviour,
price trends, supply and market velocity to be derived from real observations.
Synthetic data does not prove any of those signals; the schema simply has to
accept real ones later.

### DataSource

Where data came from: `SYNTHETIC`, `CSV_IMPORT`, `RDW`, `MANUAL`.

### Valuation

A stored valuation result: `targetVehicleId`, `createdAt`,
`estimatedMarketValue`, `recommendedBuyPriceLow`, `recommendedBuyPriceHigh`,
`confidenceScore`, `comparableCount`, `algorithmVersion`.

### ComparableResult

Why a listing was selected: the listing, `similarityScore`, structured reasons,
structured differences and its contribution to the adjusted price.

## Listing lifecycle

`ACTIVE` · `PRICE_REDUCED` · `REMOVED` · `LIKELY_SOLD` · `RELISTED` · `UNKNOWN`

A disappeared listing is **not** automatically sold. `LIKELY_SOLD` is only set
when an explicit documented heuristic supports it. Observed facts (snapshots)
stay separate from inferred states (lifecycle), because future analytics depend
on that distinction.

## Relationships

```
DataSource 1-* Listing *-1 Vehicle 1-* VehicleOption *-1 VehicleOptionDefinition
                  |                \-1 VehicleSpecification
                  |-1 Seller
                  \-* ListingSnapshot

Vehicle 1-* Valuation 1-* ComparableResult *-1 Listing
```
