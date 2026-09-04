"""The allowlist for the public dealer pilot.

Only these two dealers' own sites are supported, and adding a third is a
deliberate act with its own robots and terms review — not a configuration
change. Aggregators and marketplaces are not here and do not belong here.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from functools import partial
from typing import Protocol

from echte_auto_waarde.data_sources.base import RawListing
from echte_auto_waarde.data_sources.dealers.autoxl import AutoXlDataSource
from echte_auto_waarde.data_sources.dealers.collector import PoliteFetcher
from echte_auto_waarde.data_sources.dealers.inzoeven import InzoevenDataSource
from echte_auto_waarde.data_sources.dealers.platform import (
    PLATFORM_DEALERS,
    PlatformDataSource,
    build_platform_source,
)
from echte_auto_waarde.data_sources.dealers.vanmossel import VanMosselDataSource
from echte_auto_waarde.models.enums import DataSourceType


class DealerSource(Protocol):
    """What every dealer adapter offers, beyond the import source protocol.

    How a source reads its listings is its own business: one reads an inventory
    page, another follows a sitemap and reads published structured data. The
    command line only needs to start a run and report what it did.
    """

    key: str
    source_type: DataSourceType
    name: str
    quality: float
    limit: int
    # Counted per run, for the collection report.
    discovered: int
    rejected: int

    @property
    def origin(self) -> str: ...

    def fetch_listings(self) -> Iterable[RawListing]: ...


DealerSourceFactory = Callable[..., DealerSource]

DEALER_SOURCES: dict[str, DealerSourceFactory] = {
    "inzoeven": InzoevenDataSource,
    "autoxl": AutoXlDataSource,
    "vanmossel": VanMosselDataSource,
    # Five dealers on one inventory platform. Each was checked on its own —
    # robots.txt, listing path, sampled structured data — before being listed.
    **{slug: partial(build_platform_source, slug) for slug in PLATFORM_DEALERS},
}

__all__ = [
    "DEALER_SOURCES",
    "AutoXlDataSource",
    "DealerSource",
    "PLATFORM_DEALERS",
    "InzoevenDataSource",
    "PlatformDataSource",
    "PoliteFetcher",
    "VanMosselDataSource",
]
