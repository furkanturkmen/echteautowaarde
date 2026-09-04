"""Dutch vehicle register enrichment (RDW open data).

This is the only module that knows Dutch register field names. Everything
outside it works with `RawVehicle`, so the register can change, gain fields or
be replaced without touching the domain, the comparable engine, the valuation
engine, the API or the frontend.

**What this source is.** A specification source: it describes the car behind a
plate. It is not a market source. It has no listings, no asking prices, no
current market values, and no mileage. A valuation is still produced entirely by
our own engine from comparable listings.

**Licence.** The register's open data is published under CC0 and free to use,
including commercially, with no account and no API key. The publisher's terms
add two conditions that shape this application: reuse may not state that the
data comes from them, and their logo and house style may not be used. The
consumer interface therefore speaks of "het kentekenregister" and carries no
third-party branding. An optional Socrata app token (free, no payment details)
only widens throttling; requests work without one and none is sent unless
configured.

**Fair use.** The publisher serves this on a fair-use basis, so one lookup means
one small request per dataset, with an explicit timeout, and stored vehicles are
not fetched again.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

import httpx

from echte_auto_waarde.config import get_settings
from echte_auto_waarde.data_sources.base import (
    RawVehicle,
    VehicleSourceUnavailable,
)
from echte_auto_waarde.models.enums import DataSourceType

logger = logging.getLogger(__name__)

RDW_SOURCE_KEY = "rdw"

# The register's own dataset identifiers.
DATASET_VEHICLES = "m9d7-ebf2"  # Gekentekende voertuigen: make, body, dates
DATASET_FUEL = "8ys7-d773"  # Brandstof: fuel description and net maximum power
DATASET_BODY = "vezc-m2t6"  # Carrosserie: European body description

# Only passenger cars are in scope. The register also holds trucks, buses,
# trailers and specials; BB-100-B, for example, is a concrete mixer.
PASSENGER_CAR = "personenauto"

# Register wording for electric propulsion, used to tell a hybrid from a plain
# combustion car when several fuel rows are returned.
_ELECTRIC_WORDS = {"elektriciteit", "elektrisch"}

# Fields that mark a hybrid as externally chargeable. Without one of these the
# powertrain is reported as a plain hybrid rather than guessed as plug-in.
_PLUGIN_MARKERS = (
    "elektrisch_verbruik_extern_opladen_wltp",
    "actie_radius_extern_opladen_wltp",
    "actie_radius_extern_opladen_stad_wltp",
    "max_vermogen_15_minuten",
)

# 1 kW in metric horsepower.
_HP_PER_KW = 1.35962


class RdwVehicleSource:
    """Vehicle specifications for one plate, from the open register."""

    key = RDW_SOURCE_KEY
    source_type = DataSourceType.RDW
    # Consumer-facing name. Deliberately neutral: the terms forbid presenting
    # the data as the publisher's, so the register is named, not the publisher.
    name = "Kentekenregister (open data)"

    def __init__(
        self,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
        app_token: str | None = None,
    ) -> None:
        settings = get_settings()
        self._base_url = (base_url or settings.rdw_base_url).rstrip("/")
        self._timeout = timeout_seconds or settings.rdw_timeout_seconds
        self._app_token = app_token or settings.rdw_app_token

    # -- HTTP ---------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        # Anonymous requests are throttled from a shared pool per IP address; a
        # token is optional and free, so it is sent only when one is configured.
        return {"X-App-Token": self._app_token} if self._app_token else {}

    def _get(self, dataset: str, plate: str) -> list[dict[str, Any]]:
        url = f"{self._base_url}/{dataset}.json"
        try:
            response = httpx.get(
                url,
                params={"kenteken": plate},
                headers=self._headers(),
                timeout=self._timeout,
            )
        except httpx.TimeoutException as error:
            raise VehicleSourceUnavailable(f"Register timed out after {self._timeout}s") from error
        except httpx.HTTPError as error:
            raise VehicleSourceUnavailable(f"Register unreachable: {error}") from error

        if response.status_code != httpx.codes.OK:
            raise VehicleSourceUnavailable(f"Register returned HTTP {response.status_code}")

        try:
            payload = response.json()
        except ValueError as error:
            raise VehicleSourceUnavailable("Register returned a non-JSON body") from error

        if not isinstance(payload, list):
            raise VehicleSourceUnavailable("Register returned an unexpected shape")
        return [row for row in payload if isinstance(row, dict)]

    # -- Public API ---------------------------------------------------------

    def fetch_vehicle(self, plate: str) -> RawVehicle | None:
        """Specifications for a normalized plate, or None when unknown.

        None also covers a plate that exists but is not a passenger car: this
        product values cars, and a truck is as useless to it as an unknown
        plate. Callers show the manual route in both cases.
        """
        rows = self._get(DATASET_VEHICLES, plate)
        if not rows:
            return None

        registration = rows[0]
        if _text(registration.get("voertuigsoort")).lower() != PASSENGER_CAR:
            logger.info(
                "Plate %s is registered as %r, not a passenger car",
                plate,
                _text(registration.get("voertuigsoort")),
            )
            return None

        # Enrichment is best-effort per dataset: the registration record alone
        # is already useful, so a failing detail request degrades to less data
        # rather than to no data at all.
        fuel_rows = _optional(lambda: self._get(DATASET_FUEL, plate))
        body_rows = _optional(lambda: self._get(DATASET_BODY, plate))

        return map_to_raw_vehicle(registration, fuel_rows, body_rows)


def map_to_raw_vehicle(
    registration: dict[str, Any],
    fuel_rows: list[dict[str, Any]] | None = None,
    body_rows: list[dict[str, Any]] | None = None,
) -> RawVehicle:
    """Map register records onto the shared raw vehicle shape.

    Only fields the register actually publishes are mapped. Mileage, trim,
    transmission, drivetrain, options and any market price are absent from the
    register and stay absent here: a gap is reported as a gap and completed by
    the user, never filled with a guess.
    """
    first_registration = _date(registration.get("datum_eerste_toelating_dt")) or _compact_date(
        registration.get("datum_eerste_toelating")
    )

    power_kw = _max_power_kw(fuel_rows or [])

    return RawVehicle(
        make=_text(registration.get("merk")),
        model=_text(registration.get("handelsbenaming")),
        year=first_registration.year if first_registration else None,
        first_registration_date=first_registration,
        license_plate=_text(registration.get("kenteken")) or None,
        # The register's own body wording, with the European description as a
        # fallback. Both are normalized by the shared normalization layer.
        body_type=_text(registration.get("inrichting")) or _body_from_rows(body_rows or []),
        fuel_type=_fuel_description(fuel_rows or []),
        engine_displacement_cc=_int(registration.get("cilinderinhoud")),
        power_kw=power_kw,
        power_hp=round(power_kw * _HP_PER_KW) if power_kw else None,
        doors=_int(registration.get("aantal_deuren")),
        seats=_int(registration.get("aantal_zitplaatsen")),
        color=_colour(registration.get("eerste_kleur")),
        catalog_price_cents=_euro_to_cents(registration.get("catalogusprijs")),
    )


# -- Field helpers ----------------------------------------------------------


def _text(value: Any) -> str:
    return str(value).strip() if isinstance(value, str) else ""


def _int(value: Any) -> int | None:
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _euro_to_cents(value: Any) -> int | None:
    """The catalogue price, published in whole euros."""
    amount = _float(value)
    return round(amount * 100) if amount and amount > 0 else None


def _date(value: Any) -> date | None:
    text = _text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _compact_date(value: Any) -> date | None:
    """The register also publishes dates as `YYYYMMDD`."""
    text = _text(value)
    if len(text) != 8 or not text.isdigit():
        return None
    try:
        return date(int(text[:4]), int(text[4:6]), int(text[6:8]))
    except ValueError:
        return None


def _colour(value: Any) -> str | None:
    """Colour, when one is actually registered."""
    text = _text(value)
    if not text or text.lower() in {"niet geregistreerd", "n.v.t."}:
        return None
    return text.capitalize()


def _body_from_rows(rows: list[dict[str, Any]]) -> str:
    for row in rows:
        description = _text(row.get("type_carrosserie_europese_omschrijving"))
        if description:
            return description
    return ""


def _max_power_kw(rows: list[dict[str, Any]]) -> int | None:
    """The strongest power figure across the fuel rows.

    A hybrid lists one row per energy source; the combustion row carries the
    figure that describes the car. Taking the maximum avoids reporting a plug-in
    hybrid as the output of its electric motor alone.
    """
    values = [_float(row.get("nettomaximumvermogen")) for row in rows]
    usable = [value for value in values if value and value > 0]
    return round(max(usable)) if usable else None


def _fuel_description(rows: list[dict[str, Any]]) -> str:
    """One fuel wording for the normalization layer.

    A single row is passed through as published. Several rows mean a hybrid, and
    the distinction between a plain and a plug-in hybrid is only drawn when the
    register actually reports external charging — never guessed from the
    presence of an electric motor alone.
    """
    descriptions = [_text(row.get("brandstof_omschrijving")) for row in rows]
    present = [description for description in descriptions if description]
    if not present:
        return ""
    if len(present) == 1:
        return present[0]

    has_electric = any(description.lower() in _ELECTRIC_WORDS for description in present)
    has_combustion = any(description.lower() not in _ELECTRIC_WORDS for description in present)
    if not (has_electric and has_combustion):
        return present[0]

    chargeable = any(
        _float(row.get(marker)) not in (None, 0.0) for row in rows for marker in _PLUGIN_MARKERS
    )
    return "Plug-in hybride" if chargeable else "Hybride"


def _optional(call) -> list[dict[str, Any]]:
    """Run a detail request, treating failure as missing detail."""
    try:
        return call()
    except VehicleSourceUnavailable as error:
        logger.info("Register detail unavailable, continuing without it: %s", error)
        return []
