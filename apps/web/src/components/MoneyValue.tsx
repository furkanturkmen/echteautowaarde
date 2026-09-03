import { formatMoney, formatMoneyDelta } from "@/lib/format";

/**
 * Money, at the four sizes this product needs.
 *
 * The valuation is the product, so the hierarchy between an amount and its
 * label is deliberate and consistent: the number always outweighs the words
 * around it.
 */

type MoneySize = "hero" | "lead" | "base" | "sm";

const SIZES: Record<MoneySize, string> = {
  hero: "text-5xl sm:text-6xl font-semibold tracking-tight leading-none",
  lead: "text-2xl sm:text-3xl font-semibold tracking-tight",
  base: "text-lg font-medium",
  sm: "text-sm font-medium",
};

export function MoneyValue({
  cents,
  size = "base",
  className = "",
  signed = false,
}: {
  cents: number | null | undefined;
  size?: MoneySize;
  className?: string;
  signed?: boolean;
}) {
  const text = signed ? formatMoneyDelta(cents) : formatMoney(cents);
  return <span className={`${SIZES[size]} tabular-nums ${className}`.trim()}>{text}</span>;
}

/** A label above a value, used wherever a figure needs naming. */
export function StatDisplay({
  label,
  children,
  hint,
  className = "",
}: {
  label: string;
  children: React.ReactNode;
  hint?: string;
  className?: string;
}) {
  return (
    <div className={className}>
      <dt className="text-xs font-medium tracking-wide text-muted uppercase">{label}</dt>
      <dd className="mt-1 text-ink">{children}</dd>
      {hint ? <p className="mt-1 text-xs text-subtle">{hint}</p> : null}
    </div>
  );
}
