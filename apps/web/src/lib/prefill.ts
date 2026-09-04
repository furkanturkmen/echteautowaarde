/**
 * Carrying a looked-up vehicle to the manual form.
 *
 * The register knows the car but not its mileage, uitvoering or transmission,
 * so a lookup lands on the manual form with the known fields already filled and
 * only the gaps left to complete. It travels in sessionStorage rather than the
 * URL: a plate is a vehicle identifier and does not belong in a query string,
 * and this keeps the address bar clean when the user goes back.
 *
 * It is read once and cleared, so a later visit to the form starts empty.
 */

import type { PlateDraft } from "@/lib/api";

const KEY = "eaw:plate-prefill";

export interface PlatePrefill {
  draft: PlateDraft;
  missingFields: string[];
  askingPrice: string;
}

export function storePrefill(prefill: PlatePrefill): void {
  try {
    sessionStorage.setItem(KEY, JSON.stringify(prefill));
  } catch {
    // A blocked storage costs the prefill, not the form: the user can still
    // type everything by hand.
  }
}

export function takePrefill(): PlatePrefill | null {
  try {
    const raw = sessionStorage.getItem(KEY);
    if (!raw) return null;
    sessionStorage.removeItem(KEY);
    return JSON.parse(raw) as PlatePrefill;
  } catch {
    return null;
  }
}
