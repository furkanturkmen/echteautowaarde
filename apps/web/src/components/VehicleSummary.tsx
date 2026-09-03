import type { Vehicle } from "@/lib/api";
import { formatMileage, formatPlate } from "@/lib/format";
import { BODY_TYPE_LABELS, FUEL_TYPE_LABELS, TRANSMISSION_LABELS } from "@/lib/labels";

/**
 * Which car is being valued — the first thing a reader should resolve.
 *
 * Only known facts appear: an unknown transmission or body type is left out
 * rather than shown as "Onbekend" noise.
 */
export function VehicleSummary({
  vehicle,
  size = "lg",
}: {
  vehicle: Vehicle;
  size?: "lg" | "sm";
}) {
  const title = [vehicle.make, vehicle.model, vehicle.engineDescription, vehicle.trim]
    .filter(Boolean)
    .join(" ");

  const facts = [
    vehicle.year ? String(vehicle.year) : null,
    vehicle.mileageKm !== null ? formatMileage(vehicle.mileageKm) : null,
    vehicle.transmission !== "UNKNOWN" ? TRANSMISSION_LABELS[vehicle.transmission] : null,
    vehicle.fuelType !== "UNKNOWN" ? FUEL_TYPE_LABELS[vehicle.fuelType] : null,
    vehicle.bodyType !== "UNKNOWN" ? BODY_TYPE_LABELS[vehicle.bodyType] : null,
    vehicle.powerHp ? `${vehicle.powerHp} pk` : null,
  ].filter(Boolean) as string[];

  return (
    <div>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <h1
          className={
            size === "lg"
              ? "text-2xl font-semibold tracking-tight text-ink sm:text-3xl"
              : "text-lg font-semibold text-ink"
          }
        >
          {title}
        </h1>
        {vehicle.licensePlate ? (
          <span className="inline-flex items-center rounded-eaw-sm border border-plate-ink/20 bg-plate px-2.5 py-1 font-[family-name:var(--font-plate)] text-sm font-bold tracking-[0.08em] text-plate-ink">
            {formatPlate(vehicle.licensePlate)}
          </span>
        ) : null}
      </div>

      <p className={`mt-2 text-muted ${size === "lg" ? "text-base" : "text-sm"}`}>
        {facts.join(" · ")}
      </p>
    </div>
  );
}
