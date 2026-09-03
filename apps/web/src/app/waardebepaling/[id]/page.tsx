import { ArrowLeft } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { ErrorPanel, InsufficientPanel } from "@/components/ResultPanels";
import { ValuationResult } from "@/components/ValuationResult";
import { ApiError, type Valuation, fetchValuation } from "@/lib/api";

export const metadata: Metadata = {
  title: "Autowaarde",
  description:
    "De geschatte marktwaarde, het prijsadvies en de vergelijkbare auto's waarop de " +
    "waardering is gebaseerd.",
};

/**
 * Stable result URL.
 *
 * The valuation was created and stored once, by the form that requested it;
 * this route only reads it back, so refreshing or sharing the link never
 * produces another valuation.
 *
 * Rendered on the server: the result is the product, and it should arrive with
 * the page rather than after a client round trip. Interactivity (expanding a
 * comparable, inspecting confidence) still lives in client components.
 */
export default async function StoredValuationPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const valuationId = Number.parseInt(id, 10);

  if (!Number.isInteger(valuationId) || valuationId <= 0) {
    notFound();
  }

  // Only the fetch is guarded: JSX built inside a try/catch would not have its
  // render errors caught anyway, so the outcome is resolved to data first.
  let outcome: { valuation: Valuation } | { error: ApiError };
  try {
    outcome = { valuation: await fetchValuation(valuationId) };
  } catch (caught) {
    outcome = {
      error:
        caught instanceof ApiError
          ? caught
          : new ApiError("Er ging iets mis bij het ophalen van de waardering.", 500),
    };
  }

  return (
    <div className="mx-auto max-w-6xl px-5 py-10 sm:px-8 sm:py-14">
      <Link
        href="/"
        className="inline-flex items-center gap-2 text-sm font-medium text-muted transition-colors hover:text-ink"
      >
        <ArrowLeft aria-hidden="true" className="size-4" />
        Andere auto bekijken
      </Link>
      <div className="mt-8">
        {"error" in outcome ? (
          <div className="max-w-xl">
            <ErrorPanel error={outcome.error} showManualLink={false} />
          </div>
        ) : outcome.valuation.sufficientData ? (
          <ValuationResult valuation={outcome.valuation} />
        ) : (
          <div className="max-w-2xl">
            <InsufficientPanel valuation={outcome.valuation} />
          </div>
        )}
      </div>
    </div>
  );
}
