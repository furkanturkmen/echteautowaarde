/**
 * Dutch wording for the backend's stable English codes.
 *
 * The backend owns the classification; this file owns the words a Dutch
 * consumer reads. Every key here corresponds to a code the API actually emits —
 * nothing is invented to fill a gap.
 */

import type {
  BodyType,
  DealClassification,
  Drivetrain,
  FuelType,
  SellerType,
  SimilarityEntry,
  Transmission,
} from "@/lib/api";
import { formatMileage } from "@/lib/format";

export const BODY_TYPE_LABELS: Record<BodyType, string> = {
  HATCHBACK: "Hatchback",
  SEDAN: "Sedan",
  STATIONWAGON: "Stationwagen",
  SUV: "SUV",
  COUPE: "Coupé",
  CABRIOLET: "Cabriolet",
  MPV: "MPV",
  UNKNOWN: "Onbekend",
};

export const FUEL_TYPE_LABELS: Record<FuelType, string> = {
  PETROL: "Benzine",
  DIESEL: "Diesel",
  HYBRID: "Hybride",
  PLUGIN_HYBRID: "Plug-in hybride",
  ELECTRIC: "Elektrisch",
  LPG: "LPG",
  UNKNOWN: "Onbekend",
};

export const TRANSMISSION_LABELS: Record<Transmission, string> = {
  MANUAL: "Handgeschakeld",
  AUTOMATIC: "Automaat",
  UNKNOWN: "Onbekend",
};

export const DRIVETRAIN_LABELS: Record<Drivetrain, string> = {
  FWD: "Voorwielaandrijving",
  RWD: "Achterwielaandrijving",
  AWD: "Vierwielaandrijving",
  UNKNOWN: "Onbekend",
};

export const SELLER_TYPE_LABELS: Record<SellerType, string> = {
  PRIVATE: "Particulier",
  DEALER: "Dealer",
  UNKNOWN: "Onbekend",
};

export type DealTone = "positive" | "neutral" | "caution" | "negative";

export const DEAL_LABELS: Record<
  DealClassification,
  { label: string; tone: DealTone; explanation: string }
> = {
  EXCELLENT_DEAL: {
    label: "Zeer goede deal",
    tone: "positive",
    explanation: "De vraagprijs ligt duidelijk onder de geschatte marktwaarde.",
  },
  GOOD_DEAL: {
    label: "Goede koop",
    tone: "positive",
    explanation: "De vraagprijs ligt onder de geschatte marktwaarde.",
  },
  FAIR_PRICE: {
    label: "Eerlijke prijs",
    tone: "neutral",
    explanation: "De vraagprijs ligt dicht bij de geschatte marktwaarde.",
  },
  EXPENSIVE: {
    label: "Aan de dure kant",
    tone: "caution",
    explanation: "De vraagprijs ligt boven de geschatte marktwaarde.",
  },
  VERY_EXPENSIVE: {
    label: "Erg duur",
    tone: "negative",
    explanation: "De vraagprijs ligt duidelijk boven de geschatte marktwaarde.",
  },
};

export const ADJUSTMENT_LABELS: Record<string, string> = {
  MILEAGE: "Kilometerstand",
  AGE: "Bouwjaar",
  OPTIONS: "Opties",
  TRIM: "Uitvoering",
};

export const CONFIDENCE_FACTOR_LABELS: Record<string, string> = {
  comparable_count: "Aantal vergelijkbare auto's",
  average_similarity: "Gemiddelde overeenkomst",
  price_dispersion: "Spreiding in marktprijzen",
  observation_age: "Actualiteit van de advertenties",
  data_completeness: "Volledigheid van de autogegevens",
  source_quality: "Kwaliteit van de databron",
  search_widened: "Zoekopdracht verbreed",
};

/** Short human-readable detail per confidence factor, from real backend detail. */
export function describeConfidenceFactor(
  code: string,
  detail: Record<string, unknown>,
): string | null {
  const number = (key: string): number | null =>
    typeof detail[key] === "number" ? (detail[key] as number) : null;

  switch (code) {
    case "comparable_count": {
      const count = number("comparable_count");
      return count === null ? null : `${count} vergelijkbare auto's gebruikt`;
    }
    case "average_similarity": {
      const similarity = number("average_similarity");
      return similarity === null
        ? null
        : `gemiddeld ${Math.round(similarity * 100)}% overeenkomst`;
    }
    case "price_dispersion": {
      const dispersion = number("relative_dispersion");
      return dispersion === null
        ? null
        : `prijzen lopen ${Math.round(dispersion * 100)}% uiteen rond de mediaan`;
    }
    case "observation_age": {
      const days = number("median_observation_age_days");
      if (days === null) return null;
      return days === 0 ? "advertenties van vandaag" : `mediaan ${days} dagen oud`;
    }
    case "data_completeness": {
      const missing = number("missing_field_count");
      const optionsComplete = detail["option_data_complete"];
      if (missing === null) return null;
      if (missing === 0 && optionsComplete === true) return "alle kenmerken bekend";
      const parts: string[] = [];
      if (missing > 0) parts.push(`${missing} kenmerk(en) onbekend`);
      if (optionsComplete === false) parts.push("optiegegevens onvolledig");
      return parts.join(", ");
    }
    case "source_quality": {
      const quality = number("source_quality");
      return quality === null ? null : `bronkwaliteit ${Math.round(quality * 100)}%`;
    }
    case "search_widened": {
      const level = number("widening_level");
      return level === null ? null : `zoekopdracht ${level} stap(pen) verbreed`;
    }
    default:
      return null;
  }
}

const OPTION_FALLBACK = (key: string) =>
  key.replace(/_/g, " ").replace(/^\w/, (character) => character.toUpperCase());

/**
 * Describe one similarity reason or difference in Dutch.
 *
 * Option entries carry only the canonical key, so the caller passes a lookup
 * built from the vehicles in the response — the Dutch label always comes from
 * the backend's own taxonomy rather than a hardcoded translation.
 */
export function describeSimilarityEntry(
  entry: SimilarityEntry,
  optionLabels: Map<string, string>,
): string {
  const value = entry.value;
  const target = entry.targetValue;
  const optionLabel = (key: unknown) =>
    typeof key === "string" ? (optionLabels.get(key) ?? OPTION_FALLBACK(key)) : "optie";

  switch (entry.code) {
    case "SAME_GENERATION":
      return `Zelfde generatie${value ? ` (${value})` : ""}`;
    case "SAME_BODY_TYPE":
      return `Zelfde carrosserie (${BODY_TYPE_LABELS[value as BodyType] ?? value})`;
    case "SAME_POWERTRAIN":
      return `Zelfde aandrijving (${FUEL_TYPE_LABELS[value as FuelType] ?? value})`;
    case "SAME_ENGINE":
      return `Zelfde motorvariant (${value})`;
    case "SAME_TRANSMISSION":
      return `Zelfde transmissie (${TRANSMISSION_LABELS[value as Transmission] ?? value})`;
    case "SAME_TRIM":
      return `Zelfde uitvoering (${value})`;
    case "SAME_YEAR":
      return `Zelfde bouwjaar (${value})`;
    case "SIMILAR_MILEAGE":
      return "Vergelijkbare kilometerstand";
    case "SHARED_OPTION":
      return optionLabel(value);

    case "DIFFERENT_GENERATION":
      return `Andere generatie: ${value} in plaats van ${target}`;
    case "DIFFERENT_BODY_TYPE":
      return `Andere carrosserie: ${BODY_TYPE_LABELS[value as BodyType] ?? value}`;
    case "DIFFERENT_POWERTRAIN":
      return `Andere aandrijving: ${FUEL_TYPE_LABELS[value as FuelType] ?? value}`;
    case "DIFFERENT_ENGINE":
      return `Andere motorvariant: ${value}`;
    case "DIFFERENT_TRANSMISSION":
      return `Andere transmissie: ${TRANSMISSION_LABELS[value as Transmission] ?? value}`;
    case "DIFFERENT_DRIVETRAIN":
      return `Andere aandrijflijn: ${DRIVETRAIN_LABELS[value as Drivetrain] ?? value}`;
    case "DIFFERENT_TRIM":
      return `Andere uitvoering: ${value} in plaats van ${target}`;
    case "YEAR_DIFFERENCE": {
      const delta = entry.delta ?? 0;
      const years = Math.abs(delta);
      return delta > 0
        ? `${years} jaar nieuwer`
        : `${years} jaar ouder`;
    }
    case "MILEAGE_DIFFERENCE": {
      // The word already carries the direction, so the number must not repeat
      // it: "+56.059 km minder gereden" reads as a contradiction.
      const delta = entry.delta ?? 0;
      return `${formatMileage(Math.abs(delta))} ${delta > 0 ? "meer" : "minder"} gereden`;
    }
    case "POWER_DIFFERENCE": {
      const delta = entry.delta ?? 0;
      return delta > 0 ? `${delta} pk meer vermogen` : `${Math.abs(delta)} pk minder vermogen`;
    }
    // The taxonomy's own casing is kept: lowercasing turns "Apple CarPlay" into
    // "apple carplay" and "Matrix LED-koplampen" into "matrix led-koplampen".
    case "EXTRA_OPTION":
      return `Heeft ${optionLabel(value)}`;
    case "MISSING_OPTION":
      return `Geen ${optionLabel(value)}`;
    default:
      return entry.code;
  }
}

/**
 * Dutch description of how wide the comparable search had to go.
 *
 * The API's own description is English on purpose (it is a developer-facing
 * field); the consumer wording is composed here from the level.
 */
export const WIDENING_LEVEL_LABELS: Record<number, string> = {
  0: "zelfde model, generatie, aandrijving en transmissie, binnen 3 modeljaren",
  1: "zelfde model en generatie, vergelijkbare aandrijving, binnen 4 modeljaren",
  2: "zelfde model, elke generatie, binnen 5 modeljaren",
};

const kilometres = new Intl.NumberFormat("nl-NL");
const years = new Intl.NumberFormat("nl-NL", { maximumFractionDigits: 1 });
const percent = new Intl.NumberFormat("nl-NL", { style: "percent", maximumFractionDigits: 0 });

/**
 * Dutch explanation of one valuation adjustment.
 *
 * Built from the adjustment's structured detail, so the wording is Dutch while
 * every number still comes from the engine. Returns null when the backend sent
 * no detail — better to show the amount alone than to invent a reason.
 */
export function describeAdjustment(type: string, detail: Record<string, unknown> | null): string | null {
  if (!detail) return null;
  const number = (key: string): number | null =>
    typeof detail[key] === "number" ? (detail[key] as number) : null;

  switch (type) {
    case "MILEAGE": {
      const delta = number("deltaKm");
      const median = number("comparableMedianMileageKm");
      if (delta === null || median === null) return null;
      return `Deze auto reed ${kilometres.format(Math.abs(delta))} km ${
        delta > 0 ? "meer" : "minder"
      } dan de mediaan van de vergelijkbare auto's (${kilometres.format(median)} km).`;
    }
    case "AGE": {
      const delta = number("deltaYears");
      const median = number("comparableMedianYear");
      if (delta === null || median === null) return null;
      return `Deze auto is ${years.format(Math.abs(delta))} jaar ${
        delta > 0 ? "nieuwer" : "ouder"
      } dan de mediaan van de vergelijkbare auto's (${years.format(median)}).`;
    }
    case "OPTIONS": {
      const target = number("targetOptionImportance");
      const median = number("comparableMedianOptionImportance");
      if (target === null || median === null) return null;
      return target > median
        ? "Deze auto is beter uitgerust dan de meeste vergelijkbare auto's."
        : "Deze auto is minder uitgerust dan de meeste vergelijkbare auto's.";
    }
    case "TRIM": {
      const share = number("comparableShareWithPackage");
      const trim = typeof detail["trim"] === "string" ? (detail["trim"] as string) : null;
      if (share === null) return null;
      return trim
        ? `Deze auto heeft de ${trim}-uitvoering; ${percent.format(share)} van de vergelijkbare auto's heeft zo'n pakket.`
        : `${percent.format(share)} van de vergelijkbare auto's heeft een sportievere uitvoering dan deze auto.`;
    }
    default:
      return null;
  }
}
