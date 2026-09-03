"""Ingestion of raw adapter records into normalized persistence.

This is the single place where source wording becomes canonical data. Adapters
stay dumb (they only report what a source says); the domain stays clean (it only
sees canonical values); and the raw text is preserved on the way through so any
normalization decision can be traced back.

Ingestion is idempotent per (data source, external reference): running it twice
updates the existing listing and appends new observations instead of duplicating
the market.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from echte_auto_waarde.data_sources.base import DataSourceAdapter, RawListing, RawVehicle
from echte_auto_waarde.domain import normalization
from echte_auto_waarde.domain.options import OPTION_TAXONOMY, split_option_texts
from echte_auto_waarde.models.enums import ListingStatus, SellerType
from echte_auto_waarde.models.listing import DataSource, Listing, ListingSnapshot, Seller
from echte_auto_waarde.models.option import VehicleOption, VehicleOptionDefinition
from echte_auto_waarde.models.vehicle import Vehicle

logger = logging.getLogger(__name__)


@dataclass
class IngestionResult:
    listings_created: int = 0
    listings_updated: int = 0
    snapshots_created: int = 0
    unresolved_option_texts: int = 0

    @property
    def total_listings(self) -> int:
        return self.listings_created + self.listings_updated


def sync_option_definitions(session: Session) -> int:
    """Write the option taxonomy to the database, updating existing rows.

    The taxonomy in the domain layer is the source of truth; the table exists so
    listings can reference options relationally.
    """
    existing = {
        definition.key: definition
        for definition in session.scalars(select(VehicleOptionDefinition)).all()
    }

    for option in OPTION_TAXONOMY:
        row = existing.get(option.key)
        if row is None:
            session.add(
                VehicleOptionDefinition(
                    key=option.key,
                    label_nl=option.label_nl,
                    category=option.category,
                    importance=option.importance,
                )
            )
        else:
            row.label_nl = option.label_nl
            row.category = option.category
            row.importance = option.importance

    session.flush()
    return len(OPTION_TAXONOMY)


def ensure_data_source(session: Session, adapter: DataSourceAdapter) -> DataSource:
    data_source = session.scalar(select(DataSource).where(DataSource.key == adapter.key))
    if data_source is None:
        data_source = DataSource(
            key=adapter.key,
            source_type=adapter.source_type,
            name=adapter.name,
            quality=adapter.quality,
        )
        session.add(data_source)
        session.flush()
    else:
        data_source.name = adapter.name
        data_source.quality = adapter.quality
    return data_source


def ingest(session: Session, adapter: DataSourceAdapter) -> IngestionResult:
    """Ingest everything the adapter currently reports."""
    sync_option_definitions(session)
    data_source = ensure_data_source(session, adapter)
    option_definitions = {
        row.key: row for row in session.scalars(select(VehicleOptionDefinition)).all()
    }

    result = IngestionResult()
    for raw_listing in adapter.fetch_listings():
        _ingest_listing(session, data_source, raw_listing, option_definitions, result)

    session.flush()
    return result


def _ingest_listing(
    session: Session,
    data_source: DataSource,
    raw: RawListing,
    option_definitions: dict[str, VehicleOptionDefinition],
    result: IngestionResult,
) -> None:
    listing = session.scalar(
        select(Listing).where(
            Listing.data_source_id == data_source.id,
            Listing.external_reference == raw.external_reference,
        )
    )

    if listing is None:
        vehicle = _build_vehicle(raw.vehicle, option_definitions, result)
        session.add(vehicle)
        session.flush()

        listing = Listing(
            vehicle_id=vehicle.id,
            seller_id=_resolve_seller(session, raw).id if raw.seller else None,
            data_source_id=data_source.id,
            external_reference=raw.external_reference,
            asking_price_cents=raw.asking_price_cents,
            url=raw.url,
            status=raw.status,
            first_seen_at=raw.first_seen_at,
            last_seen_at=raw.last_seen_at,
        )
        session.add(listing)
        session.flush()
        result.listings_created += 1
    else:
        listing.asking_price_cents = raw.asking_price_cents
        listing.status = raw.status
        listing.last_seen_at = raw.last_seen_at
        result.listings_updated += 1

    _append_snapshots(session, listing, raw, result)


def _append_snapshots(
    session: Session, listing: Listing, raw: RawListing, result: IngestionResult
) -> None:
    """Append observations that are not recorded yet.

    History is never rewritten: an existing snapshot is left exactly as it was
    observed, even if the source now reports something different.
    """
    known = {
        (_as_utc(snapshot.observed_at), snapshot.asking_price_cents)
        for snapshot in session.scalars(
            select(ListingSnapshot).where(ListingSnapshot.listing_id == listing.id)
        ).all()
    }

    if not raw.snapshots:
        # A source without explicit history still gives us one observation.
        session.add(
            ListingSnapshot(
                listing_id=listing.id,
                observed_at=raw.last_seen_at,
                asking_price_cents=raw.asking_price_cents,
                mileage_km=raw.vehicle.mileage_km,
                status=raw.status,
            )
        )
        result.snapshots_created += 1
        return

    for snapshot in raw.snapshots:
        if (_as_utc(snapshot.observed_at), snapshot.asking_price_cents) in known:
            continue
        session.add(
            ListingSnapshot(
                listing_id=listing.id,
                observed_at=snapshot.observed_at,
                asking_price_cents=snapshot.asking_price_cents,
                mileage_km=snapshot.mileage_km,
                status=snapshot.status,
            )
        )
        result.snapshots_created += 1


def _as_utc(value: datetime) -> datetime:
    """Return an aware UTC datetime.

    Timestamps are written in UTC, but SQLite stores them without a timezone, so
    values read back are naive. Comparing a naive stored value with an aware
    incoming one would silently fail every deduplication check and duplicate the
    observation history.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _resolve_seller(session: Session, raw: RawListing) -> Seller:
    """Reuse an identical seller row when one already exists.

    Only the coarse identity a listing exposes (type, name, city) is stored; no
    attempt is made to identify people behind private listings.
    """
    assert raw.seller is not None
    seller_type = _parse_seller_type(raw.seller.seller_type)

    existing = session.scalar(
        select(Seller).where(
            Seller.seller_type == seller_type,
            Seller.name == raw.seller.name,
            Seller.city == raw.seller.city,
        )
    )
    if existing is not None:
        return existing

    seller = Seller(seller_type=seller_type, name=raw.seller.name, city=raw.seller.city)
    session.add(seller)
    session.flush()
    return seller


def _parse_seller_type(value: str | None) -> SellerType:
    if not value:
        return SellerType.UNKNOWN
    try:
        return SellerType(value.strip().upper())
    except ValueError:
        return SellerType.UNKNOWN


def _build_vehicle(
    raw: RawVehicle,
    option_definitions: dict[str, VehicleOptionDefinition],
    result: IngestionResult,
) -> Vehicle:
    make = normalization.normalize_make(raw.make)
    model = normalization.normalize_model(make, raw.model)

    options, trim_labels, unresolved = split_option_texts(list(raw.option_texts))
    result.unresolved_option_texts += len(unresolved)
    if unresolved:
        logger.debug("Unresolved option texts for %s %s: %s", make, model, unresolved)

    # A package mentioned in the option list belongs on the trim field; counting
    # it as equipment as well would let one package influence value twice.
    trim = normalization.normalize_trim(raw.trim) or (trim_labels[0] if trim_labels else None)

    vehicle = Vehicle(
        license_plate=normalization.normalize_license_plate(raw.license_plate),
        make=make,
        model=model,
        generation=normalization.collapse_whitespace(raw.generation) if raw.generation else None,
        trim=trim,
        make_raw=raw.make,
        model_raw=raw.model,
        trim_raw=raw.trim,
        body_type=normalization.normalize_body_type(raw.body_type),
        fuel_type=normalization.normalize_fuel_type(raw.fuel_type),
        transmission=normalization.normalize_transmission(raw.transmission),
        drivetrain=normalization.normalize_drivetrain(raw.drivetrain),
        engine_description=normalization.normalize_engine_description(raw.engine_description),
        engine_displacement_cc=raw.engine_displacement_cc,
        power_kw=raw.power_kw,
        power_hp=raw.power_hp,
        year=raw.year,
        first_registration_date=raw.first_registration_date,
        mileage_km=raw.mileage_km,
        color=raw.color,
        doors=raw.doors,
        seats=raw.seats,
        catalog_price_cents=raw.catalog_price_cents,
        source_metadata=json.dumps({"unresolved_options": unresolved}) if unresolved else None,
    )

    for option, raw_text in options:
        definition = option_definitions.get(option.key)
        if definition is None:
            continue
        vehicle.options.append(VehicleOption(definition_id=definition.id, raw_text=raw_text))

    return vehicle


def infer_listing_status(listing: Listing) -> ListingStatus:
    """Interpret observed history into a lifecycle state.

    Deliberately conservative: a listing that simply disappeared is REMOVED, not
    sold. LIKELY_SOLD requires an explicit heuristic, which does not exist yet
    because synthetic data cannot support one.
    """
    if len(listing.snapshots) >= 2:
        first, last = listing.snapshots[0], listing.snapshots[-1]
        if last.asking_price_cents < first.asking_price_cents:
            return ListingStatus.PRICE_REDUCED
    return listing.status
