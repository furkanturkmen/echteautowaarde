"""Vehicle option entities.

Options are strategically important: they drive both similarity and part of the
valuation. Listings describe the same feature in many ways, so every option is
resolved to a canonical definition while the raw text is preserved.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Enum, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from echte_auto_waarde.db.base import Base, TimestampMixin
from echte_auto_waarde.models.enums import OptionCategory

if TYPE_CHECKING:
    from echte_auto_waarde.models.vehicle import Vehicle


class VehicleOptionDefinition(Base, TimestampMixin):
    """Canonical option, seeded from the option taxonomy in the domain layer."""

    __tablename__ = "vehicle_option_definitions"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Stable machine key, e.g. "adaptive_cruise_control".
    key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    # Dutch consumer label, e.g. "Adaptieve cruise control".
    label_nl: Mapped[str] = mapped_column(String(96))
    category: Mapped[OptionCategory] = mapped_column(
        Enum(OptionCategory, native_enum=False, length=16), default=OptionCategory.OTHER
    )

    # Relative weight (0..1) expressing how much this option matters for
    # similarity and valuation. Configurable per the taxonomy, never hardcoded
    # at the call site.
    importance: Mapped[float] = mapped_column(Float, default=0.5)

    vehicle_options: Mapped[list[VehicleOption]] = relationship(back_populates="definition")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<VehicleOptionDefinition {self.key}>"


class VehicleOption(Base, TimestampMixin):
    """A canonical option present on one vehicle."""

    __tablename__ = "vehicle_options"

    id: Mapped[int] = mapped_column(primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(
        ForeignKey("vehicles.id", ondelete="CASCADE"), index=True
    )
    definition_id: Mapped[int] = mapped_column(
        ForeignKey("vehicle_option_definitions.id", ondelete="CASCADE"), index=True
    )

    # The wording the source used, kept so any normalization stays traceable.
    raw_text: Mapped[str | None] = mapped_column(String(160))

    vehicle: Mapped[Vehicle] = relationship(back_populates="options")
    definition: Mapped[VehicleOptionDefinition] = relationship(back_populates="vehicle_options")

    __table_args__ = (UniqueConstraint("vehicle_id", "definition_id", name="uq_vehicle_option"),)
