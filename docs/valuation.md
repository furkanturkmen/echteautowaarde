# Comparable selection and valuation methodology

This document explains how a valuation is produced. A developer should be able
to understand any result from this page plus the domain modules in
`apps/api/echte_auto_waarde/domain/`, without reading every line of code.

*Status: implemented (`valuation-v0.1`). Every constant below lives in a
configuration dataclass in the domain layer — `SimilarityWeights`,
`ComparableCriteria`, `ValuationConfig`, `DealThresholds` — and can be replaced
per search or per request.*



## Measuring the model against real evidence

Once a lawful real dataset has been imported, the engine can be measured against
it offline. The framework runs the production valuation code; it reimplements
nothing and tunes nothing.

### What is measured, and what is not

**This is not accuracy.** An asking price is what somebody was asking — not what
a car sold for, and not what it was worth. A dealer's optimistic price and a
private seller's quick-sale price are both legitimate observations, and an
estimate that differs from either is not thereby wrong. We have no sale prices,
so we cannot measure accuracy, and nothing here should ever be described as
error against truth.

What is measured is **deviation from observed asking prices**: whether the
valuation is coherent with the market it was given. Consistently large deviation
is a reason to investigate; small deviation means the model agrees with sellers,
which is a weaker claim than being right.

### Leave-one-out

Every eligible listing becomes a target in turn:

1. its vehicle is the target,
2. **that listing is excluded from the evidence** (`exclude_listing_id` at the
   comparable boundary, so a listing can never value itself),
3. the normal comparable pipeline runs,
4. the normal valuation pipeline runs,
5. the estimate is compared with that listing's observed asking price.

The asking price is deliberately not passed to the engine: the number being
measured must not influence the number doing the measuring.

Only **real evidence** takes part — imported and other non-synthetic sources —
regardless of the configured market mode. Demo listings are never evaluated and
never used as evidence.

### Metrics

Evaluated count, insufficient-evidence count, median absolute deviation in euros
and as a percentage, P75 and P90 absolute percentage deviation, mean signed
percentage deviation, and the share estimated above and below the observed ask.
Segments are reported by model, model year, mileage band, transmission, fuel,
body type, trim, comparable-count band, similarity band and confidence band, and
a group is only reported when it has at least five members.

The confidence diagnostic asks one directional question — do higher-confidence
valuations deviate less than low-confidence ones? — and reports the answer.
**It changes nothing.** Weight calibration would be a separate, deliberate phase.

The largest deviations are listed with their evidence and adjustments for
engineering diagnosis. Nothing is excluded from the metrics for being an outlier.

### Example

```powershell
python -m echte_auto_waarde.evaluate_market --source-key import:dealer-example
python -m echte_auto_waarde.evaluate_market --make BMW --model "3 Serie" --output report.json
```

Nothing is stored: an evaluation creates no valuation records and leaves
consumer history untouched.

### Limitations

- **Not point-in-time.** Evaluation uses the current state of each listing, not
  the market as it stood when that listing was observed. Historical
  reconstruction would need evidence to be rebuilt as of a moment in time, which
  is a redesign, not a flag. This is not backtesting and is not described as it.
- Asking prices are not sale prices, so no result is a measure of accuracy.
- A dataset dominated by one seller measures that seller's pricing policy.
- Small segments are dropped rather than reported unreliably.

### The intended process

```
lawful real dataset -> import -> evaluate -> inspect diagnostics
   -> only then consider methodology calibration
```

Calibration is deliberately last, and deliberately a separate decision.

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
| Engine variant | 0.12 | Displacement and engine family (`1.5 eTSI`) where both titles state one, otherwise the descriptions compared whole; closeness is covered by power |
| Year | 0.12 | Linear over a five-year tolerance |
| Body type | 0.08 | Exact match 1.0, otherwise 0.2 |
| Transmission | 0.07 | Exact match or nothing |
| Trim | 0.06 | Exact match 1.0, otherwise 0.2 |
| Power | 0.05 | Linear over a 100 hp tolerance |
| Drivetrain | 0.05 | Exact match 1.0, otherwise 0.25 |
| Options | 0.04 | Importance-weighted overlap (shared importance / union importance) |

### Characteristics neither vehicle states

A factor that one or both vehicles leave unstated **takes no part in the score**.
It is dropped from the weighted average and the remaining weights carry the
result, which is recorded in `SimilarityBreakdown.unevaluated` so the shortfall
can be explained.

This replaced a fixed score of 0.4 for unknowns. That fixed score compressed the
whole scale: dealer listings publish no generation, power, drivetrain or option
list, so 0.26 of the weight scored 0.4 on every comparison no matter what the
cars were. Two identical Golfs reached 0.805 and the worst pair in the same
dataset reached 0.382 — a usable range of 0.42, inside which a genuine match and
a loose one were hard to tell apart. On the same 39 listings the repaired scale
runs 0.337 to 0.998.

Renormalising must not reward an empty description, so the divisor never falls
below **`MINIMUM_EVALUABLE_WEIGHT` (0.5)**. A vehicle described only by make,
model, year, mileage and trim leaves 0.32 of the weight evaluable and therefore
cannot exceed `0.32 / 0.5 = 0.64`, which keeps it under the cutoff. That is
deliberate: three matching numbers are not a comparison, and the honest answer is
insufficient data rather than a confident-looking valuation.

### The cutoff

`ComparableCriteria` carries the per-search preferences a future "what matters to
me" interface will set: `min_similarity` (default **0.65**), `max_comparables`,
`required_option_keys`, `require_same_transmission` and `require_same_engine`.

The cutoff was 0.55, chosen against the compressed scale. On the repaired scale
that number admitted almost everything, so it was re-measured by leave-one-out on
both datasets:

| Cutoff | Real pilot (39 listings) | Demo dataset (122 listings) |
|---|---|---|
| 0.55 | median 13.9%, P75 18.7%, 1 without a result | median 9.6%, P75 17.9%, 0 without a result |
| 0.60 | median 10.9%, P75 21.2%, 1 | median 9.0%, P75 15.4%, 0 |
| **0.65** | **median 9.6%, P75 14.9%, 1** | **median 8.5%, P75 14.8%, 1** |
| 0.70 | median 7.6%, P75 12.9%, 2 | median 7.4%, P75 13.9%, 7 |
| 0.75 | median 7.6%, P75 11.8%, 6 | median 7.3%, P75 15.1%, 17 |

Deviation keeps falling above 0.65, but so does coverage: at 0.70 six percent of
cars get no valuation at all, and at 0.75 a seventh of them do not. 0.65 lowers
deviation at every percentile while still valuing all but one car in each
dataset, and it is a modest enough move not to be tuned to the edge of a
39-listing sample.

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
below the similarity threshold.

A shortage often says more about the description than about the market: a
characteristic the target leaves blank can never be evaluated, so it caps how
similar any advertisement can be. The refusal therefore carries
`unstatedTargetFields` — the scored characteristics the entered vehicle does not
state, heaviest first — and the interface names the heaviest few in Dutch
("Vul brandstof, transmissie en motor in") instead of only reporting that
nothing was close enough.

The interface surfaces this in Dutch as *"We
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
