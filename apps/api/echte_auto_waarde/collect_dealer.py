"""Collect a small sample from a dealer's own public inventory page.

Usage (from apps/api, with the virtual environment active):

    python -m echte_auto_waarde.collect_dealer --source inzoeven
    python -m echte_auto_waarde.collect_dealer --source autoxl --limit 10
    python -m echte_auto_waarde.collect_dealer --source inzoeven --dry-run

Two dealers are supported and adding a third is a deliberate act with its own
robots and terms review. Marketplaces and aggregators are not supported.

The pilot is capped at 25 listings per source per run, reads one page at a time
with a delay, obeys robots.txt, and stops rather than working around a block or
a challenge. It stores facts a valuation needs — never photographs,
descriptions, marketing copy or contact details.

Collection is always INCREMENTAL. The sample is partial by design, so a listing
that is absent from it means nothing: nothing is ever marked removed, and no
sale is ever inferred. Asking prices are observations, not sale prices.

robots.txt permitting a request is not a licence to reuse the data. Recurring or
larger collection belongs in a permission, feed or API arrangement.
"""

from __future__ import annotations

import argparse
import logging
import sys

from echte_auto_waarde.data_sources.dealers import DEALER_SOURCES
from echte_auto_waarde.data_sources.dealers.collector import (
    DEFAULT_LISTING_LIMIT,
    MAX_LISTING_LIMIT,
    DealerCollectionError,
    build_fetcher,
    clamp_limit,
)
from echte_auto_waarde.db.session import SessionLocal
from echte_auto_waarde.models.enums import ImportMode
from echte_auto_waarde.services.import_market import import_market_file

logger = logging.getLogger("echte_auto_waarde.collect_dealer")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Collect a small sample from a dealer's public inventory page."
    )
    parser.add_argument("--source", required=True, choices=sorted(DEALER_SOURCES))
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LISTING_LIMIT,
        help=f"Listings to take (default {DEFAULT_LISTING_LIMIT}, hard maximum "
        f"{MAX_LISTING_LIMIT}).",
    )
    parser.add_argument(
        "--scope",
        help="Import scope. Defaults to the source name; a scope is never used to "
        "retire listings for this kind of source.",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Collect and report, writing nothing."
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    limit = clamp_limit(args.limit)
    if args.limit != limit:
        logger.info("Limit %d is outside the pilot's range; using %d.", args.limit, limit)

    fetcher = build_fetcher()
    source = DEALER_SOURCES[args.source](limit=limit, fetcher=fetcher)
    scope = args.scope or args.source

    logger.info("Source     : %s (%s)", source.key, source.origin)
    logger.info("Limit      : %d listings, one request at a time", limit)

    try:
        decision = fetcher.check_robots(source.origin)
        logger.info("robots.txt : %s", decision.detail)
        if not decision.allowed:
            logger.error("Stopping: robots.txt disallows this path. Nothing was collected.")
            return 1

        with SessionLocal() as session:
            report = import_market_file(
                session,
                source,
                scope=scope,
                # Never FULL_SNAPSHOT: the sample is partial by design.
                mode=ImportMode.INCREMENTAL,
                dry_run=args.dry_run,
            )

            if not report.succeeded:
                session.rollback()
                logger.error("Import rejected. Nothing was written.")
                for problem in report.validation_errors[:10]:
                    logger.error("  %s", problem)
                return 1

            session.commit()
    except DealerCollectionError as error:
        # Blocked, challenged, or disallowed. There is no bypass path.
        logger.error("Stopping this source: %s", error)
        return 1

    logger.info("Requests   : %d", fetcher.requests_made)
    logger.info("Discovered : %d listing cards", source.discovered)
    logger.info("Parsed     : %d", report.rows_read)
    logger.info("Rejected   : %d", source.rejected)
    if args.dry_run:
        logger.info("Dry run: nothing was written.")
        return 0

    logger.info("Created    : %d", report.listings_created)
    logger.info("Updated    : %d", report.listings_updated)
    logger.info(
        "Observed asking prices from public dealer advertisements. Not sale prices, "
        "and nothing here is marked sold or removed."
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    sys.exit(main())
