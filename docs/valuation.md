# Comparable selection and valuation methodology

This document explains how a valuation is produced. A developer should be able
to understand any result from this page plus the domain modules in
`apps/api/echte_auto_waarde/domain/`, without reading every line of code.

*Status: implemented (`valuation-v0.1`). Every constant below lives in a
configuration dataclass in the domain layer — `SimilarityWeights`,
`ComparableCriteria`, `ValuationConfig`, `DealThresholds` — and can be replaced
per search or per request.*


## Which evidence a valuation may use

Before any of the methodology below runs, the comparable query decides what
counts as evidence at all. The rule lives in one function
(`domain/evidence.py`) and is applied in one place (`load_candidates`), so the
valuation engine receives comparables without knowing which adapter produced
them.

| Market mode | Target vehicle | Evidence used |
|---|---|---|
| `DEMO` (default) | anything | the synthetic demo market |
| `REAL` | a demo vehicle | the synthetic demo market |
| `REAL` | a real vehicle (manual, register-enriched, imported) | **imported and other real sources only** |

A demo car is valued against the demo market because it is a fictional car. A
real car in real-market mode is never valued against invented listings, and a
shortage of real comparables is **never** topped up with demo data: the honest
answer is the existing insufficient-data result, with its confidence and its
explanation.

Every valuation reports what it actually rested on, derived from the listings
behind it rather than assumed.

## Pipeline

```
vehicle -> normalize -> candidate filtering -> similarity scoring -> drop weak candidates
-> outlier removal -> weighted market statistics -> transparent adjustments
-> estimated market value -> recommended purchase range -> confidence -> deal classification
```

The engine is deterministic, transparent, testable and configurable. No LLM
takes part in any step: the AI layer only explains the finished structured
result.

## 1. Normalization

Make, model, generation, body type, fuel type, transmission, drivetrain, trim
and option names are mapped to canonical values before anything else happens.
`BMW` / `bmw` / `B.M.W.` normalize identically; `Automaat` / `Automatic` /
`AUTO` map to one canonical transmission. Raw values are retained.

Trim and package survive normalization because they materially affect value, and
an appearance package is never conflated with a performance model: a `BMW 330e M
Sport` is not a `BMW M3`.

## 2. Candidate filtering and widening

Hard/near-hard filters first — same make, same model, compatible generation,
body type, fuel/powertrain, and transmission where it matters — then scoring of
whatever remains.

Filters that are too strict return nothing, so the engine widens in documented
levels:

1. same model + generation + powertrain
2. same model + generation, broader engine range
3. same model, nearby years

Any widening actually used is reported in the result and lowers confidence.

## 3. Similarity scoring

Similarity is expressed on a `0.00`-`1.00` scale throughout the system
(`domain/similarity.py`). The default weights sum to 1.0:

| Factor | Weight | Scoring |
|---|---|---|
| Fuel / powertrain | 0.15 | Exact match 1.0; related powertrains score partially (PHEV vs hybrid 0.45, petrol vs hybrid 0.35, petrol vs LPG 0.5); unrelated 0.0 |
| Mileage | 0.14 | Linear over a 60.000 km tolerance (about four years of average Dutch use) |
| Generation | 0.12 | Exact match or nothing |
| Engine variant | 0.12 | Exact match or nothing; closeness is covered by power |
| Year | 0.12 | Linear over a five-year tolerance |
| Body type | 0.08 | Exact match 1.0, otherwise 0.2 |
| Transmission | 0.07 | Exact match or nothing |
| Trim | 0.06 | Exact match 1.0, otherwise 0.2 |
| Power | 0.05 | Linear over a 100 hp tolerance |
| Drivetrain | 0.05 | Exact match 1.0, otherwise 0.25 |
| Options | 0.04 | Importance-weighted overlap (shared importance / union importance) |

A missing value on either side scores 0.4 — an unknown is neither a match nor a
mismatch, and must not be rewarded like one.

`ComparableCriteria` carries the per-search preferences a future "what matters to
me" interface will set: `min_similarity` (default 0.55), `max_comparables`,
`required_option_keys`, `require_same_transmission` and `require_same_engine`.

Every comparable returns structured reasons and differences, which the frontend
renders as **Overeenkomsten** and **Verschillen**.

## 4. Outlier handling

Extreme listings must not dominate a small comparable group, so prices are
screened with a **modified z-score based on the median absolute deviation
(MAD)**, flagging anything above 3.5. MAD was chosen over the IQR because it
stays meaningful on the small groups this product works with (often 8-30
listings) and assumes no particular distribution.

Two guards keep the method honest: groups smaller than four are never trimmed
(with that little evidence an outlier cannot be told apart from the market), and
at most 25% of a group can ever be removed. Removed listings and their scores
are available for debugging, and the count appears in the market statistics.

## 5. Market statistics

Every valuation reports: comparable count, minimum, maximum and median asking
price, weighted median, average mileage, average year, price dispersion and
similarity statistics. These exist so a user sees the market, not only a single
number.

## 6. Central price

A robust similarity-weighted central price — not an arithmetic mean — forms the
market basis. Listings closer to the target vehicle carry more weight.

## 7. Adjustments

Adjustments are structured (`type`, `amount`, `reason`) and conservative:

| Adjustment | Basis | Cap |
|---|---|---|
| `MILEAGE` | 6 cents per km of difference from the group median mileage, applied only beyond 1.000 km | 15% of the market basis |
| `AGE` | 2,5% of the market basis per model year of difference from the group median year | 10% of the market basis |
| `OPTIONS` | 600 euro per point of option-importance difference from the group median | 8% of the market basis |
| `TRIM` | 800 euro for a sport/appearance package, scaled by the share of the group that lacks (or has) it | — |

Every constant is a documented assumption, not a measured market figure, and
each is deliberately conservative for two reasons: comparable prices already
contain most of the effect of age and equipment, and a large correction on thin
evidence is a worse answer than a small one. The mileage model is flat for now
and may become model- or category-dependent once real data exists.

Option value sits well below retail — used buyers pay for equipment, but not
what it cost new — and options already influence similarity, so their price
effect stays modest. Trim packages are deliberately kept out of a vehicle's
option list (see the option taxonomy) so one package cannot be counted twice.

Only real computed adjustments are ever returned or displayed, and the estimate
is rounded to whole euros because cent-level precision would imply accuracy the
evidence does not support.

## 8. Estimated market value

The market basis plus adjustments gives `estimatedMarketValue` — the best
estimate from current comparable data, always communicated as an estimate
(*geschatte marktwaarde*, never *exacte waarde*).

## 9. Recommended purchase range

`recommendedBuyPriceLow` / `recommendedBuyPriceHigh` answer *"wat zou jij
betalen?"* and are derived as **94%-98% of the estimated market value**. The
range sits below the estimate on purpose: it is what a buyer should aim to pay,
not what the market lists, and the spread reflects the negotiation room typical
of Dutch asking prices.

## 10. Deal classification

Owned by `domain/deals.py`, comparing asking price against the estimated market
value:

| Ratio (asking / estimate) | Code | Dutch label |
|---|---|---|
| <= 0.92 | `EXCELLENT_DEAL` | Zeer goede deal |
| <= 0.97 | `GOOD_DEAL` | Goede koop |
| <= 1.04 | `FAIR_PRICE` | Eerlijke prijs |
| <= 1.12 | `EXPENSIVE` | Aan de dure kant |
| > 1.12 | `VERY_EXPENSIVE` | Erg duur |

The band around 1.0 is wide on purpose: comparable asking prices carry real
spread, so a small deviation is market noise rather than something worth
flagging to a consumer. Thresholds exist in exactly one place; the frontend only
maps codes to labels.

## 11. Confidence

`confidenceScore` is a data-quality measurement, never a random or
model-generated number (`domain/confidence.py`):

| Factor | Weight | Full score at |
|---|---|---|
| Comparable count | 0.30 | 20 comparables |
| Average similarity | 0.25 | Similarity 1.0; nothing at or below 0.5 |
| Price dispersion | 0.20 | Relative IQR 0; nothing at or above 0.30 |
| Observation age | 0.10 | All observations within 60 days |
| Data completeness | 0.10 | No missing fields, all option texts resolved |
| Source quality | 0.05 | Source quality 1.0 |

The weighted result is then multiplied by 0.88 per widening level, because a
widened search means the strict evidence was not there. The synthetic source
scores 0.35 on quality, which is exactly why demo valuations cannot reach high
confidence.

Structured positive and negative factors accompany the score — including a
`search_widened` entry whenever widening happened — so the frontend and the AI
can explain uncertainty concretely. Below 0.55 a result counts as low
confidence.

## 12. Insufficient data

Below three comparables no valuation is produced at all. The API returns HTTP
200 with `sufficientData: false`, no value, and an `insufficientDataReason`
explaining the shortage; the comparable search separately reports how many
candidates were considered, how many the filters rejected and how many fell
below the similarity threshold. The interface surfaces this in Dutch as *"We
hebben te weinig vergelijkbare auto's om met voldoende zekerheid een waarde te
bepalen."*

## Algorithm version

Results carry an identifier such as `valuation-v0.1` so valuations produced by
different methodology versions stay comparable later.

## Limitations

- MVP data is synthetic: the methodology can be validated, Dutch market accuracy
  cannot.
- Adjustments are conservative heuristics, not a trained model.
- No machine learning is used. It is only considered once enough real historical
  observations exist, and any future model must stay explainable.
