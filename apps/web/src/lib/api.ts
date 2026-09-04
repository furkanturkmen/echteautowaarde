/**
 * Client for the local Echte Auto Waarde API.
 *
 * The types below mirror the FastAPI response models exactly; the frontend
 * never invents a field the backend does not return, and never reproduces
 * valuation logic — it only renders what the engine produced.
 */

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type BodyType =
  | "HATCHBACK"
  | "SEDAN"
  | "STATIONWAGON"
  | "SUV"
  | "COUPE"
  | "CABRIOLET"
  | "MPV"
  | "UNKNOWN";

export type FuelType =
  | "PETROL"
  | "DIESEL"
  | "HYBRID"
  | "PLUGIN_HYBRID"
  | "ELECTRIC"
  | "LPG"
  | "UNKNOWN";

export type Transmission = "MANUAL" | "AUTOMATIC" | "UNKNOWN";
export type Drivetrain = "FWD" | "RWD" | "AWD" | "UNKNOWN";
export type SellerType = "PRIVATE" | "DEALER" | "UNKNOWN";

export type DealClassification =
  | "EXCELLENT_DEAL"
  | "GOOD_DEAL"
  | "FAIR_PRICE"
  | "EXPENSIVE"
  | "VERY_EXPENSIVE";

export interface VehicleOption {
  key: string;
  labelNl: string;
  category: string;
  importance: number;
}

export interface Vehicle {
  id: number;
  licensePlate: string | null;
  make: string;
  model: string;
  generation: string | null;
  trim: string | null;
  bodyType: BodyType;
  fuelType: FuelType;
  transmission: Transmission;
  drivetrain: Drivetrain;
  engineDescription: string | null;
  powerKw: number | null;
  powerHp: number | null;
  year: number | null;
  firstRegistrationDate: string | null;
  mileageKm: number | null;
  color: string | null;
  doors: number | null;
  seats: number | null;
  catalogPriceCents: number | null;
  options: VehicleOption[];
}

export interface SimilarityEntry {
  code: string;
  field: string | null;
  value: string | number | null;
  targetValue: string | number | null;
  delta: number | null;
}

export interface Comparable {
  listingId: number;
  similarity: number;
  askingPriceCents: number;
  priceDifferenceCents: number | null;
  sellerType: SellerType | null;
  observedAt: string | null;
  vehicle: Vehicle;
  reasons: SimilarityEntry[];
  differences: SimilarityEntry[];
}

export interface Adjustment {
  type: string;
  amountCents: number;
  reason: string;
  detail: Record<string, unknown> | null;
}

export interface ConfidenceFactor {
  code: string;
  impact: "POSITIVE" | "NEGATIVE";
  score: number;
  weight: number;
  detail: Record<string, unknown>;
}

export interface MarketStatistics {
  comparableCount: number;
  minPriceCents: number;
  maxPriceCents: number;
  medianPriceCents: number;
  weightedMedianPriceCents: number;
  p25PriceCents: number;
  p75PriceCents: number;
  relativeDispersion: number;
  averageMileageKm: number | null;
  averageYear: number | null;
  averageSimilarity: number;
  minSimilarity: number;
  maxSimilarity: number;
  outliersRemoved: number;
}

export interface Valuation {
  id: number | null;
  sufficientData: boolean;
  algorithmVersion: string;
  vehicle: Vehicle;
  askingPriceCents: number | null;
  estimatedMarketValueCents: number | null;
  recommendedBuyPriceLowCents: number | null;
  recommendedBuyPriceHighCents: number | null;
  marketBasisCents: number | null;
  dealClassification: DealClassification | null;
  confidenceScore: number | null;
  confidenceFactors: ConfidenceFactor[];
  comparableCount: number;
  wideningLevel: number;
  wideningDescription: string | null;
  marketStatistics: MarketStatistics | null;
  adjustments: Adjustment[];
  comparables: Comparable[];
  insufficientDataReason: string | null;
  dataDisclaimer: string;
}

export interface ExampleVehicle {
  vehicleId: number;
  licensePlate: string | null;
  make: string;
  model: string;
  year: number | null;
  mileageKm: number | null;
  trim: string | null;
  engineDescription: string | null;
  askingPriceCents: number;
}

export interface ManualVehicleInput {
  make: string;
  model: string;
  year?: number | null;
  mileageKm?: number | null;
  trim?: string | null;
  generation?: string | null;
  bodyType?: string | null;
  fuelType?: string | null;
  transmission?: string | null;
  drivetrain?: string | null;
  engineDescription?: string | null;
  powerHp?: number | null;
  licensePlate?: string | null;
  optionTexts?: string[];
}

export interface ValuationRequest {
  vehicleId?: number;
  licensePlate?: string;
  manualVehicle?: ManualVehicleInput;
  askingPriceCents?: number;
}

/** An error the interface can act on: unknown plate, thin data, backend down. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }

  /** True when the backend could not be reached at all. */
  get isOffline(): boolean {
    return this.status === 0;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
      cache: "no-store",
    });
  } catch {
    throw new ApiError(
      "De lokale API is niet bereikbaar. Start de backend en probeer het opnieuw.",
      0,
    );
  }

  if (!response.ok) {
    throw new ApiError(await readErrorDetail(response), response.status);
  }

  return (await response.json()) as T;
}

async function readErrorDetail(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string") {
      return body.detail;
    }
    if (Array.isArray(body.detail)) {
      // FastAPI validation errors arrive as a list of field problems.
      return "De ingevoerde gegevens zijn niet geldig. Controleer de velden.";
    }
  } catch {
    // Fall through to the generic message below.
  }
  return `De aanvraag is mislukt (${response.status}).`;
}

export function createValuation(payload: ValuationRequest): Promise<Valuation> {
  return request<Valuation>("/valuations", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function fetchExamples(limit = 6): Promise<ExampleVehicle[]> {
  return request<ExampleVehicle[]>(`/market/examples?limit=${limit}`);
}

export function fetchOptions(): Promise<VehicleOption[]> {
  return request<VehicleOption[]>("/options");
}

export function createManualVehicle(payload: ManualVehicleInput): Promise<Vehicle> {
  return request<Vehicle>("/vehicles/manual", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function fetchValuation(valuationId: number): Promise<Valuation> {
  return request<Valuation>(`/valuations/${valuationId}`);
}

export interface AiAnswer {
  available: boolean;
  provider: string;
  model: string;
  answer: string | null;
  grounded: boolean;
  groundingNote: string | null;
  unavailableReason: string | null;
}

export interface AiSuggestions {
  available: boolean;
  provider: string;
  model: string;
  questions: string[];
}

export function askAboutValuation(valuationId: number, message: string): Promise<AiAnswer> {
  // Only the id and the question travel: the backend loads the stored valuation
  // and builds the AI context itself, so nothing here is authoritative.
  return request<AiAnswer>("/ai/chat", {
    method: "POST",
    body: JSON.stringify({ valuationId, message }),
  });
}

export function fetchAiSuggestions(valuationId: number): Promise<AiSuggestions> {
  return request<AiSuggestions>(`/ai/valuations/${valuationId}/suggestions`);
}
