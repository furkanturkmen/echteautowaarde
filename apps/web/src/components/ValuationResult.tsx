import { AdjustmentBreakdown } from "@/components/AdjustmentBreakdown";
import { ComparableEvidence } from "@/components/ComparableEvidence";
import { ConfidenceIndicator } from "@/components/ConfidenceIndicator";
import { DealBadge } from "@/components/DealBadge";
import { MarketPosition } from "@/components/MarketPosition";
import { MoneyValue, StatDisplay } from "@/components/MoneyValue";
import { VehicleSummary } from "@/components/VehicleSummary";
import type { Valuation } from "@/lib/api";
import { formatMileage, formatMoney, formatPercentage } from "@/lib/format";
import { DEAL_LABELS, WIDENING_LEVEL_LABELS } from "@/lib/labels";

/**
 * The valuation result — the core screen of the product.
 *
 * Reading order is deliberate: which car, what it is worth, what to pay, what
 * is asked, how that compares, how certain we are, and then the evidence. Every
 * figure comes from the backend response; nothing is filled in to make the
 * layout look complete.
 */
export function ValuationResult({ valuation }: { valuation: Valuation }) {
  const estimate = valuation.estimatedMarketValueCents;
  const low = valuation.recommendedBuyPriceLowCents;
  const high = valuation.recommendedBuyPriceHighCents;
  const statistics = valuation.marketStatistics;
  const asking = valuation.askingPriceCents;
  const deal = valuation.dealClassification;

  if (estimate === null || low === null || high === null) {
    // A sufficient-data valuation always carries these; this guard only keeps
    // the component honest rather than rendering a broken screen.
    return null;
  }

  return (
    <>
      <VehicleSummary vehicle={valuation.vehicle} />

      {/* The five-second read: value, advice, asking price, deal, confidence. */}
      <section
        aria-labelledby="waarde-titel"
        className="mt-6 rounded-eaw-lg border border-line bg-surface shadow-eaw"
      >
        <div className="grid lg:grid-cols-[1.35fr_1fr]">
          <div className="p-6 sm:p-8">
            <h2
              id="waarde-titel"
              className="text-xs font-medium tracking-wide text-muted uppercase"
            >
              Geschatte marktwaarde
            </h2>
            <p className="mt-2 text-brand">
              <MoneyValue cents={estimate} size="hero" />
            </p>
            <p className="mt-3 max-w-md text-sm text-muted">
              Op basis van {valuation.comparableCount} vergelijkbare auto&apos;s schatten we de
              marktwaarde op ongeveer {formatMoney(estimate)}.
            </p>

            <div className="mt-8 rounded-eaw border border-brand/15 bg-brand-soft p-5">
              <p className="text-xs font-medium tracking-wide text-brand uppercase">
                Prijsadvies
              </p>
              <p className="mt-1 text-brand">
                <MoneyValue cents={low} size="lead" />
                <span className="mx-2 text-brand/50">–</span>
                <MoneyValue cents={high} size="lead" />
              </p>
              <p className="mt-2 text-sm text-brand/80">
                Wat je voor deze auto zou moeten proberen te betalen.
              </p>
            </div>
          </div>

          <div className="border-t border-line p-6 sm:p-8 lg:border-t-0 lg:border-l">
            {asking !== null ? (
              <div className="pb-6">
                <StatDisplay label="Vraagprijs">
                  <MoneyValue cents={asking} size="lead" />
                </StatDisplay>
                {deal ? (
                  <div className="mt-4">
                    <DealBadge classification={deal} size="lg" />
                    <p className="mt-3 text-sm text-muted">
                      {DEAL_LABELS[deal].explanation} Verschil met de geschatte marktwaarde:{" "}
                      <span className="whitespace-nowrap text-ink tabular-nums">
                        <MoneyValue cents={asking - estimate} size="sm" signed />
                      </span>
                      .
                    </p>
                    {/* A deal label describes the asking price against the market.
                        Without this line, "Eerlijke prijs" could be misread as
                        "so this is the amount to pay" — which is what the
                        prijsadvies, not the classification, answers. */}
                    <p className="mt-3 text-sm font-medium text-ink">
                      {asking > high ? (
                        <>
                          Dat is{" "}
                          <span className="whitespace-nowrap tabular-nums">
                            {formatMoney(asking - high)}
                          </span>{" "}
                          meer dan ons prijsadvies.
                        </>
                      ) : asking < low ? (
                        <>
                          Dat is{" "}
                          <span className="whitespace-nowrap tabular-nums">
                            {formatMoney(low - asking)}
                          </span>{" "}
                          minder dan ons prijsadvies.
                        </>
                      ) : (
                        <>Deze vraagprijs valt binnen ons prijsadvies.</>
                      )}
                    </p>
                  </div>
                ) : null}
              </div>
            ) : (
              <div className="pb-6">
                <StatDisplay label="Vraagprijs">
                  <span className="text-muted">Niet ingevuld</span>
                </StatDisplay>
                <p className="mt-2 text-sm text-muted">
                  Vul een vraagprijs in om te zien of die eerlijk is.
                </p>
              </div>
            )}

            <div className="border-t border-line pt-6">
              {valuation.confidenceScore !== null ? (
                <ConfidenceIndicator
                  score={valuation.confidenceScore}
                  factors={valuation.confidenceFactors}
                />
              ) : null}
            </div>
          </div>
        </div>
      </section>

      {statistics ? (
        <section aria-labelledby="markt-titel" className="mt-12">
          <h2 id="markt-titel" className="text-lg font-semibold text-ink">
            Marktpositie
          </h2>
          <p className="mt-1 text-sm text-muted">
            Waar deze auto staat tussen de vergelijkbare advertenties.
          </p>

          <div className="mt-5 rounded-eaw-lg border border-line bg-surface p-6 sm:p-8">
            <MarketPosition
              statistics={statistics}
              estimatedMarketValueCents={estimate}
              askingPriceCents={asking}
            />

            <dl className="mt-8 grid grid-cols-2 gap-6 border-t border-line pt-6 sm:grid-cols-4">
              <StatDisplay label="Vergelijkbare auto's">
                <span className="text-base font-medium tabular-nums">
                  {statistics.comparableCount}
                </span>
              </StatDisplay>
              <StatDisplay label="Gemiddelde km-stand">
                <span className="text-base font-medium tabular-nums">
                  {formatMileage(statistics.averageMileageKm)}
                </span>
              </StatDisplay>
              <StatDisplay label="Gemiddeld bouwjaar">
                <span className="text-base font-medium tabular-nums">
                  {statistics.averageYear ?? "—"}
                </span>
              </StatDisplay>
              <StatDisplay label="Gemiddelde overeenkomst">
                <span className="text-base font-medium tabular-nums">
                  {formatPercentage(statistics.averageSimilarity)}
                </span>
              </StatDisplay>
            </dl>

            {statistics.outliersRemoved > 0 ? (
              <p className="mt-4 text-sm text-muted">
                {statistics.outliersRemoved} advertentie(s) met een sterk afwijkende prijs zijn
                buiten de berekening gelaten.
              </p>
            ) : null}
          </div>
        </section>
      ) : null}

      <section aria-labelledby="vergelijking-titel" className="mt-12">
        <h2 id="vergelijking-titel" className="text-lg font-semibold text-ink">
          Vergelijkbare auto&apos;s
        </h2>
        <p className="mt-1 text-sm text-muted">
          Dit zijn de advertenties waarop de waardering is gebaseerd. Open een auto om te zien
          waarin hij overeenkomt en verschilt.
        </p>

        <div className="mt-5 rounded-eaw-lg border border-line bg-surface p-5 sm:p-6">
          <ComparableEvidence target={valuation.vehicle} comparables={valuation.comparables} />
        </div>
      </section>

      <section aria-labelledby="opbouw-titel" className="mt-12">
        <h2 id="opbouw-titel" className="text-lg font-semibold text-ink">
          Opbouw van de waardering
        </h2>
        <p className="mt-1 text-sm text-muted">
          Van de marktbasis naar de geschatte marktwaarde van deze auto.
        </p>

        <div className="mt-5 grid items-start gap-5 lg:grid-cols-[1.35fr_1fr]">
          <div className="rounded-eaw-lg border border-line bg-surface p-6 sm:p-8">
            {valuation.marketBasisCents !== null ? (
              <AdjustmentBreakdown
                marketBasisCents={valuation.marketBasisCents}
                adjustments={valuation.adjustments}
                estimatedMarketValueCents={estimate}
                comparableCount={valuation.comparableCount}
              />
            ) : (
              <p className="text-sm text-muted">
                Voor deze waardering is de marktbasis niet vastgelegd.
              </p>
            )}
          </div>

          <div className="rounded-eaw-lg border border-line bg-surface p-6 text-sm sm:p-8">
            <h3 className="font-medium text-ink">Hoe deze auto&apos;s zijn gekozen</h3>
            {WIDENING_LEVEL_LABELS[valuation.wideningLevel] ? (
              <p className="mt-2 text-muted">
                Selectie: {WIDENING_LEVEL_LABELS[valuation.wideningLevel]}.
                {valuation.wideningLevel > 0
                  ? " De zoekopdracht is verbreed omdat er te weinig strikt vergelijkbare auto's waren; dat verlaagt de betrouwbaarheid."
                  : ""}
              </p>
            ) : null}
            {statistics ? (
              <p className="mt-3 text-muted">
                Prijzen van {formatMoney(statistics.minPriceCents)} tot{" "}
                {formatMoney(statistics.maxPriceCents)}, overeenkomst tussen{" "}
                {formatPercentage(statistics.minSimilarity)} en{" "}
                {formatPercentage(statistics.maxSimilarity)}.
              </p>
            ) : null}
            <p className="mt-4 border-t border-line pt-4 text-subtle">
              Methodiek {valuation.algorithmVersion}. {valuation.dataDisclaimer}
            </p>
          </div>
        </div>
      </section>
    </>
  );
}
