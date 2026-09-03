"use client";

import { useId } from "react";

import { normalizePlate } from "@/lib/format";

/**
 * Dutch license plate input.
 *
 * Recognisably a Dutch plate — yellow field, dark characters, the blue EU strip
 * — but it stays a real text input: proper label, keyboard entry, autocomplete
 * off, and no character masking that would fight the caret. Realism never wins
 * over usability here.
 *
 * Width is capped so it keeps a plate's proportions on a wide screen instead of
 * stretching into a yellow banner.
 */
export function LicensePlateInput({
  value,
  onChange,
  id,
  describedBy,
  invalid = false,
  autoFocus = false,
}: {
  value: string;
  onChange: (value: string) => void;
  id?: string;
  describedBy?: string;
  invalid?: boolean;
  autoFocus?: boolean;
}) {
  const generatedId = useId();
  const inputId = id ?? generatedId;

  return (
    <div
      className={`flex h-16 w-full max-w-[22rem] items-stretch overflow-hidden rounded-eaw border-2 bg-plate sm:h-[4.5rem] ${
        invalid ? "border-negative" : "border-plate-ink/25"
      }`}
    >
      <div
        aria-hidden="true"
        className="flex w-9 flex-col items-center justify-center bg-plate-eu text-[0.6rem] font-semibold text-white sm:w-11"
      >
        <span className="leading-none tracking-widest">★★</span>
        <span className="mt-1 leading-none">NL</span>
      </div>
      <input
        id={inputId}
        name="kenteken"
        value={value}
        onChange={(event) => onChange(normalizePlate(event.target.value).slice(0, 8))}
        placeholder="XX-123-X"
        aria-describedby={describedBy}
        aria-invalid={invalid || undefined}
        autoComplete="off"
        autoCorrect="off"
        spellCheck={false}
        autoFocus={autoFocus}
        inputMode="text"
        className="w-full bg-transparent px-4 text-center font-[family-name:var(--font-plate)] text-[1.75rem] font-bold tracking-[0.12em] text-plate-ink uppercase placeholder:font-semibold placeholder:text-plate-ink/35 focus:outline-none sm:text-[2rem]"
      />
    </div>
  );
}
