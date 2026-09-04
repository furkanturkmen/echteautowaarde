"""Which specification source the application uses.

One place decides, so the routes never construct a source themselves and tests
can substitute one. When enrichment is switched off this returns nothing at all,
and the plate lookup answers from local data only — no outbound call is even
possible.
"""

from __future__ import annotations

from functools import lru_cache

from echte_auto_waarde.config import get_settings
from echte_auto_waarde.data_sources.base import VehicleSpecificationSource
from echte_auto_waarde.data_sources.rdw import RdwVehicleSource


@lru_cache(maxsize=1)
def get_vehicle_source() -> VehicleSpecificationSource | None:
    """The one place that decides whether enrichment exists at all.

    Off by default: the application is local-first, and the only outbound call
    it can make is one the operator switched on. When this returns None the
    plate lookup answers from local data alone and cannot reach the network.
    """
    if not get_settings().rdw_enabled:
        return None
    return RdwVehicleSource()
