import type { MarketStatistics } from "@/lib/api";
import { formatMoney } from "@/lib/format";

/**
 * Where this car sits in the comparable market.
 *
 * Deliberately not a chart. The axis carries position only, and every number
 * lives in a fixed legend below it, so no two labels can ever overlap — not
 * when the asking price equals the estimate, not when the comparable range is
 * narrow, and not when p25, median and p75 nearly coincide.
 *
 * Two further guards keep it readable and honest:
 * - the estimate tick sits above the bar and the asking-price tick below it, so
 *   identical values stay individually visible;
 * - a value outside the comparable range widens the axis (never clipped) and is
 *   called out in words, because that is genuinely worth knowing.
 */

// Minimum axis span, as a share of the median, so a market where every car is
// priced almost identically does not collapse every marker onto one point.
const MINIMUM_SPAN_RATIO = 0.06;

function positionOf(cents: number, min: number, max: number): number {
  if (max <= min) return 50;
  return Math.min(100, Math.max(0, ((cents - min) / (max - min)) * 100));
}

function LegendItem({ swatch, label, value }: { swatch: React.ReactNode; label: string; value: string }) {
  return (
    <div className="flex items-baseline gap-2.5">
      <span aria-hidden="true" className="flex w-3 shrink-0 justify-center self-center">
        {swatch}
      </span>
      <span className="text-sm text-muted">{label}</span>
      <span className="ml-auto text-sm font-medium text-ink tabular-nums">{value}</span>
    </div>
  );
}

export function MarketPosition({
  statistics,
  estimatedMarketValueCents,
  askingPriceCents,
}: {
  statistics: MarketStatistics;
  estimatedMarketValueCents: number;
  askingPriceCents: number | null;
}) {
  const { minPriceCents, maxPriceCents, medianPriceCents, p25PriceCents, p75PriceCents } =
    statistics;

  const values = [
    minPriceCents,
    maxPriceCents,
    estimatedMarketValueCents,
    ...(askingPriceCents !== null ? [askingPriceCents] : []),
  ];
  let axisMin = Math.min(...values);
  let axisMax = Math.max(...values);

  const minimumSpan = Math.max(medianPriceCents * MINIMUM_SPAN_RATIO, 100_00);
  if (axisMax - axisMin < minimumSpan) {
    const padding = (minimumSpan - (axisMax - axisMin)) / 2;
    axisMin -= padding;
    axisMax += padding;
  }

  const bandLeft = positionOf(p25PriceCents, axisMin, axisMax);
  const bandWidth = positionOf(p75PriceCents, axisMin, axisMax) - bandLeft;

  const askingOutsideRange =
    askingPriceCents !== null &&
    (askingPriceCents > maxPriceCents || askingPriceCents < minPriceCents);
  const estimateOutsideRange =
    estimatedMarketValueCents > maxPriceCents || estimatedMarketValueCents < minPriceCents;

  return (
    <div>
      <p className="sr-only">
        De vergelijkbare auto&apos;s liggen tussen {formatMoney(minPriceCents)} en{" "}
        {formatMoney(maxPriceCents)}, met een mediaan van {formatMoney(medianPriceCents)}. De
        geschatte marktwaarde is {formatMoney(estimatedMarketValueCents)}
        {askingPriceCents !== null
          ? ` en de vraagprijs is ${formatMoney(askingPriceCents)}.`
          : "."}
      </p>

      <div aria-hidden="true" className="px-1 py-6">
        <div className="relative h-2.5 rounded-full bg-market-track">
          {/* Middle half of the market. */}
          <div
            className="absolute inset-y-0 rounded-full bg-market-band"
            style={{ left: `${bandLeft}%`, width: `${Math.max(bandWidth, 0.5)}%` }}
          />
          {/* Median. */}
          <span
            className="absolute inset-y-[-2px] w-0.5 rounded-full bg-muted"
            style={{ left: `${positionOf(medianPriceCents, axisMin, axisMax)}%` }}
          />
          {/* Estimate sits above the bar, asking price below it, so the two stay
              distinguishable even at an identical position. */}
          <span
            className="absolute -top-2.5 h-[1.4rem] w-[3px] rounded-full bg-brand"
            style={{
              left: `${positionOf(estimatedMarketValueCents, axisMin, axisMax)}%`,
              transform: "translateX(-50%)",
            }}
          />
          {askingPriceCents !== null ? (
            <span
              className="absolute -bottom-2.5 h-[1.4rem] w-[3px] rounded-full bg-ink/70"
              style={{
                left: `${positionOf(askingPriceCents, axisMin, axisMax)}%`,
                transform: "translateX(-50%)",
              }}
            />
          ) : null}
        </div>

        <div className="mt-4 flex justify-between text-xs text-subtle">
          <span>goedkoper</span>
          <span>duurder</span>
        </div>
      </div>

      <div className="grid gap-x-10 gap-y-2.5 border-t border-line pt-4 lg:grid-cols-2">
        <LegendItem
          swatch={<span className="h-4 w-[3px] rounded-full bg-brand" />}
          label="Geschatte marktwaarde"
          value={formatMoney(estimatedMarketValueCents)}
        />
        {askingPriceCents !== null ? (
          <LegendItem
            swatch={<span className="h-4 w-[3px] rounded-full bg-ink/70" />}
            label="Vraagprijs"
            value={formatMoney(askingPriceCents)}
          />
        ) : null}
        <LegendItem
          swatch={<span className="h-2.5 w-3 rounded-sm bg-market-band" />}
          label="Middenmoot van de markt"
          value={`${formatMoney(p25PriceCents)} – ${formatMoney(p75PriceCents)}`}
        />
        <LegendItem
          swatch={<span className="h-4 w-0.5 rounded-full bg-muted" />}
          label="Mediaan vraagprijs"
          value={formatMoney(medianPriceCents)}
        />
        <LegendItem
          swatch={<span className="h-0.5 w-3 rounded-full bg-line-strong" />}
          label="Volledige spreiding"
          value={`${formatMoney(minPriceCents)} – ${formatMoney(maxPriceCents)}`}
        />
      </div>

      {askingOutsideRange || estimateOutsideRange ? (
        <p className="mt-4 text-sm text-muted">
          {askingOutsideRange
            ? `De vraagprijs valt ${
                askingPriceCents! > maxPriceCents ? "boven" : "onder"
              } het bereik van alle vergelijkbare auto's.`
            : `De geschatte marktwaarde valt ${
                estimatedMarketValueCents > maxPriceCents ? "boven" : "onder"
              } het bereik van de vergelijkbare auto's, door de correcties op deze auto.`}
        </p>
      ) : null}
    </div>
  );
}
