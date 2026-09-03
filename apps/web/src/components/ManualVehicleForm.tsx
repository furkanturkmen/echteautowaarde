"use client";

import { ArrowRight } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useId, useState } from "react";

import { Button } from "@/components/Button";
import { ErrorPanel, InsufficientPanel } from "@/components/ResultPanels";
import {
  ApiError,
  type Valuation,
  type VehicleOption,
  createManualVehicle,
  createValuation,
  fetchOptions,
} from "@/lib/api";
import { normalizePlate, parseEuroInput } from "@/lib/format";

/**
 * Manual vehicle entry, for cars the local dataset does not know.
 *
 * The values sent are ordinary Dutch wording ("Automaat", "Plug-in hybride"):
 * the backend normalizes them exactly as it does for any other source, so this
 * path is not a special case in the domain.
 *
 * The option list is the engine's real taxonomy, fetched from the API, so a
 * user can only pick equipment the valuation actually understands.
 *
 * Submitting stores the vehicle, requests one valuation, and opens it by id, so
 * the result page can be refreshed without producing another valuation.
 */

const CURRENT_YEAR = new Date().getFullYear();

const FUEL_CHOICES = ["Benzine", "Diesel", "Hybride", "Plug-in hybride", "Elektrisch", "LPG"];
const TRANSMISSION_CHOICES = ["Automaat", "Handgeschakeld"];
const BODY_CHOICES = ["Hatchback", "Sedan", "Stationwagon", "SUV", "Coupé", "Cabriolet", "MPV"];
const DRIVETRAIN_CHOICES = [
  "Voorwielaandrijving",
  "Achterwielaandrijving",
  "Vierwielaandrijving",
];

const OPTION_CATEGORY_LABELS: Record<string, string> = {
  TRIM_PACKAGE: "Uitvoeringspakket",
  COMFORT: "Comfort",
  SAFETY: "Veiligheid",
  INFOTAINMENT: "Infotainment",
  EXTERIOR: "Exterieur",
  TOWING: "Trekken",
  OTHER: "Overig",
};

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="block text-sm font-medium text-ink">{label}</span>
      {children}
      {hint ? <span className="mt-1 block text-xs text-subtle">{hint}</span> : null}
    </label>
  );
}

const CONTROL =
  "mt-2 h-11 w-full rounded-eaw border border-line-strong bg-surface px-3 text-sm text-ink " +
  "placeholder:text-subtle";

export function ManualVehicleForm() {
  const router = useRouter();
  const errorId = useId();

  const [values, setValues] = useState({
    make: "",
    model: "",
    engineDescription: "",
    trim: "",
    generation: "",
    year: "",
    mileageKm: "",
    fuelType: "",
    transmission: "",
    bodyType: "",
    drivetrain: "",
    powerHp: "",
    licensePlate: "",
    askingPrice: "",
  });
  const [selectedOptions, setSelectedOptions] = useState<Set<string>>(new Set());
  const [options, setOptions] = useState<VehicleOption[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [apiError, setApiError] = useState<ApiError | null>(null);
  const [insufficient, setInsufficient] = useState<Valuation | null>(null);

  useEffect(() => {
    let active = true;
    fetchOptions()
      .then((result) => {
        if (active) setOptions(result);
      })
      .catch(() => {
        // Options are optional input; the form still works without the list.
      });
    return () => {
      active = false;
    };
  }, []);

  function update(field: keyof typeof values, value: string) {
    setValues((current) => ({ ...current, [field]: value }));
    setError(null);
    setApiError(null);
    setInsufficient(null);
  }

  function toggleOption(label: string) {
    setSelectedOptions((current) => {
      const next = new Set(current);
      if (next.has(label)) next.delete(label);
      else next.add(label);
      return next;
    });
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();

    if (!values.make.trim() || !values.model.trim()) {
      setError("Merk en model zijn nodig om vergelijkbare auto's te kunnen zoeken.");
      return;
    }

    const year = values.year ? Number.parseInt(values.year, 10) : null;
    if (year !== null && (Number.isNaN(year) || year < 1950 || year > CURRENT_YEAR + 1)) {
      setError(`Vul een bouwjaar in tussen 1950 en ${CURRENT_YEAR + 1}.`);
      return;
    }

    const mileage = values.mileageKm ? Number.parseInt(values.mileageKm, 10) : null;
    if (mileage !== null && (Number.isNaN(mileage) || mileage < 0 || mileage > 2_000_000)) {
      setError("Vul een geldige kilometerstand in.");
      return;
    }

    const askingPriceCents = values.askingPrice ? parseEuroInput(values.askingPrice) : null;
    if (values.askingPrice.trim() && askingPriceCents === null) {
      setError("Vul een geldige vraagprijs in, bijvoorbeeld 27.500.");
      return;
    }

    const powerHp = values.powerHp ? Number.parseInt(values.powerHp, 10) : null;

    setSubmitting(true);
    setError(null);
    setApiError(null);
    setInsufficient(null);

    try {
      const vehicle = await createManualVehicle({
        make: values.make.trim(),
        model: values.model.trim(),
        year,
        mileageKm: mileage,
        trim: values.trim.trim() || null,
        generation: values.generation.trim() || null,
        bodyType: values.bodyType || null,
        fuelType: values.fuelType || null,
        transmission: values.transmission || null,
        drivetrain: values.drivetrain || null,
        engineDescription: values.engineDescription.trim() || null,
        powerHp: powerHp !== null && Number.isFinite(powerHp) ? powerHp : null,
        licensePlate: values.licensePlate ? normalizePlate(values.licensePlate) : null,
        optionTexts: [...selectedOptions],
      });

      const valuation = await createValuation({
        vehicleId: vehicle.id,
        ...(askingPriceCents !== null ? { askingPriceCents } : {}),
      });

      if (valuation.id !== null) {
        router.push(`/waardebepaling/${valuation.id}`);
        return;
      }

      // Nothing is stored without enough evidence, so there is no result page
      // to open: the outcome stays here, next to the fields that produced it.
      setInsufficient(valuation);
      setSubmitting(false);
    } catch (caught) {
      setSubmitting(false);
      setApiError(
        caught instanceof ApiError
          ? caught
          : new ApiError("De auto kon niet worden gewaardeerd. Probeer het opnieuw.", 500),
      );
    }
  }

  const groupedOptions = options.reduce<Record<string, VehicleOption[]>>((groups, option) => {
    (groups[option.category] ??= []).push(option);
    return groups;
  }, {});

  return (
    <form onSubmit={submit} noValidate>
      <fieldset className="border-0 p-0">
        <legend className="text-sm font-medium tracking-wide text-muted uppercase">
          De auto
        </legend>
        <div className="mt-4 grid gap-5 sm:grid-cols-2">
          <Field label="Merk">
            <input
              value={values.make}
              onChange={(event) => update("make", event.target.value)}
              placeholder="BMW"
              autoComplete="off"
              required
              className={CONTROL}
            />
          </Field>
          <Field label="Model">
            <input
              value={values.model}
              onChange={(event) => update("model", event.target.value)}
              placeholder="3 Serie"
              autoComplete="off"
              required
              className={CONTROL}
            />
          </Field>
          <Field label="Motorvariant" hint="Bijvoorbeeld 330e, 2.0 TDI of Long Range">
            <input
              value={values.engineDescription}
              onChange={(event) => update("engineDescription", event.target.value)}
              placeholder="330e"
              autoComplete="off"
              className={CONTROL}
            />
          </Field>
          <Field label="Uitvoering" hint="Bijvoorbeeld M Sport, AMG Line of Business Edition">
            <input
              value={values.trim}
              onChange={(event) => update("trim", event.target.value)}
              placeholder="M Sport"
              autoComplete="off"
              className={CONTROL}
            />
          </Field>
          <Field label="Bouwjaar">
            <input
              value={values.year}
              onChange={(event) => update("year", event.target.value)}
              inputMode="numeric"
              placeholder="2021"
              autoComplete="off"
              className={CONTROL}
            />
          </Field>
          <Field label="Kilometerstand">
            <input
              value={values.mileageKm}
              onChange={(event) => update("mileageKm", event.target.value)}
              inputMode="numeric"
              placeholder="82000"
              autoComplete="off"
              className={CONTROL}
            />
          </Field>
          <Field label="Brandstof">
            <select
              value={values.fuelType}
              onChange={(event) => update("fuelType", event.target.value)}
              className={CONTROL}
            >
              <option value="">Niet opgegeven</option>
              {FUEL_CHOICES.map((choice) => (
                <option key={choice} value={choice}>
                  {choice}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Transmissie">
            <select
              value={values.transmission}
              onChange={(event) => update("transmission", event.target.value)}
              className={CONTROL}
            >
              <option value="">Niet opgegeven</option>
              {TRANSMISSION_CHOICES.map((choice) => (
                <option key={choice} value={choice}>
                  {choice}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Carrosserie">
            <select
              value={values.bodyType}
              onChange={(event) => update("bodyType", event.target.value)}
              className={CONTROL}
            >
              <option value="">Niet opgegeven</option>
              {BODY_CHOICES.map((choice) => (
                <option key={choice} value={choice}>
                  {choice}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Aandrijving">
            <select
              value={values.drivetrain}
              onChange={(event) => update("drivetrain", event.target.value)}
              className={CONTROL}
            >
              <option value="">Niet opgegeven</option>
              {DRIVETRAIN_CHOICES.map((choice) => (
                <option key={choice} value={choice}>
                  {choice}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Vermogen" hint="In pk">
            <input
              value={values.powerHp}
              onChange={(event) => update("powerHp", event.target.value)}
              inputMode="numeric"
              placeholder="292"
              autoComplete="off"
              className={CONTROL}
            />
          </Field>
          <Field label="Generatie" hint="Bijvoorbeeld G20 of Mk8">
            <input
              value={values.generation}
              onChange={(event) => update("generation", event.target.value)}
              placeholder="G20"
              autoComplete="off"
              className={CONTROL}
            />
          </Field>
        </div>
      </fieldset>

      {options.length > 0 ? (
        <fieldset className="mt-10 border-0 p-0">
          <legend className="text-sm font-medium tracking-wide text-muted uppercase">
            Opties
          </legend>
          <p className="mt-2 text-sm text-muted">
            Opties tellen mee in de vergelijking en in de waardering.
          </p>
          <div className="mt-4 space-y-5">
            {Object.entries(groupedOptions).map(([category, categoryOptions]) => (
              <div key={category}>
                <p className="text-xs font-medium text-subtle">
                  {OPTION_CATEGORY_LABELS[category] ?? category}
                </p>
                <div className="mt-2 flex flex-wrap gap-2">
                  {categoryOptions.map((option) => {
                    const checked = selectedOptions.has(option.labelNl);
                    return (
                      <label
                        key={option.key}
                        className={`inline-flex cursor-pointer items-center gap-2 rounded-eaw border px-3 py-2 text-sm transition-colors ${
                          checked
                            ? "border-brand bg-brand-soft text-brand"
                            : "border-line bg-surface text-ink hover:bg-surface-muted"
                        }`}
                      >
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() => toggleOption(option.labelNl)}
                          className="size-4 accent-[var(--eaw-brand)]"
                        />
                        {option.labelNl}
                      </label>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        </fieldset>
      ) : null}

      <fieldset className="mt-10 border-0 p-0">
        <legend className="text-sm font-medium tracking-wide text-muted uppercase">
          Prijs en kenteken
        </legend>
        <div className="mt-4 grid gap-5 sm:grid-cols-2">
          <Field label="Vraagprijs (optioneel)" hint="Om te zien of de vraagprijs eerlijk is">
            <input
              value={values.askingPrice}
              onChange={(event) => update("askingPrice", event.target.value)}
              inputMode="numeric"
              placeholder="27.500"
              autoComplete="off"
              className={CONTROL}
            />
          </Field>
          <Field label="Kenteken (optioneel)">
            <input
              value={values.licensePlate}
              onChange={(event) =>
                update("licensePlate", normalizePlate(event.target.value).slice(0, 8))
              }
              placeholder="XX-123-X"
              autoComplete="off"
              className={`${CONTROL} uppercase`}
            />
          </Field>
        </div>
      </fieldset>

      {error ? (
        <p id={errorId} role="alert" className="mt-6 text-sm font-medium text-negative">
          {error}
        </p>
      ) : null}

      {apiError ? (
        <div className="mt-6">
          <ErrorPanel error={apiError} showManualLink={false} />
        </div>
      ) : null}

      {insufficient ? (
        <div className="mt-6">
          <InsufficientPanel valuation={insufficient} />
        </div>
      ) : null}

      <div className="mt-8">
        <Button type="submit" size="lg" disabled={submitting} aria-describedby={errorId}>
          {submitting ? "Bezig met waarderen…" : "Bekijk echte autowaarde"}
          {submitting ? null : <ArrowRight aria-hidden="true" className="size-4" />}
        </Button>
      </div>
    </form>
  );
}
