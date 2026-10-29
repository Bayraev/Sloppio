import type { ModelInfo } from "@/lib/api";

export function estimateCost(
  model: ModelInfo | undefined,
  resolution: string,
  durationSeconds: number
): number | null {
  if (!model) return null;
  const perSec = model.pricing.per_second_usd[resolution];
  if (!perSec || perSec <= 0) return null; // unknown cost — never treat as free
  return perSec * durationSeconds;
}

export type GenerateDecision = {
  estimate: number | null;
  blocked: boolean;
  blockedReason: "no_model" | "unknown_cost" | "budget" | null;
};

export function decideGenerate(
  model: ModelInfo | undefined,
  resolution: string,
  durationSeconds: number,
  remainingBudgetUsd: number
): GenerateDecision {
  if (!model) return { estimate: null, blocked: true, blockedReason: "no_model" };
  const estimate = estimateCost(model, resolution, durationSeconds);
  if (estimate === null) return { estimate: null, blocked: true, blockedReason: "unknown_cost" };
  if (estimate > remainingBudgetUsd) {
    return { estimate, blocked: true, blockedReason: "budget" };
  }
  return { estimate, blocked: false, blockedReason: null };
}
