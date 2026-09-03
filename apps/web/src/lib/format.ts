/**
 * Dutch formatting helpers.
 *
 * Money is stored in cents by the backend and only ever becomes a string here,
 * so rounding happens in exactly one place.
 */

const euro = new Intl.NumberFormat("nl-NL", {
  style: "currency",
  currency: "EUR",
  maximumFractionDigits: 0,
});

const euroSigned = new Intl.NumberFormat("nl-NL", {
  style: "currency",
  currency: "EUR",
  maximumFractionDigits: 0,
  signDisplay: "exceptZero",
});

const decimal = new Intl.NumberFormat("nl-NL");
const dateFormat = new Intl.DateTimeFormat("nl-NL", {
  day: "numeric",
  month: "short",
  year: "numeric",
});

export function formatMoney(cents: number | null | undefined): string {
  if (cents === null || cents === undefined) return "—";
  return euro.format(Math.round(cents / 100));
}

export function formatMoneyDelta(cents: number | null | undefined): string {
  if (cents === null || cents === undefined) return "—";
  return euroSigned.format(Math.round(cents / 100));
}

export function formatMileage(km: number | null | undefined): string {
  if (km === null || km === undefined) return "—";
  return `${decimal.format(km)} km`;
}

export function formatPercentage(fraction: number | null | undefined): string {
  if (fraction === null || fraction === undefined) return "—";
  return `${Math.round(fraction * 100)}%`;
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? "—" : dateFormat.format(parsed);
}

export function formatYear(year: number | null | undefined): string {
  return year ? String(year) : "—";
}

/** Strip a plate to storage form: uppercase, no separators. */
export function normalizePlate(value: string): string {
  return value.toUpperCase().replace(/[^A-Z0-9]/g, "");
}

/**
 * Group a plate the way Dutch plates are written.
 *
 * Only the sidecodes this dataset uses are grouped explicitly; anything else is
 * shown as typed rather than forced into a pattern that may not exist.
 */
export function formatPlate(value: string): string {
  const plate = normalizePlate(value);
  if (plate.length !== 6) return plate;

  const patterns: RegExp[] = [
    /^([A-Z]{2})(\d{3})([A-Z])$/, // BB-100-B
    /^([A-Z])(\d{3})([A-Z]{2})$/, // B-100-BB
    /^(\d{2})([A-Z]{3})(\d)$/, // 12-ABC-3
    /^([A-Z]{2})(\d{2})(\d{2})$/, // AB-12-34
    /^(\d{2})(\d{2})([A-Z]{2})$/, // 12-34-AB
    /^([A-Z]{3})(\d{2})([A-Z])$/, // ABC-12-D
  ];

  for (const pattern of patterns) {
    const match = plate.match(pattern);
    if (match) return `${match[1]}-${match[2]}-${match[3]}`;
  }
  return plate;
}

/** Parse a user-typed amount in euro into cents, or null when unusable. */
export function parseEuroInput(value: string): number | null {
  const cleaned = value.replace(/[^\d,.-]/g, "").replace(/\./g, "").replace(",", ".");
  if (!cleaned) return null;
  const amount = Number.parseFloat(cleaned);
  if (!Number.isFinite(amount) || amount < 0) return null;
  return Math.round(amount * 100);
}
