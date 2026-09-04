"""Which market evidence a valuation is allowed to use.

The demo market is invented. Real market data is imported from a file someone
was entitled to supply. Mixing them would produce a number that looks like a
market estimate and is partly fiction, which is the one thing this product
promises not to do.

The rule lives here, in one function, so it is not scattered through the
application as `if source == SYNTHETIC` checks. The comparable query applies it
once; the valuation engine never sees it and still receives comparables without
knowing which adapter produced them.
"""

from __future__ import annotations

from enum import StrEnum

from echte_auto_waarde.models.enums import DataSourceType

# Everything that is not the invented demo market. A vehicle entered by hand or
# enriched from the register is real; so is an imported listing.
REAL_SOURCE_TYPES = frozenset(
    {
        DataSourceType.CSV_IMPORT,
        DataSourceType.DEALER_SITE,
        DataSourceType.RDW,
        DataSourceType.MANUAL,
    }
)
DEMO_SOURCE_TYPES = frozenset({DataSourceType.SYNTHETIC})


class MarketMode(StrEnum):
    """Which market this installation is answering questions about.

    DEMO is the default because that is what a fresh install contains. Switching
    to REAL is a deliberate act by whoever imported real data, and it is what
    stops a real valuation from quietly resting on invented listings.
    """

    DEMO = "DEMO"
    REAL = "REAL"


def evidence_source_types(mode: MarketMode, target_is_demo: bool) -> frozenset[DataSourceType]:
    """The data sources a valuation for this target may draw evidence from.

    A demo vehicle is always valued against the demo market: it is a fictional
    car, and comparing it to real listings would be just as wrong in the other
    direction.

    A real vehicle in REAL mode may only use real evidence. When too little of
    it exists the valuation reports insufficient data — a shortage of real
    comparables is never made up with demo listings.
    """
    if target_is_demo:
        return DEMO_SOURCE_TYPES
    if mode is MarketMode.REAL:
        return REAL_SOURCE_TYPES
    return DEMO_SOURCE_TYPES


SYNTHETIC_DISCLAIMER = (
    "Deze waardering is gebaseerd op een synthetische demomarkt en is niet "
    "geschikt voor echte aankoopbeslissingen."
)
IMPORTED_DISCLAIMER = (
    "Deze waardering is gebaseerd op geïmporteerde marktgegevens: waargenomen "
    "vraagprijzen, geen verkoopprijzen."
)
DEALER_DISCLAIMER = (
    "Bron: openbare dealeradvertenties. Dit zijn waargenomen vraagprijzen, geen verkoopprijzen."
)
MIXED_DISCLAIMER = (
    "Deze waardering gebruikt zowel geïmporteerde marktgegevens als "
    "demogegevens en is niet geschikt voor echte aankoopbeslissingen."
)
NO_EVIDENCE_DISCLAIMER = (
    "Er is geen marktbewijs gebruikt: we hebben te weinig vergelijkbare advertenties gevonden."
)


def describe_evidence(source_types: set[DataSourceType]) -> str:
    """One honest Dutch sentence about what this valuation actually rests on."""
    if not source_types:
        return NO_EVIDENCE_DISCLAIMER
    has_demo = DataSourceType.SYNTHETIC in source_types
    has_real = bool(source_types - DEMO_SOURCE_TYPES)
    if has_demo and has_real:
        return MIXED_DISCLAIMER
    if has_demo:
        return SYNTHETIC_DISCLAIMER
    # Naming the kind of source, without implying a partnership or an official
    # feed: these are advertisements a dealer published publicly.
    if source_types == {DataSourceType.DEALER_SITE}:
        return DEALER_DISCLAIMER
    return IMPORTED_DISCLAIMER
