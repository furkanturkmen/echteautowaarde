import type { Adjustment } from "@/lib/api";
import { MoneyValue } from "@/components/MoneyValue";
import { ADJUSTMENT_LABELS, describeAdjustment } from "@/lib/labels";

/**
 * How the market basis became this estimate.
 *
 * Only adjustments the backend actually computed are listed; when the car
 * matches its comparable group closely, the engine returns none and the
 * interface says exactly that instead of inventing corrections.
 *
 * The wording is composed here from each adjustment's structured detail, so the
 * consumer reads Dutch while every figure still comes from the engine.
 */
export function AdjustmentBreakdown({
  marketBasisCents,
  adjustments,
  estimatedMarketValueCents,
  comparableCount,
}: {
  marketBasisCents: number;
  adjustments: Adjustment[];
  estimatedMarketValueCents: number;
  comparableCount: number;
}) {
  return (
    <div>
      <dl className="divide-y divide-line">
        <div className="flex items-baseline justify-between gap-6 py-3">
          <dt>
            <span className="text-ink">Marktbasis</span>
            <p className="mt-0.5 text-sm text-muted">
              Gewogen mediaan van {comparableCount} vergelijkbare auto&apos;s
            </p>
          </dt>
          <dd>
            <MoneyValue cents={marketBasisCents} size="base" />
          </dd>
        </div>

        {adjustments.length === 0 ? (
          <div className="py-3 text-sm text-muted">
            Geen correcties nodig: deze auto komt op kilometerstand, bouwjaar, opties en
            uitvoering overeen met de vergelijkbare auto&apos;s.
          </div>
        ) : (
          adjustments.map((adjustment) => (
            <div
              key={adjustment.type}
              className="flex items-baseline justify-between gap-6 py-3"
            >
              <dt>
                <span className="text-ink">
                  {ADJUSTMENT_LABELS[adjustment.type] ?? adjustment.type}
                </span>
                {describeAdjustment(adjustment.type, adjustment.detail) ? (
                  <p className="mt-0.5 text-sm text-muted">
                    {describeAdjustment(adjustment.type, adjustment.detail)}
                  </p>
                ) : null}
              </dt>
              <dd
                className={
                  adjustment.amountCents >= 0
                    ? "text-positive whitespace-nowrap"
                    : "text-negative whitespace-nowrap"
                }
              >
                <MoneyValue cents={adjustment.amountCents} size="base" signed />
              </dd>
            </div>
          ))
        )}

        <div className="flex items-baseline justify-between gap-6 pt-3">
          <dt className="font-medium text-ink">Geschatte marktwaarde</dt>
          <dd>
            <MoneyValue cents={estimatedMarketValueCents} size="lead" />
          </dd>
        </div>
      </dl>
    </div>
  );
}
