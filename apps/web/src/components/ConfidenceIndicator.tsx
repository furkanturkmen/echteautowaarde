"use client";

import { Minus, Plus } from "lucide-react";
import { useState } from "react";

import type { ConfidenceFactor } from "@/lib/api";
import { formatPercentage } from "@/lib/format";
import { CONFIDENCE_FACTOR_LABELS, describeConfidenceFactor } from "@/lib/labels";

/**
 * Confidence as a data-quality reading.
 *
 * Deliberately quieter than the valuation itself, and always inspectable: the
 * factors come from the deterministic backend model, so a user can see exactly
 * what makes this estimate strong or weak.
 */
export function ConfidenceIndicator({
  score,
  factors,
}: {
  score: number;
  factors: ConfidenceFactor[];
}) {
  const [open, setOpen] = useState(false);
  const percentage = Math.round(score * 100);
  const weakest = [...factors].sort((a, b) => a.score - b.score)[0];

  return (
    <div>
      <div className="flex items-baseline justify-between gap-4">
        <span className="text-xs font-medium tracking-wide text-muted uppercase">
          Betrouwbaarheid
        </span>
        <span className="text-lg font-semibold tabular-nums">{percentage}%</span>
      </div>

      <div
        className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-surface-muted"
        role="meter"
        aria-valuenow={percentage}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Betrouwbaarheid van de waardering"
      >
        <div
          className="h-full rounded-full bg-brand transition-[width] duration-500"
          style={{ width: `${percentage}%` }}
        />
      </div>

      <p className="mt-2 text-sm text-muted">
        {score >= 0.75
          ? "Sterk onderbouwd door de gevonden advertenties."
          : score >= 0.55
            ? "Redelijk onderbouwd; bekijk de aandachtspunten."
            : "Zwak onderbouwd — behandel deze schatting met voorbehoud."}
        {weakest ? (
          <>
            {" "}
            Grootste beperking:{" "}
            {(CONFIDENCE_FACTOR_LABELS[weakest.code] ?? weakest.code).toLowerCase()}.
          </>
        ) : null}
      </p>

      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        aria-expanded={open}
        className="mt-3 text-sm font-medium text-brand hover:underline"
      >
        {open ? "Verberg onderbouwing" : "Waarom deze betrouwbaarheid?"}
      </button>

      {open ? (
        <ul className="mt-3 space-y-2 border-t border-line pt-3">
          {factors.map((factor) => {
            const detail = describeConfidenceFactor(factor.code, factor.detail);
            const positive = factor.impact === "POSITIVE";
            const Icon = positive ? Plus : Minus;
            return (
              <li key={factor.code} className="flex gap-3 text-sm">
                <Icon
                  aria-hidden="true"
                  strokeWidth={2.5}
                  className={`mt-0.5 size-4 shrink-0 ${
                    positive ? "text-positive" : "text-caution"
                  }`}
                />
                <span>
                  <span className="text-ink">
                    {CONFIDENCE_FACTOR_LABELS[factor.code] ?? factor.code}
                  </span>
                  <span className="sr-only">
                    {positive ? " — positieve factor" : " — negatieve factor"}
                  </span>
                  {detail ? <span className="text-muted"> — {detail}</span> : null}
                  <span className="ml-1 text-subtle tabular-nums">
                    ({formatPercentage(factor.score)}
                    {factor.weight > 0 ? `, weging ${formatPercentage(factor.weight)}` : ""})
                  </span>
                </span>
              </li>
            );
          })}
        </ul>
      ) : null}
    </div>
  );
}
