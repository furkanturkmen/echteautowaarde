"""Import real market evidence from a local CSV file.

Usage (from apps/api, with the virtual environment active):

    python -m echte_auto_waarde.import_market --file market.csv \
        --source-key import:dealer-example --scope bmw-3-serie

    # A file that is the complete picture of that scope right now. Listings of
    # the same source and scope that are absent from it are marked REMOVED.
    python -m echte_auto_waarde.import_market --file market.csv \
        --source-key import:dealer-example --scope bmw-3-serie \
        --mode full-snapshot

    # Validate without writing anything.
    python -m echte_auto_waarde.import_market --file market.csv \
        --source-key import:dealer-example --scope bmw-3-serie --dry-run

Nothing is downloaded and no marketplace is contacted: this reads the file you
give it. You are responsible for having the right to use that data.

REMOVED means "not observed in a completed full snapshot of this source and
scope". It does not mean sold, and no sale price is ever recorded.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from echte_auto_waarde.data_sources.csv_import import CsvImportDataSource
from echte_auto_waarde.db.session import SessionLocal
from echte_auto_waarde.models.enums import ImportMode
from echte_auto_waarde.services.import_market import import_market_file

logger = logging.getLogger("echte_auto_waarde.import_market")

MAX_ERRORS_SHOWN = 20


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import market evidence from a CSV file.")
    parser.add_argument("--file", required=True, type=Path, help="CSV file to import.")
    parser.add_argument(
        "--source-key",
        required=True,
        help="Stable identity of the dataset, for example import:dealer-example.",
    )
    parser.add_argument(
        "--scope",
        required=True,
        help="What this file describes, for example bmw-3-serie. A full snapshot "
        "may only retire listings within its own scope.",
    )
    parser.add_argument("--name", help="Readable name for the dataset. Defaults to the key.")
    parser.add_argument(
        "--mode",
        choices=["incremental", "full-snapshot"],
        default="incremental",
        help="incremental (default) adds and updates. full-snapshot additionally "
        "retires listings of this source and scope that the file does not contain.",
    )
    parser.add_argument(
        "--quality",
        type=float,
        default=0.7,
        help="How much this source is trusted (0-1), used by the confidence model.",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Validate the file and write nothing."
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if not args.file.is_file():
        logger.error("File not found: %s", args.file)
        return 2
    if not 0.0 <= args.quality <= 1.0:
        logger.error("--quality must be between 0 and 1.")
        return 2

    mode = ImportMode.FULL_SNAPSHOT if args.mode == "full-snapshot" else ImportMode.INCREMENTAL
    source = CsvImportDataSource(
        path=args.file,
        key=args.source_key,
        name=args.name or args.source_key,
        quality=args.quality,
    )

    with SessionLocal() as session:
        try:
            report = import_market_file(
                session, source, scope=args.scope, mode=mode, dry_run=args.dry_run
            )
        except Exception:
            # Nothing is half-applied: the transaction is discarded entirely.
            session.rollback()
            logger.exception("The import failed and nothing was written.")
            return 1

        if not report.succeeded:
            session.rollback()
            logger.error(
                "Import rejected: %d problem(s) in %s. Nothing was written.",
                len(report.validation_errors),
                args.file,
            )
            for problem in report.validation_errors[:MAX_ERRORS_SHOWN]:
                logger.error("  %s", problem)
            if len(report.validation_errors) > MAX_ERRORS_SHOWN:
                logger.error("  ... and %d more", len(report.validation_errors) - MAX_ERRORS_SHOWN)
            return 1

        session.commit()

    logger.info("Run %s", report.run_id if report.run_id is not None else "(dry run)")
    logger.info("  source     : %s", report.source_key)
    logger.info("  scope      : %s", report.scope)
    logger.info("  mode       : %s", report.mode.value)
    logger.info("  rows read  : %d", report.rows_read)
    if report.dry_run:
        logger.info("  dry run: the file is valid and nothing was written.")
        return 0

    logger.info("  created    : %d", report.listings_created)
    logger.info("  updated    : %d", report.listings_updated)
    if report.mode is ImportMode.FULL_SNAPSHOT:
        logger.info(
            "  removed    : %d (not observed in this snapshot; not sold)", report.listings_removed
        )
    logger.info(
        "Imported asking prices are observations, never sale prices, and you are "
        "responsible for having the right to use this data."
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    sys.exit(main())
