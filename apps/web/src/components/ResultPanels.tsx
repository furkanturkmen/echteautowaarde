import { Info, TriangleAlert } from "lucide-react";

import { ButtonLink } from "@/components/Button";
import { VehicleSummary } from "@/components/VehicleSummary";
import type { ApiError, Valuation } from "@/lib/api";

/**
 * The two outcomes that are not a valuation: too little evidence, or a request
 * that failed. Both are shown where the user was working, so they can correct
 * the input immediately.
 */

export function InsufficientPanel({ valuation }: { valuation: Valuation }) {
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
      <p className="mt-4 text-sm text-muted">
        Probeer een ander model uit de demomarkt, of vul meer kenmerken in zodat er meer
        vergelijkbare auto&apos;s gevonden kunnen worden.
      </p>
    </div>
  );
}

export function ErrorPanel({ error, showManualLink = true }: { error: ApiError; showManualLink?: boolean }) {
  const unknownPlate = error.status === 404;

  return (
    <div role="alert" className="rounded-eaw-lg border border-line bg-surface p-6 sm:p-8">
      <TriangleAlert aria-hidden="true" className="size-6 text-caution" />
      <h2 className="mt-4 text-lg font-semibold text-ink">
        {unknownPlate
          ? "Dit kenteken staat niet in de lokale dataset"
          : error.isOffline
            ? "Geen verbinding met de lokale API"
            : "De waardering is niet gelukt"}
      </h2>
      <p className="mt-3 text-muted">{error.message}</p>

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
