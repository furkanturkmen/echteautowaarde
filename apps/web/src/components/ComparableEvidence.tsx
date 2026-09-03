"use client";

import { ChevronDown } from "lucide-react";
import { Fragment, useMemo, useState } from "react";

import type { Comparable, Vehicle } from "@/lib/api";
import { MoneyValue } from "@/components/MoneyValue";
import { formatDate, formatMileage, formatMoneyDelta } from "@/lib/format";
import { SELLER_TYPE_LABELS, describeSimilarityEntry } from "@/lib/labels";

/**
 * The comparable vehicles behind the valuation — the evidence, not decoration.
 *
 * Desktop gets a dense structured table because comparing rows is the whole
 * point; mobile gets cards carrying the same figures in the same order. Either
 * way every comparable opens to show why it was selected, and nothing is
 * summarised away.
 */

type SortKey = "similarity" | "price" | "mileage" | "year";

const SORTS: Record<SortKey, { label: string; compare: (a: Comparable, b: Comparable) => number }> =
  {
    similarity: {
      label: "Meeste overeenkomst",
      compare: (a, b) => b.similarity - a.similarity,
    },
    price: {
      label: "Laagste vraagprijs",
      compare: (a, b) => a.askingPriceCents - b.askingPriceCents,
    },
    mileage: {
      label: "Laagste kilometerstand",
      compare: (a, b) => (a.vehicle.mileageKm ?? Infinity) - (b.vehicle.mileageKm ?? Infinity),
    },
    year: {
      label: "Nieuwste bouwjaar",
      compare: (a, b) => (b.vehicle.year ?? 0) - (a.vehicle.year ?? 0),
    },
  };

function buildOptionLabels(target: Vehicle, comparables: Comparable[]): Map<string, string> {
  const labels = new Map<string, string>();
  for (const option of target.options) labels.set(option.key, option.labelNl);
  for (const comparable of comparables) {
    for (const option of comparable.vehicle.options) labels.set(option.key, option.labelNl);
  }
  return labels;
}

// Comparables below this score never reach the result, so drawing bars from 0%
// wastes the whole scale and makes 88% and 71% look identical. The bar is drawn
// across the range that actually occurs; the percentage next to it stays the
// exact figure.
const METER_FLOOR = 0.6;

function SimilarityMeter({ value }: { value: number }) {
  const percentage = Math.round(value * 100);
  const fill = Math.min(100, Math.max(6, ((value - METER_FLOOR) / (1 - METER_FLOOR)) * 100));
  return (
    <span className="flex items-center gap-2">
      <span className="w-10 text-sm font-semibold tabular-nums">{percentage}%</span>
      <span aria-hidden="true" className="h-1.5 w-12 overflow-hidden rounded-full bg-market-track">
        <span className="block h-full rounded-full bg-brand" style={{ width: `${fill}%` }} />
      </span>
    </span>
  );
}

function DifferenceLists({
  comparable,
  optionLabels,
}: {
  comparable: Comparable;
  optionLabels: Map<string, string>;
}) {
  return (
    <div className="grid gap-6 sm:grid-cols-2">
      <div>
        <h4 className="text-xs font-medium tracking-wide text-muted uppercase">Overeenkomsten</h4>
        <ul className="mt-2 space-y-1 text-sm">
          {comparable.reasons.map((entry, index) => (
            <li key={`${entry.code}-${index}`} className="text-ink">
              {describeSimilarityEntry(entry, optionLabels)}
            </li>
          ))}
          {comparable.reasons.length === 0 ? (
            <li className="text-muted">Geen expliciete overeenkomsten vastgesteld.</li>
          ) : null}
        </ul>
      </div>
      <div>
        <h4 className="text-xs font-medium tracking-wide text-muted uppercase">Verschillen</h4>
        <ul className="mt-2 space-y-1 text-sm">
          {comparable.differences.map((entry, index) => (
            <li key={`${entry.code}-${index}`} className="text-ink">
              {describeSimilarityEntry(entry, optionLabels)}
            </li>
          ))}
          {comparable.differences.length === 0 ? (
            <li className="text-muted">Geen relevante verschillen vastgesteld.</li>
          ) : null}
        </ul>
      </div>
    </div>
  );
}

export function ComparableEvidence({
  target,
  comparables,
}: {
  target: Vehicle;
  comparables: Comparable[];
}) {
  const [sort, setSort] = useState<SortKey>("similarity");
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  const optionLabels = useMemo(
    () => buildOptionLabels(target, comparables),
    [target, comparables],
  );
  const sorted = useMemo(
    () => [...comparables].sort(SORTS[sort].compare),
    [comparables, sort],
  );

  function toggle(listingId: number) {
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(listingId)) next.delete(listingId);
      else next.add(listingId);
      return next;
    });
  }

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted">
          {comparables.length} advertenties gebruikt als bewijs voor deze waardering.
        </p>
        <label className="flex items-center gap-2 text-sm">
          <span className="text-muted">Sorteer</span>
          <select
            value={sort}
            onChange={(event) => setSort(event.target.value as SortKey)}
            className="h-9 rounded-eaw-sm border border-line-strong bg-surface px-2 text-sm text-ink"
          >
            {Object.entries(SORTS).map(([key, { label }]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        </label>
      </div>

      {/* Desktop: a real comparison table. */}
      <div className="mt-4 hidden overflow-x-auto lg:block">
        <table className="w-full border-collapse text-sm">
          <caption className="sr-only">
            Vergelijkbare auto&apos;s met overeenkomst, kilometerstand, bouwjaar, uitvoering en
            vraagprijs
          </caption>
          <thead>
            <tr className="border-b border-line text-left text-xs tracking-wide text-muted uppercase">
              <th scope="col" className="py-2 pr-4 font-medium">
                Overeenkomst
              </th>
              <th scope="col" className="py-2 pr-4 font-medium">
                Auto
              </th>
              <th scope="col" className="py-2 pr-4 font-medium">
                Bouwjaar
              </th>
              <th scope="col" className="py-2 pr-4 text-right font-medium">
                Km-stand
              </th>
              <th scope="col" className="py-2 pr-4 font-medium">
                Uitvoering
              </th>
              <th scope="col" className="py-2 pr-4 text-right font-medium">
                Vraagprijs
              </th>
              <th scope="col" className="py-2 pr-4 text-right font-medium">
                Verschil
              </th>
              <th scope="col" className="py-2 pr-4 font-medium">
                Verkoper
              </th>
              <th scope="col" className="py-2 font-medium">
                <span className="sr-only">Details</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((comparable) => {
              const isOpen = expanded.has(comparable.listingId);
              return (
                <Fragment key={comparable.listingId}>
                  <tr className="border-b border-line align-middle hover:bg-surface-muted/60">
                    <td className="py-3 pr-4">
                      <SimilarityMeter value={comparable.similarity} />
                    </td>
                    <td className="py-3 pr-4">
                      <span className="text-ink">
                        {comparable.vehicle.make} {comparable.vehicle.model}
                      </span>
                      {comparable.vehicle.engineDescription ? (
                        <span className="text-muted"> {comparable.vehicle.engineDescription}</span>
                      ) : null}
                    </td>
                    <td className="py-3 pr-4 tabular-nums">{comparable.vehicle.year ?? "—"}</td>
                    <td className="py-3 pr-4 text-right tabular-nums">
                      {formatMileage(comparable.vehicle.mileageKm)}
                    </td>
                    <td className="py-3 pr-4 text-muted">{comparable.vehicle.trim ?? "—"}</td>
                    <td className="py-3 pr-4 text-right">
                      <MoneyValue cents={comparable.askingPriceCents} size="sm" />
                    </td>
                    <td
                      className={`py-3 pr-4 text-right tabular-nums ${
                        (comparable.priceDifferenceCents ?? 0) > 0 ? "text-caution" : "text-muted"
                      }`}
                    >
                      {comparable.priceDifferenceCents === null
                        ? "—"
                        : formatMoneyDelta(comparable.priceDifferenceCents)}
                    </td>
                    <td className="py-3 pr-4 text-muted">
                      {comparable.sellerType
                        ? SELLER_TYPE_LABELS[comparable.sellerType]
                        : "Onbekend"}
                      <span className="block text-xs text-subtle">
                        gezien {formatDate(comparable.observedAt)}
                      </span>
                    </td>
                    <td className="py-3 text-right">
                      <button
                        type="button"
                        onClick={() => toggle(comparable.listingId)}
                        aria-expanded={isOpen}
                        className="inline-flex min-h-9 items-center gap-1 rounded-eaw-sm px-2 py-2 text-sm font-medium text-brand hover:bg-brand-soft"
                      >
                        {isOpen ? "Sluit" : "Waarom?"}
                        <ChevronDown
                          aria-hidden="true"
                          className={`size-4 transition-transform ${isOpen ? "rotate-180" : ""}`}
                        />
                      </button>
                    </td>
                  </tr>
                  {isOpen ? (
                    <tr className="border-b border-line">
                      <td colSpan={9} className="bg-surface-muted/50 px-1 py-4">
                        <DifferenceLists comparable={comparable} optionLabels={optionLabels} />
                      </td>
                    </tr>
                  ) : null}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Mobile and tablet: the same evidence as cards. */}
      <ul className="mt-4 space-y-3 lg:hidden">
        {sorted.map((comparable) => {
          const isOpen = expanded.has(comparable.listingId);
          return (
            <li
              key={comparable.listingId}
              className="rounded-eaw border border-line bg-surface p-4"
            >
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="font-medium text-ink">
                    {comparable.vehicle.make} {comparable.vehicle.model}{" "}
                    {comparable.vehicle.engineDescription}
                  </p>
                  <p className="mt-1 text-sm text-muted">
                    {[
                      comparable.vehicle.year,
                      formatMileage(comparable.vehicle.mileageKm),
                      comparable.vehicle.trim,
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </p>
                </div>
                <div className="text-right">
                  <MoneyValue cents={comparable.askingPriceCents} size="base" />
                  {comparable.priceDifferenceCents !== null ? (
                    <p
                      className={`text-xs tabular-nums ${
                        comparable.priceDifferenceCents > 0 ? "text-caution" : "text-muted"
                      }`}
                    >
                      <span className="whitespace-nowrap">
                        {formatMoneyDelta(comparable.priceDifferenceCents)}
                      </span>{" "}
                      t.o.v. waarde
                    </p>
                  ) : null}
                </div>
              </div>

              <div className="mt-3 flex items-center justify-between gap-4">
                <SimilarityMeter value={comparable.similarity} />
                <span className="text-xs text-subtle">
                  {comparable.sellerType ? SELLER_TYPE_LABELS[comparable.sellerType] : "Onbekend"}{" "}
                  · {formatDate(comparable.observedAt)}
                </span>
              </div>

              <button
                type="button"
                onClick={() => toggle(comparable.listingId)}
                aria-expanded={isOpen}
                className="-mx-2 mt-2 inline-flex min-h-11 items-center gap-1 rounded-eaw-sm px-2 text-sm font-medium text-brand active:bg-brand-soft"
              >
                {isOpen ? "Verberg vergelijking" : "Waarom vergelijkbaar?"}
                <ChevronDown
                  aria-hidden="true"
                  className={`size-4 transition-transform ${isOpen ? "rotate-180" : ""}`}
                />
              </button>

              {isOpen ? (
                <div className="mt-3 border-t border-line pt-3">
                  <DifferenceLists comparable={comparable} optionLabels={optionLabels} />
                </div>
              ) : null}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
