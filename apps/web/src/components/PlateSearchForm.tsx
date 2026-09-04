"use client";

import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useId, useState } from "react";

import { Button } from "@/components/Button";
import { LicensePlateInput } from "@/components/LicensePlateInput";
import { ErrorPanel, InsufficientPanel } from "@/components/ResultPanels";
import {
  ApiError,
  type ExampleVehicle,
  type Valuation,
  createValuation,
  fetchExamples,
  lookupPlate,
} from "@/lib/api";
import { formatMoney, formatPlate, normalizePlate, parseEuroInput } from "@/lib/format";
import { storePrefill } from "@/lib/prefill";

/**
 * The entry point: kenteken, optional vraagprijs, one primary action.
 *
 * The valuation is requested here and stored once by the backend; the result
 * screen is then opened by its id, so refreshing that screen never creates a
 * second valuation. Outcomes that have no result page — thin evidence, an
 * unknown plate, an unreachable API — stay on this form, where the input can be
 * corrected straight away.
 *
 * The example vehicles are real rows from the local dataset, fetched after
 * mount so a backend that is not running never blocks the page from rendering.
 */

// Dutch license plates are always six characters once separators are removed.
const PLATE_LENGTH = 6;

export function PlateSearchForm() {
  const router = useRouter();
  const plateId = useId();
  const priceId = useId();
  const hintId = useId();

  const [plate, setPlate] = useState("");
  const [price, setPrice] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [apiError, setApiError] = useState<ApiError | null>(null);
  const [insufficient, setInsufficient] = useState<Valuation | null>(null);
  const [examples, setExamples] = useState<ExampleVehicle[]>([]);
  // Set when one of the example cars was chosen. The examples are demonstration
  // data with invented plates, so they are valued by id: a typed plate is a
  // claim about a real vehicle and must never be answered with a fiction.
  // Editing the plate clears this, because then it is no longer that choice.
  const [demoVehicleId, setDemoVehicleId] = useState<number | null>(null);

  useEffect(() => {
    let active = true;
    fetchExamples(5)
      .then((result) => {
        if (active) setExamples(result);
      })
      .catch(() => {
        // The form works without examples; no error belongs on the homepage.
      });
    return () => {
      active = false;
    };
  }, []);

  function reset() {
    setError(null);
    setApiError(null);
    setInsufficient(null);
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const normalized = normalizePlate(plate);

    if (normalized.length !== PLATE_LENGTH) {
      setError("Vul een volledig kenteken in, bijvoorbeeld XX-123-X.");
      return;
    }

    const askingPriceCents = price.trim() ? parseEuroInput(price) : null;
    if (price.trim() && askingPriceCents === null) {
      setError("Vul een geldige vraagprijs in, bijvoorbeeld 27.500.");
      return;
    }

    reset();
    setSubmitting(true);

    try {
      const valuation = await createValuation({
        ...(demoVehicleId !== null
          ? { vehicleId: demoVehicleId }
          : { licensePlate: normalized }),
        ...(askingPriceCents !== null ? { askingPriceCents } : {}),
      });

      if (valuation.id !== null) {
        router.push(`/waardebepaling/${valuation.id}`);
        return;
      }

      // Without enough evidence nothing is stored, so there is no result page
      // to open: the outcome belongs here, next to the input.
      setInsufficient(valuation);
      setSubmitting(false);
    } catch (caught) {
      // A plate we do not know locally is worth one more question: the open
      // vehicle register may know the car even though we have never seen it.
      if (caught instanceof ApiError && caught.status === 404) {
        const handled = await continueWithLookup(normalized, price);
        if (handled) return;
      }

      setSubmitting(false);
      setApiError(
        caught instanceof ApiError
          ? caught
          : new ApiError("Er ging iets mis bij het bepalen van de waarde.", 500),
      );
    }
  }

  /**
   * Look the plate up and, when the register knows it, continue on the manual
   * form with what it told us. Returns whether the outcome was handled here.
   *
   * A failed lookup is not an error worth showing: the unknown-plate message
   * the user already gets says exactly what to do next.
   */
  async function continueWithLookup(normalized: string, askingPrice: string): Promise<boolean> {
    try {
      const lookup = await lookupPlate(normalized);
      if (lookup.status !== "ENRICHED" || !lookup.draft) return false;

      storePrefill({
        draft: lookup.draft,
        missingFields: lookup.missingFields,
        askingPrice,
      });
      router.push("/handmatig");
      return true;
    } catch {
      return false;
    }
  }

  return (
    <div>
      <form onSubmit={submit} noValidate>
        <div className="grid gap-4 sm:grid-cols-[1fr_auto] sm:items-end">
          <div>
            <label htmlFor={plateId} className="block text-sm font-medium text-ink">
              Kenteken
            </label>
            <div className="mt-2">
              <LicensePlateInput
                id={plateId}
                value={plate}
                onChange={(value) => {
                  setPlate(value);
                  setDemoVehicleId(null);
                  reset();
                }}
                describedBy={hintId}
                invalid={Boolean(error)}
              />
            </div>
          </div>

          <div className="sm:w-52">
            <label htmlFor={priceId} className="block text-sm font-medium text-ink">
              Vraagprijs <span className="font-normal text-muted">(optioneel)</span>
            </label>
            <div className="mt-2 flex h-16 items-center rounded-eaw border border-line-strong bg-surface px-4 sm:h-[4.5rem]">
              <span className="mr-2 text-lg text-muted">€</span>
              <input
                id={priceId}
                name="vraagprijs"
                value={price}
                onChange={(event) => {
                  setPrice(event.target.value);
                  reset();
                }}
                inputMode="numeric"
                autoComplete="off"
                placeholder="27.500"
                className="w-full bg-transparent text-lg font-medium text-ink tabular-nums placeholder:font-normal placeholder:text-subtle focus:outline-none"
              />
            </div>
          </div>
        </div>

        <p id={hintId} className="mt-3 text-sm text-muted">
          Vraagprijs invullen geeft direct een prijsadvies en een beoordeling van de
          marktpositie.
        </p>

        {error ? (
          <p role="alert" className="mt-2 text-sm font-medium text-negative">
            {error}
          </p>
        ) : null}

        <div className="mt-6 flex flex-wrap items-center gap-x-6 gap-y-3">
          <Button type="submit" size="lg" disabled={submitting}>
            {submitting ? "Bezig met waarderen…" : "Bekijk echte autowaarde"}
            {submitting ? null : <ArrowRight aria-hidden="true" className="size-4" />}
          </Button>
          <Link
            href="/handmatig"
            className="text-sm font-medium text-brand underline-offset-4 hover:underline"
          >
            Auto handmatig invoeren
          </Link>
        </div>
      </form>

      {apiError ? (
        <div className="mt-6">
          <ErrorPanel error={apiError} />
        </div>
      ) : null}

      {insufficient ? (
        <div className="mt-6">
          <InsufficientPanel valuation={insufficient} />
        </div>
      ) : null}

      {examples.length > 0 ? (
        <div className="mt-10 border-t border-line pt-6">
          <p className="text-xs font-medium tracking-wide text-subtle uppercase">
            Voorbeelden uit de lokale demomarkt
          </p>
          <ul className="mt-3 flex flex-wrap gap-2">
            {examples.map((example) => (
              <li key={example.vehicleId}>
                <button
                  type="button"
                  onClick={() => {
                    setDemoVehicleId(example.vehicleId);
                    setPlate(example.licensePlate ?? "");
                    setPrice(String(Math.round(example.askingPriceCents / 100)));
                    reset();
                  }}
                  className="rounded-eaw border border-line bg-surface px-3 py-2 text-left text-sm transition-colors hover:border-line-strong hover:bg-surface-muted"
                >
                  <span className="font-medium text-ink">
                    {example.make} {example.model} {example.engineDescription}
                  </span>
                  <span className="mt-0.5 block text-xs text-muted tabular-nums">
                    {example.licensePlate ? formatPlate(example.licensePlate) : "—"} ·{" "}
                    {example.year} · {formatMoney(example.askingPriceCents)}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
