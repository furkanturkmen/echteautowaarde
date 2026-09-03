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
    <div className="mx-auto flex max-w-5xl flex-col px-5 pt-14 pb-8 sm:px-8 sm:pt-24">
      <div className="max-w-2xl">
        <h1 className="text-[2.25rem] leading-[1.08] font-semibold tracking-[-0.028em] text-balance text-ink sm:text-[3.375rem]">
          Ontdek wat je écht zou moeten betalen.
        </h1>
        <p className="mt-6 text-lg leading-[1.65] text-pretty text-muted">
          Controleer de waarde van een auto en vergelijk hem met soortgelijke occasions. Je
          ziet welke auto&apos;s zijn gebruikt, waarin ze verschillen en hoe de waardering is
          opgebouwd.
        </p>
      </div>

      <div className="mt-10 rounded-eaw-lg border border-line bg-surface p-6 shadow-eaw sm:mt-12 sm:p-8">
        <PlateSearchForm />
      </div>

    </div>
  );
}
