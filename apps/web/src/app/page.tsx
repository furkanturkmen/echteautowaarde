/**
 * Placeholder homepage.
 *
 * The real consumer interface is built in the frontend phase. This page exists
 * only so the project never ships the Next.js starter template.
 */
export default function Home() {
  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col justify-center gap-4 px-6 py-24">
      <p className="text-sm font-medium tracking-wide text-[var(--color-text-muted)] uppercase">
        Echte Auto Waarde
      </p>
      <h1 className="text-4xl font-semibold text-balance text-[var(--color-brand)]">
        Ontdek wat je écht zou moeten betalen.
      </h1>
      <p className="text-[var(--color-text-muted)]">
        Controleer de waarde van een auto en vergelijk hem met soortgelijke occasions.
      </p>
      <p className="mt-8 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-4 text-sm text-[var(--color-text-muted)]">
        Deze lokale MVP is in ontwikkeling. De marktdata is volledig fictief en niet
        geschikt voor echte aankoopbeslissingen.
      </p>
    </main>
  );
}
