"""The allowlist for the public dealer pilot.

Only these two dealers' own sites are supported, and adding a third is a
deliberate act with its own robots and terms review — not a configuration
change. Aggregators and marketplaces are not here and do not belong here.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Protocol

from echte_auto_waarde.data_sources.base import RawListing
from echte_auto_waarde.data_sources.dealers.autoxl import AutoXlDataSource
from echte_auto_waarde.data_sources.dealers.collector import PoliteFetcher
from echte_auto_waarde.data_sources.dealers.inzoeven import InzoevenDataSource
from echte_auto_waarde.models.enums import DataSourceType


class DealerSource(Protocol):
    """What every dealer adapter offers, beyond the import source protocol."""

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

    def parse(self, html: str) -> Iterable[RawListing]: ...


DealerSourceFactory = Callable[..., DealerSource]

DEALER_SOURCES: dict[str, DealerSourceFactory] = {
    "inzoeven": InzoevenDataSource,
    "autoxl": AutoXlDataSource,
}

__all__ = [
    "DEALER_SOURCES",
    "AutoXlDataSource",
    "DealerSource",
    "InzoevenDataSource",
    "PoliteFetcher",
]
