# Product

## What Echte Auto Waarde is

An automotive market intelligence and valuation application for Dutch consumers,
with an AI explanation layer on top. It is not a chatbot about cars: the core
product remains fully useful when AI is disabled.

## The question it answers

> **Wat zou jij voor deze auto betalen?**

The answer is never a bare number. Every valuation ships with the evidence
behind it: which comparable cars were found, why they are comparable, how they
differ, which adjustments were applied, and how confident the estimate is.

## User journey

1. **Input** — kenteken, manual vehicle entry, and optionally the asking price
   (`vraagprijs`). Advertisement-URL input is future scope.
2. **Comparison** — the deterministic comparable engine selects similar vehicles
   from the local dataset and scores their similarity.
3. **Valuation** — robust market statistics plus transparent adjustments produce
   an estimated market value (`geschatte marktwaarde`) and a recommended
   purchase range (`prijsadvies`).
4. **Evidence** — the comparable table, market position, adjustments and
   confidence factors are all inspectable.
5. **Explanation** — the local AI answers questions about the result it was
   given.

## Consumer vocabulary

The interface is Dutch; the code is English.

| UI | Code | Meaning |
|---|---|---|
| Autowaarde / Geschatte marktwaarde | `estimatedMarketValue` | Best estimate from comparable data |
| Vraagprijs | `askingPrice` | What the seller asks |
| Prijsadvies | `recommendedBuyPriceLow` / `High` | Sensible purchase/negotiation range |
| Vergelijkbare auto's | `comparableVehicles` | The evidence set |
| Betrouwbaarheid | `confidenceScore` | Data-quality measure, not an AI score |

Deal classification, owned by the backend:

| Code | Dutch label |
|---|---|
| `EXCELLENT_DEAL` | Zeer goede deal |
| `GOOD_DEAL` | Goede koop |
| `FAIR_PRICE` | Eerlijke prijs |
| `EXPENSIVE` | Aan de dure kant |
| `VERY_EXPENSIVE` | Erg duur |

## Transparency

"Echte" sets an expectation of honesty. Estimates are presented as estimates:

- ✗ "Deze auto is exact €27.340 waard."
- ✓ "Op basis van 31 vergelijkbare auto's schatten we de marktwaarde op ongeveer €27.300."

When comparable evidence is too thin, the product says so instead of producing a
confident-looking number.

## Priorities

Market comparison beats AI features. Transparency beats visual polish. Better
comparable data beats more features. A simple reliable local MVP beats
speculative scalability.
