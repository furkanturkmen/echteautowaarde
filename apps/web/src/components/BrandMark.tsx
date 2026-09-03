/**
 * Echte Auto Waarde brand mark — "Marktpositie" (Concept A).
 *
 * Three shapes and nothing else: a market line, the value block at 32% and the
 * median dot at 68%. It draws the promise the product makes — one value read
 * against the market — and stays legible at 16 px.
 *
 * The mark is always a filled rounded square: navy on a light surface, white on
 * navy, with the shapes knocked out of it. Proportions follow the brand
 * construction sheet (radius 22%, line inset 18%, block 16 x 37%, dot 13%).
 *
 * Per the brand guidance the yellow median dot is dropped below 24 px and the
 * value block widens, leaving two shapes and maximum negative space. No
 * gradients, shadows or gloss; no car, speedometer, check or shield.
 */

type Tone = "light" | "dark" | "mono";

interface ToneColors {
  container: string;
  shapes: string;
  dot: string;
}

const TONES: Record<Tone, ToneColors> = {
  // Primary: on a light surface the container carries the navy.
  light: { container: "var(--eaw-brand)", shapes: "#ffffff", dot: "var(--eaw-plate)" },
  // On navy the mark inverts, and the dot keeps the accent.
  dark: { container: "#ffffff", shapes: "var(--eaw-brand)", dot: "var(--eaw-plate)" },
  // One colour, for print and anywhere the accent cannot be reproduced.
  mono: { container: "currentColor", shapes: "#ffffff", dot: "#ffffff" },
};

// Below this size the dot is dropped rather than rendered as an unreadable speck.
const DOT_MIN_SIZE = 24;

export function BrandMark({
  size = 32,
  tone = "light",
  className = "",
  title = "Echte Auto Waarde",
}: {
  size?: number;
  tone?: Tone;
  className?: string;
  title?: string;
}) {
  const colors = TONES[tone];
  const showDot = size >= DOT_MIN_SIZE;
  // Without the dot the block widens, so two shapes still read as a position.
  const blockWidth = showDot ? 5.1 : 6.8;

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      role="img"
      aria-label={title}
      className={className}
    >
      <rect width="32" height="32" rx="7.2" fill={colors.container} />
      {/* The market: a quiet line the value is read against. */}
      <rect
        x="5.76"
        y="15.35"
        width="20.48"
        height="1.3"
        rx="0.65"
        fill={colors.shapes}
        opacity="0.34"
      />
      {/* This car's value, at 32% of the line. */}
      <rect
        x={32 * 0.32 - blockWidth / 2}
        y="10.1"
        width={blockWidth}
        height="11.8"
        rx="1.7"
        fill={colors.shapes}
      />
      {/* The market median, at 68%. */}
      {showDot ? <circle cx={32 * 0.68} cy="16" r="2.1" fill={colors.dot} /> : null}
    </svg>
  );
}

/**
 * Mark plus wordmark. The name is always written out — "EAW" exists only as an
 * icon, never as the written brand name.
 */
export function BrandLockup({
  tone = "light",
  withPayoff = false,
}: {
  tone?: Tone;
  withPayoff?: boolean;
}) {
  const nameColor = tone === "dark" ? "text-inverted" : "text-brand";

  return (
    <span className="flex items-center gap-2.5">
      <BrandMark size={30} tone={tone} />
      <span className="flex flex-col leading-none">
        <span className={`text-[1.0625rem] font-semibold tracking-[-0.01em] ${nameColor}`}>
          Echte Auto Waarde
        </span>
        {withPayoff ? (
          <span className="mt-1.5 text-xs text-muted">
            Vergelijk de markt. Ken de waarde.
          </span>
        ) : null}
      </span>
    </span>
  );
}
