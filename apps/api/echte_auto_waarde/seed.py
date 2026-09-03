"""Seed the local database with the synthetic demo market.

Usage (from apps/api, with the virtual environment active):

    python -m echte_auto_waarde.seed            # seed, keeping existing data
    python -m echte_auto_waarde.seed --reset    # clear synthetic data first
    python -m echte_auto_waarde.seed --seed 42  # a different fictional market

The dataset is fictional and regenerated locally; nothing is downloaded.
"""

from __future__ import annotations

import argparse
import logging
import sys

from sqlalchemy import delete, inspect, select
from sqlalchemy.orm import Session

from echte_auto_waarde.data_sources.synthetic import DEFAULT_SEED, SyntheticDataSource
from echte_auto_waarde.db.session import SessionLocal, engine
from echte_auto_waarde.models.listing import DataSource, Listing, ListingSnapshot
from echte_auto_waarde.models.vehicle import Vehicle
from echte_auto_waarde.services.ingestion import ingest

logger = logging.getLogger("echte_auto_waarde.seed")


def reset_source(session: Session, source_key: str) -> int:
    """Remove every listing (and its vehicles) belonging to one data source."""
    data_source = session.scalar(select(DataSource).where(DataSource.key == source_key))
    if data_source is None:
        return 0

    listings = session.scalars(
        select(Listing).where(Listing.data_source_id == data_source.id)
    ).all()
    vehicle_ids = [listing.vehicle_id for listing in listings]
    listing_ids = [listing.id for listing in listings]

    if listing_ids:
        session.execute(delete(ListingSnapshot).where(ListingSnapshot.listing_id.in_(listing_ids)))
        session.execute(delete(Listing).where(Listing.id.in_(listing_ids)))
    if vehicle_ids:
        session.execute(delete(Vehicle).where(Vehicle.id.in_(vehicle_ids)))

    session.flush()
    return len(listing_ids)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed the synthetic demo market.")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="Generator seed.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete existing synthetic listings before seeding.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if not inspect(engine).has_table("listings"):
        logger.error("Database schema is missing. Run: alembic upgrade head")
        return 1

    adapter = SyntheticDataSource(seed=args.seed)

    with SessionLocal() as session:
        if args.reset:
            removed = reset_source(session, adapter.key)
            logger.info("Removed %d existing synthetic listings.", removed)

        result = ingest(session, adapter)
        session.commit()

    logger.info(
        "Seeded %d listings (%d new, %d updated) and %d observations.",
        result.total_listings,
        result.listings_created,
        result.listings_updated,
        result.snapshots_created,
    )
    if result.unresolved_option_texts:
        logger.info(
            "%d option texts could not be resolved to the taxonomy.",
            result.unresolved_option_texts,
        )
    logger.info("This market is synthetic and unsuitable for real purchase decisions.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
