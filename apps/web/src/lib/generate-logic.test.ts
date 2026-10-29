import { describe, expect, it } from "vitest";
import { decideGenerate, estimateCost } from "@/lib/generate-logic";
import type { ModelInfo } from "@/lib/api";

const model: ModelInfo = {
  id: "mock-seedance",
  display_name: "Mock",
  provider: "mock",
  modes: ["text_to_video"],
  resolutions: ["480p", "720p", "1080p"],
  ratios: ["16:9"],
  durations: [5, 10],
  max_reference_images: 9,
  supports_audio: true,
  verified: true,
  account_verified: false,
  pricing: { per_second_usd: { "480p": 0.01, "720p": 0.02, "1080p": 0.04 } },
};

describe("estimateCost", () => {
  it("multiplies per-second price by duration", () => {
    expect(estimateCost(model, "720p", 10)).toBeCloseTo(0.2);
  });
  it("fails closed on unknown resolution (never free)", () => {
    expect(estimateCost(model, "4k", 5)).toBeNull();
  });
  it("fails closed on missing model", () => {
    expect(estimateCost(undefined, "720p", 5)).toBeNull();
  });
});

describe("decideGenerate", () => {
  it("blocks when the estimate exceeds remaining budget", () => {
    const d = decideGenerate(model, "1080p", 10, 0.30);
    expect(d.blocked).toBe(true);
    expect(d.blockedReason).toBe("budget");
    expect(d.estimate).toBeCloseTo(0.4);
  });
  it("allows when within budget", () => {
    const d = decideGenerate(model, "1080p", 10, 0.50);
    expect(d.blocked).toBe(false);
  });
  it("blocks on unknown cost regardless of budget", () => {
    const d = decideGenerate(model, "4k", 5, 1000);
    expect(d.blocked).toBe(true);
    expect(d.blockedReason).toBe("unknown_cost");
  });
});
