import { CircleAlert, CircleCheck, CircleMinus, TriangleAlert } from "lucide-react";

import type { DealClassification } from "@/lib/api";
import { DEAL_LABELS, type DealTone } from "@/lib/labels";

/**
 * Deal classification: analysis, not a sales badge.
 *
 * The label always carries the meaning, with colour and a small icon as
 * reinforcement — never colour alone, and never the promotional styling of a
 * marketplace "topdeal" sticker.
 */

const TONE_STYLES: Record<DealTone, string> = {
  positive: "border-positive/25 bg-positive-soft text-positive",
  neutral: "border-line-strong bg-surface-muted text-ink",
  caution: "border-caution/25 bg-caution-soft text-caution",
  negative: "border-negative/25 bg-negative-soft text-negative",
};

const TONE_ICONS: Record<DealTone, typeof CircleCheck> = {
  positive: CircleCheck,
  neutral: CircleMinus,
  caution: CircleAlert,
  negative: TriangleAlert,
};

export function DealBadge({
  classification,
  size = "md",
}: {
  classification: DealClassification;
  size?: "md" | "lg";
}) {
  const { label, tone } = DEAL_LABELS[classification];
  const Icon = TONE_ICONS[tone];

  return (
    <span
      className={`inline-flex items-center gap-2 rounded-eaw border font-medium ${TONE_STYLES[tone]} ${
        size === "lg" ? "px-4 py-2 text-base" : "px-3 py-1.5 text-sm"
      }`}
    >
      <Icon aria-hidden="true" className={size === "lg" ? "size-5" : "size-4"} strokeWidth={2} />
      {label}
    </span>
  );
}
