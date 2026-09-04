"""Market data imported from a local CSV file.

This is the lawful route to real asking prices: someone who is entitled to a
dataset — their own dealer inventory, a licensed extract, an export they were
given — hands it to the application as a file. Nothing here fetches anything,
and nothing here knows about any marketplace.

**Responsibility travels with the file.** The application cannot tell whether a
row may lawfully be used, and does not pretend to: whoever runs the import is
responsible for having the right to use that data.

What the file contains is *observed asking prices*. A price in a row is what
someone was asking on the observation date. It is never a sale price, and a
listing that stops appearing was not necessarily sold.

Only market-evidence fields are read. Seller names, phone numbers and email
addresses are deliberately not part of the contract: this product needs market
evidence, not a contact database.
"""

from __future__ import annotations

import csv
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from echte_auto_waarde.data_sources.base import (
    RawListing,
    RawSeller,
    RawSnapshot,
    RawVehicle,
)
from echte_auto_waarde.models.enums import DataSourceType, ListingStatus

# Bumped when the meaning of a column changes. Files declare nothing; the
# version is documentation for the person preparing one.
CSV_CONTRACT_VERSION = "1"

REQUIRED_COLUMNS = (
    "external_reference",
    "make",
    "model",
    "asking_price_eur",
    "observed_at",
)

OPTIONAL_COLUMNS = (
    "listing_url",
    "license_plate",
    "variant",
    "trim",
    "registration_year",
    "mileage_km",
    "fuel",
    "transmission",
    "body_type",
    "drivetrain",
    "power_hp",
    "seller_type",
    "seller_city",
    "options",
)

KNOWN_COLUMNS = frozenset(REQUIRED_COLUMNS + OPTIONAL_COLUMNS)

# Options arrive as one cell so the file stays a flat table.
OPTION_SEPARATOR = ";"

MIN_YEAR = 1950
MAX_YEAR = 2100
MAX_MILEAGE_KM = 2_000_000
MAX_PRICE_CENTS = 100_000_000  # €1m, generous for a used car and still a guard.


class CsvContractError(ValueError):
    """The file does not satisfy the import contract.

    Carries row-level problems so the operator can fix the file, and never a
    traceback: a bad file is a normal outcome, not a crash.
    """

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        shown = "; ".join(problems[:5])
        more = f" (and {len(problems) - 5} more)" if len(problems) > 5 else ""
        super().__init__(f"{len(problems)} problem(s) in the import file: {shown}{more}")


@dataclass
class CsvImportDataSource:
    """A `DataSourceAdapter` over one local CSV file.

    `key` identifies the dataset, not the application: an imported market is
    never presented as something Echte Auto Waarde produced. Use something the
    operator recognises, such as `import:dealer-example`.
    """

    path: Path
    key: str
    name: str
    quality: float = 0.7
    source_type: DataSourceType = DataSourceType.CSV_IMPORT

    def fetch_listings(self) -> Iterable[RawListing]:
        """Every listing in the file, or nothing at all.

        The whole file is parsed and validated before a single record is
        yielded, so a malformed row cannot leave half an import applied.
        """
        return list(self._parse())

    # -- Parsing --------------------------------------------------------------

    def _parse(self) -> Iterator[RawListing]:
        try:
            handle = self.path.open("r", encoding="utf-8-sig", newline="")
        except OSError as error:
            raise CsvContractError([f"file could not be read: {error}"]) from error

        with handle:
            reader = csv.DictReader(handle, delimiter=",")
            if reader.fieldnames is None:
                raise CsvContractError(["file is empty: a header row is required"])

            header = [name.strip() for name in reader.fieldnames]
            missing = [column for column in REQUIRED_COLUMNS if column not in header]
            if missing:
                raise CsvContractError([f"missing required column: {name}" for name in missing])

            problems: list[str] = []
            listings: list[RawListing] = []
            seen_references: dict[str, int] = {}

            for offset, row in enumerate(reader):
                # Header is row 1, so the first data row reads as row 2.
                line = offset + 2
                try:
                    listing = self._build_listing(row, line)
                except _RowError as error:
                    problems.extend(error.problems)
                    continue

                first_line = seen_references.get(listing.external_reference)
                if first_line is not None:
                    problems.append(
                        f"row {line}: external_reference "
                        f"{listing.external_reference!r} already used on row {first_line}"
                    )
                    continue
                seen_references[listing.external_reference] = line
                listings.append(listing)

            if problems:
                raise CsvContractError(problems)
            if not listings:
                raise CsvContractError(["file contains a header but no rows"])

        yield from listings

    def _build_listing(self, row: dict[str, str | None], line: int) -> RawListing:
        problems: list[str] = []

        def text(column: str) -> str:
            value = row.get(column)
            return value.strip() if isinstance(value, str) else ""

        def require(column: str) -> str:
            value = text(column)
            if not value:
                problems.append(f"row {line}: {column} is required")
            return value

        reference = require("external_reference")
        make = require("make")
        model = require("model")

        price_cents = _price_to_cents(text("asking_price_eur"), line, "asking_price_eur", problems)
        observed_at = _timestamp(require("observed_at"), line, "observed_at", problems)

        year = _bounded_int(
            text("registration_year"), line, "registration_year", MIN_YEAR, MAX_YEAR, problems
        )
        mileage = _bounded_int(text("mileage_km"), line, "mileage_km", 0, MAX_MILEAGE_KM, problems)
        power_hp = _bounded_int(text("power_hp"), line, "power_hp", 0, 2000, problems)

        if problems:
            raise _RowError(problems)

        options = tuple(
            part.strip() for part in text("options").split(OPTION_SEPARATOR) if part.strip()
        )

        vehicle = RawVehicle(
            make=make,
            model=model,
            year=year,
            mileage_km=mileage,
            # Unknown stays unknown: normalization turns an empty value into
            # UNKNOWN, which lowers confidence rather than inventing a fact.
            trim=text("trim") or None,
            body_type=text("body_type") or None,
            fuel_type=text("fuel") or None,
            transmission=text("transmission") or None,
            drivetrain=text("drivetrain") or None,
            engine_description=text("variant") or None,
            power_hp=power_hp,
            license_plate=text("license_plate") or None,
            option_texts=options,
        )

        seller = None
        seller_type = text("seller_type")
        city = text("seller_city")
        if seller_type or city:
            # Deliberately no name, no telephone number, no email address.
            seller = RawSeller(seller_type=seller_type or "UNKNOWN", name=None, city=city or None)

        assert price_cents is not None and observed_at is not None  # guarded above
        return RawListing(
            external_reference=reference,
            vehicle=vehicle,
            asking_price_cents=price_cents,
            first_seen_at=observed_at,
            last_seen_at=observed_at,
            seller=seller,
            url=text("listing_url") or None,
            status=ListingStatus.ACTIVE,
            snapshots=(
                RawSnapshot(
                    observed_at=observed_at,
                    asking_price_cents=price_cents,
                    mileage_km=mileage,
                    status=ListingStatus.ACTIVE,
                ),
            ),
        )


class _RowError(Exception):
    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__("; ".join(problems))


# -- Field parsing ------------------------------------------------------------


def _price_to_cents(raw: str, line: int, column: str, problems: list[str]) -> int | None:
    """Euro amounts, written the Dutch way or the plain way.

    `27500`, `27.500`, `27500,50` and `27500.50` all mean the same thing; a
    currency symbol or spaces are tolerated. Money becomes integer cents here
    and stays integer cents everywhere after.
    """
    if not raw:
        problems.append(f"row {line}: {column} is required")
        return None

    cleaned = raw.replace("€", "").replace(" ", "").replace(" ", "")
    if "," in cleaned:
        # Dutch: dots group thousands, the comma is the decimal separator.
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif cleaned.count(".") > 1 or ("." in cleaned and len(cleaned.rsplit(".", 1)[1]) == 3):
        # 1.234.567 or 27.500 — dots are grouping, not a decimal point.
        cleaned = cleaned.replace(".", "")

    try:
        amount = Decimal(cleaned)
    except (InvalidOperation, ValueError):
        problems.append(f"row {line}: {column} {raw!r} is not a number")
        return None

    if amount <= 0:
        problems.append(f"row {line}: {column} must be greater than zero")
        return None

    cents = int((amount * 100).to_integral_value())
    if cents > MAX_PRICE_CENTS:
        problems.append(f"row {line}: {column} {raw!r} is implausibly high")
        return None
    return cents


def _timestamp(raw: str, line: int, column: str, problems: list[str]) -> datetime | None:
    """An observation moment: a date, or a full ISO-8601 timestamp.

    Naive values are read as UTC, which is what the rest of the application
    stores.
    """
    if not raw:
        return None
    try:
        parsed: datetime | date = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = date.fromisoformat(raw)
        except ValueError:
            problems.append(f"row {line}: {column} {raw!r} is not a date (use YYYY-MM-DD)")
            return None

    if isinstance(parsed, datetime):
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return datetime(parsed.year, parsed.month, parsed.day, tzinfo=UTC)


def _bounded_int(
    raw: str, line: int, column: str, low: int, high: int, problems: list[str]
) -> int | None:
    if not raw:
        return None
    try:
        value = int(Decimal(raw.replace(".", "").replace(" ", "")))
    except (InvalidOperation, ValueError):
        problems.append(f"row {line}: {column} {raw!r} is not a whole number")
        return None
    if not low <= value <= high:
        problems.append(f"row {line}: {column} {value} is outside {low}-{high}")
        return None
    return value
