"""Importing real market evidence from a file.

The order matters: the whole file is parsed and validated first, and only then
is anything written. A file that fails validation changes nothing at all.

The removal rule is the reason `ImportRun` exists. A listing may only be retired
by a **completed full snapshot of the same source and scope**, and retirement
means exactly one thing:

    this listing was not observed in a complete snapshot of this source and
    scope

It does not mean the car was sold, and the last asking price is not a sale
price. Nothing here sets `LIKELY_SOLD`; no sale price is ever recorded.

**Scope is immutable.** Within one data source, once a listing has a scope, that
scope is the one it keeps. A listing may adopt a scope once — when it has none,
which covers rows imported before scopes existed — and after that an import
claiming the same `external_reference` under a different scope is rejected
before anything is written. Silently moving a listing between scopes would make
full-snapshot removal unsound: a snapshot of scope B could retire a listing that
only ever belonged to scope A, or leave a listing unreachable by either.

The consequence for callers is that source and scope definitions must be stable.
If a future lawful source genuinely needs a listing to belong to several
overlapping scopes, that needs a scope-membership model — a listing may belong
to many scopes and a snapshot retires within one — which is deliberately not
built here.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from echte_auto_waarde.data_sources.csv_import import CsvContractError, CsvImportDataSource
from echte_auto_waarde.models.enums import ImportMode, ImportRunStatus, ListingStatus
from echte_auto_waarde.models.import_run import ImportRun
from echte_auto_waarde.models.listing import DataSource, Listing
from echte_auto_waarde.services.ingestion import ensure_data_source, ingest

logger = logging.getLogger(__name__)


@dataclass
class ImportReport:
    """What an import did, in terms the operator can act on."""

    run_id: int | None
    source_key: str
    scope: str
    mode: ImportMode
    status: ImportRunStatus
    rows_read: int = 0
    listings_created: int = 0
    listings_updated: int = 0
    listings_removed: int = 0
    validation_errors: list[str] = field(default_factory=list)
    dry_run: bool = False

    @property
    def succeeded(self) -> bool:
        return self.status is ImportRunStatus.COMPLETED


def import_market_file(
    session: Session,
    source: CsvImportDataSource,
    scope: str,
    mode: ImportMode = ImportMode.INCREMENTAL,
    dry_run: bool = False,
) -> ImportReport:
    """Import one file into one source and scope.

    Raises nothing for a bad file: a rejected import is a normal outcome and is
    reported, not thrown. Genuine programming errors still propagate.
    """
    report = ImportReport(
        run_id=None,
        source_key=source.key,
        scope=scope,
        mode=mode,
        status=ImportRunStatus.FAILED,
        dry_run=dry_run,
    )

    # 1. Validate everything before touching the database.
    try:
        listings = list(source.fetch_listings())
    except CsvContractError as error:
        report.validation_errors = error.problems
        logger.info(
            "Import rejected for %s/%s: %d problem(s)", source.key, scope, len(error.problems)
        )
        return report

    report.rows_read = len(listings)

    # 2. The scope invariant is checked before anything is created, including
    #    the data source itself: a rejected import must leave no trace.
    conflicts = _scope_conflicts(
        session,
        source_key=source.key,
        scope=scope,
        references=[listing.external_reference for listing in listings],
    )
    if conflicts:
        report.validation_errors = conflicts
        logger.info(
            "Import rejected for %s/%s: %d scope conflict(s)", source.key, scope, len(conflicts)
        )
        return report

    if dry_run:
        # Nothing was written, and nothing may be concluded about absences.
        report.status = ImportRunStatus.COMPLETED
        return report

    # 3. One transaction: the run, the listings and any retirement live or die
    #    together, so a failure halfway cannot leave a half-applied market.
    data_source = ensure_data_source(session, source)
    run = ImportRun(
        data_source_id=data_source.id,
        scope=scope,
        mode=mode,
        status=ImportRunStatus.STARTED,
        started_at=datetime.now(UTC),
        source_file=str(source.path),
    )
    session.add(run)
    session.flush()
    report.run_id = run.id

    try:
        result = ingest(session, source)
        _stamp_scope(
            session, data_source.id, [listing.external_reference for listing in listings], scope
        )

        removed = 0
        if mode is ImportMode.FULL_SNAPSHOT:
            removed = _retire_unseen(
                session,
                data_source_id=data_source.id,
                scope=scope,
                seen_references={listing.external_reference for listing in listings},
            )

        run.status = ImportRunStatus.COMPLETED
        run.finished_at = datetime.now(UTC)
        run.listings_seen = len(listings)
        run.listings_created = result.listings_created
        run.listings_updated = result.listings_updated
        run.listings_removed = removed
        session.flush()

        report.status = ImportRunStatus.COMPLETED
        report.listings_created = result.listings_created
        report.listings_updated = result.listings_updated
        report.listings_removed = removed
        return report
    except Exception as error:  # noqa: BLE001 - recorded, then re-raised
        # The caller rolls back, so the run row disappears with everything else.
        # Nothing is retired, which is the whole point of gating on COMPLETED.
        run.status = ImportRunStatus.FAILED
        run.finished_at = datetime.now(UTC)
        run.error_count = 1
        run.notes = str(error)[:500]
        logger.exception("Import failed for %s/%s", source.key, scope)
        raise


def _scope_conflicts(
    session: Session, source_key: str, scope: str, references: list[str]
) -> list[str]:
    """Rows that would move an existing listing into a different scope.

    Read-only by design: this runs before the data source, the run and the
    listings exist, so a conflicting file changes nothing at all.
    """
    data_source = session.scalar(select(DataSource).where(DataSource.key == source_key))
    if data_source is None or not references:
        return []

    existing = session.scalars(
        select(Listing).where(
            Listing.data_source_id == data_source.id,
            Listing.external_reference.in_(references),
            Listing.source_scope.is_not(None),
            Listing.source_scope != scope,
        )
    ).all()

    return [
        f"external_reference {listing.external_reference!r} already belongs to scope "
        f"{listing.source_scope!r} in this source and cannot be imported as {scope!r}; "
        "a listing keeps the scope it was first imported under"
        for listing in existing
    ]


def _stamp_scope(session: Session, data_source_id: int, references: list[str], scope: str) -> None:
    """Give listings that have no scope yet the scope of this import.

    Only ever fills a gap. A listing that already has a scope keeps it — the
    conflicting case was rejected before any of this ran.
    """
    if not references:
        return
    listings = session.scalars(
        select(Listing).where(
            Listing.data_source_id == data_source_id,
            Listing.external_reference.in_(references),
            Listing.source_scope.is_(None),
        )
    ).all()
    for listing in listings:
        listing.source_scope = scope
    if listings:
        session.flush()


def _retire_unseen(
    session: Session,
    data_source_id: int,
    scope: str,
    seen_references: set[str],
) -> int:
    """Mark listings absent from a completed full snapshot as REMOVED.

    Bounded to one source and one scope: a snapshot describes what it describes
    and nothing else. Removal is an observation about the listing, never a
    statement about a sale.
    """
    listings = session.scalars(
        select(Listing).where(
            Listing.data_source_id == data_source_id,
            Listing.source_scope == scope,
            Listing.status != ListingStatus.REMOVED,
        )
    ).all()

    removed = 0
    for listing in listings:
        if listing.external_reference in seen_references:
            continue
        listing.status = ListingStatus.REMOVED
        removed += 1

    if removed:
        session.flush()
    return removed
