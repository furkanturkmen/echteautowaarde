import { Info, TriangleAlert } from "lucide-react";

import { ButtonLink } from "@/components/Button";
import { VehicleSummary } from "@/components/VehicleSummary";
import type { ApiError, Valuation } from "@/lib/api";

/**
 * The two outcomes that are not a valuation: too little evidence, or a request
 * that failed. Both are shown where the user was working, so they can correct
 * the input immediately.
 */

/**
 * What the backend calls a characteristic, in the words the form uses. A field
 * the entered vehicle leaves blank caps how similar any advertisement can be,
 * so naming the heaviest few turns the shortage into something to correct.
 */
const FIELD_LABELS: Record<string, string> = {
  fuel_type: "brandstof",
  mileage: "kilometerstand",
  year: "bouwjaar",
  engine: "motor",
  generation: "generatie",
  body_type: "carrosserie",
  transmission: "transmissie",
  trim: "uitvoering",
  power: "vermogen",
  drivetrain: "aandrijving",
  options: "opties",
};

const MAX_NAMED_FIELDS = 4;

/** "brandstof, transmissie en motor" — Dutch uses no comma before "en". */
function formatList(labels: string[]): string {
  if (labels.length <= 1) return labels.join("");
  return `${labels.slice(0, -1).join(", ")} en ${labels[labels.length - 1]}`;
}

function namedFields(fields: string[]): string[] {
  return fields
    .map((field) => FIELD_LABELS[field])
    .filter((label): label is string => Boolean(label))
    .slice(0, MAX_NAMED_FIELDS);
}

export function InsufficientPanel({ valuation }: { valuation: Valuation }) {
  const missing = namedFields(valuation.unstatedTargetFields ?? []);

  return (
    <div className="rounded-eaw-lg border border-line bg-surface p-6 sm:p-8">
      <Info aria-hidden="true" className="size-6 text-brand" />
      <h2 className="mt-4 text-xl font-semibold text-balance text-ink">
        We hebben te weinig vergelijkbare auto&apos;s om met voldoende zekerheid een waarde te
        bepalen.
      </h2>

      <div className="mt-4">
        <VehicleSummary vehicle={valuation.vehicle} size="sm" />
      </div>

      <p className="mt-4 text-muted">
        Er {valuation.comparableCount === 1 ? "is" : "zijn"} {valuation.comparableCount}{" "}
        vergelijkbare {valuation.comparableCount === 1 ? "advertentie" : "advertenties"}{" "}
        gevonden. We geven bewust geen schatting in plaats van een cijfer dat de markt niet
        draagt.
      </p>
      {missing.length > 0 ? (
        <p className="mt-4 text-sm text-muted">
          Deze auto is nog beperkt omschreven. Vul {formatList(missing)} in — hoe meer kenmerken
          bekend zijn, hoe beter we vergelijkbare auto&apos;s kunnen herkennen.
        </p>
      ) : (
        <p className="mt-4 text-sm text-muted">
          Probeer een ander model uit de demomarkt, of vul meer kenmerken in zodat er meer
          vergelijkbare auto&apos;s gevonden kunnen worden.
        </p>
      )}
    </div>
  );
}

export function ErrorPanel({
  error,
  showManualLink = true,
  /**
   * What was being looked up. A 404 means "unknown plate" on the search form
   * but "this valuation does not exist" on a result URL, and telling someone
   * their plate is unknown when they opened a stale link is simply wrong.
   */
  context = "lookup",
}: {
  error: ApiError;
  showManualLink?: boolean;
  context?: "lookup" | "valuation";
}) {
  const notFound = error.status === 404;
  const unknownPlate = notFound && context === "lookup";

  return (
    <div role="alert" className="rounded-eaw-lg border border-line bg-surface p-6 sm:p-8">
      <TriangleAlert aria-hidden="true" className="size-6 text-caution" />
      <h2 className="mt-4 text-lg font-semibold text-ink">
        {unknownPlate
          ? "Dit kenteken staat niet in de lokale dataset"
          : notFound
            ? "Deze waardering bestaat niet (meer)"
            : error.isOffline
              ? "Geen verbinding met de lokale API"
              : "De waardering is niet gelukt"}
      </h2>
      <p className="mt-3 text-muted">
        {unknownPlate
          ? "We kennen dit kenteken niet in de lokale gegevens."
          : notFound
            ? "De link verwijst naar een waardering die niet in de lokale database staat. Waardeer de auto opnieuw om een nieuw resultaat te krijgen."
            : error.message}
      </p>

      {notFound && !unknownPlate ? (
        <div className="mt-6">
          <ButtonLink href="/">Auto waarderen</ButtonLink>
        </div>
      ) : null}

      {unknownPlate && showManualLink ? (
        <>
          <p className="mt-3 text-sm text-muted">
            De demomarkt bevat alleen verzonnen auto&apos;s. Voer de auto handmatig in om toch
            een waardering te krijgen.
          </p>
          <div className="mt-5">
            <ButtonLink href="/handmatig" variant="secondary">
              Auto handmatig invoeren
            </ButtonLink>
          </div>
        </>
      ) : null}
    </div>
  );
}
