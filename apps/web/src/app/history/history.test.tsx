import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { api, Generation } from "@/lib/api";

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({}),
  usePathname: () => "/history",
}));

import HistoryPage from "@/app/history/page";
import { Nav } from "@/components/nav";

const gen = (over: Partial<Generation> = {}): Generation => ({
  id: "gen_1",
  project_id: "prj_1",
  scene_id: null,
  model_id: "mock-seedance",
  provider: "mock",
  mode: "text_to_video",
  prompt: "lighthouse at dawn",
  ratio: "16:9",
  resolution: "720p",
  duration_seconds: 5,
  status: "completed",
  provider_task_id: "cgt-mock-1",
  error_code: null,
  error_message: null,
  cost_estimate_usd: 0.11,
  cost_actual_usd: 0.1056,
  output_asset_id: "out_1",
  created_at: "2026-10-28T10:00:00+00:00",
  updated_at: "2026-10-28T10:01:00+00:00",
  ...over,
});

describe("HistoryPage", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("renders generations with cost, model and MOCK labeling", async () => {
    vi.spyOn(api, "generations").mockResolvedValue({
      generations: [gen(), gen({ id: "gen_2", status: "failed", provider: "ark", prompt: "storm over harbor", cost_actual_usd: null, error_message: "moderation" })],
    });
    render(<HistoryPage />);
    await waitFor(() => expect(screen.getByTestId("history-list")).toBeTruthy());
    expect(screen.getByText("lighthouse at dawn")).toBeTruthy();
    expect(screen.getByTestId("status-completed")).toBeTruthy();
    expect(screen.getByTestId("status-failed")).toBeTruthy();
    expect(screen.getAllByText("MOCK").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Download").length).toBe(1);
  });

  it("shows the empty state when no generations match", async () => {
    vi.spyOn(api, "generations").mockResolvedValue({ generations: [] });
    render(<HistoryPage />);
    await waitFor(() => expect(screen.getByText(/No generations match/i)).toBeTruthy());
  });
});

describe("Nav mode badge", () => {
  it("clearly distinguishes mock mode", async () => {
    vi.spyOn(api, "health").mockResolvedValue({
      status: "ok",
      provider_mode: "mock",
      missing_settings: [],
    });
    vi.spyOn(api, "budget").mockResolvedValue({
      policy: { safety_margin: 0.1, note: "" },
      active_reservations: [],
      recent_charges: [],
      limits: { usd_24h: 7, usd_7d: 50 },
      spend_24h_usd: 0,
      spend_7d_usd: 0,
      reserved_usd: 0,
      remaining_24h_usd: 7,
      remaining_7d_usd: 50,
    });
    render(<Nav />);
    await waitFor(() => expect(screen.getByTestId("mode-badge").textContent).toMatch(/MOCK MODE/i));
  });
});
