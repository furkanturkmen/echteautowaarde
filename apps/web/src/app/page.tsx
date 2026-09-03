import { PlateSearchForm } from "@/components/PlateSearchForm";

/**
 * Homepage.
 *
 * One job: get someone from a license plate to a valuation. No feature grid, no
 * testimonials, no invented statistics — the proposition and the input are the
 * page.
 */
export default function Home() {
  return (
    <div className="mx-auto max-w-6xl px-5 pt-16 pb-8 sm:px-8 sm:pt-24">
      <div className="max-w-2xl">
        <h1 className="text-4xl font-semibold tracking-tight text-balance text-ink sm:text-5xl">
          Ontdek wat je écht zou moeten betalen.
        </h1>
        <p className="mt-5 text-lg text-pretty text-muted">
          Controleer de waarde van een auto en vergelijk hem met soortgelijke occasions. Je
          ziet welke auto&apos;s zijn gebruikt, waarin ze verschillen en hoe de waardering is
          opgebouwd.
        </p>
      </div>

      <div className="mt-10 rounded-eaw-lg border border-line bg-surface p-6 shadow-eaw sm:p-8">
        <PlateSearchForm />
      </div>

      <p className="mt-8 max-w-2xl text-sm text-muted">
        Deze lokale versie draait op een synthetische demomarkt. De advertenties en prijzen
        zijn verzonnen om de methodiek te testen en zijn niet geschikt voor echte
        aankoopbeslissingen.
      </p>
    </div>
  );
}
