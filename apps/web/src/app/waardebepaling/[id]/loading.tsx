/**
 * Shown while the stored valuation is fetched on the server.
 *
 * The shapes match the result layout, so the page does not jump when the real
 * figures arrive.
 */
export default function Loading() {
  return (
    <div className="mx-auto max-w-6xl px-5 py-10 sm:px-8 sm:py-14">
      <div className="h-4 w-40 animate-pulse rounded bg-surface-muted" />
      <div aria-busy="true" aria-live="polite" className="mt-8">
        <p className="sr-only">De waardering wordt geladen.</p>
        <div className="h-8 w-72 max-w-full animate-pulse rounded-eaw bg-surface-muted" />
        <div className="mt-3 h-4 w-56 max-w-full animate-pulse rounded-eaw bg-surface-muted" />
        <div className="mt-6 rounded-eaw-lg border border-line bg-surface p-6 sm:p-8">
          <div className="h-3 w-40 animate-pulse rounded bg-surface-muted" />
          <div className="mt-4 h-14 w-64 max-w-full animate-pulse rounded bg-surface-muted" />
          <div className="mt-8 h-24 animate-pulse rounded-eaw bg-surface-muted" />
        </div>
      </div>
    </div>
  );
}
