import { ArrowLeft } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";

import { ManualVehicleForm } from "@/components/ManualVehicleForm";

export const metadata: Metadata = {
  title: "Auto handmatig invoeren",
  description:
    "Voer merk, model, uitvoering, kilometerstand en opties in om de marktwaarde van een " +
    "auto te bepalen zonder kenteken.",
};

export default function ManualEntryPage() {
  return (
    <div className="mx-auto max-w-3xl px-5 py-10 sm:px-8 sm:py-14">
      <Link
        href="/"
        className="inline-flex items-center gap-2 text-sm font-medium text-muted transition-colors hover:text-ink"
      >
        <ArrowLeft aria-hidden="true" className="size-4" />
        Terug naar start
      </Link>

      <h1 className="mt-8 text-3xl font-semibold tracking-tight text-ink">
        Auto handmatig invoeren
      </h1>
      <p className="mt-3 max-w-xl text-muted">
        Hoe vollediger de gegevens, hoe beter de vergelijking. Onbekende velden mag je
        overslaan; dat verlaagt wel de betrouwbaarheid van de waardering.
      </p>

      <div className="mt-8 rounded-eaw-lg border border-line bg-surface p-6 shadow-eaw sm:p-8">
        <ManualVehicleForm />
      </div>
    </div>
  );
}
