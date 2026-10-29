export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000/api/v1";

export type Project = {
  id: string;
  slug: string;
  title: string;
  description: string;
  status: string;
  scene_count: number;
  generation_count: number;
  created_at: string;
  updated_at: string;
};

export type ModelInfo = {
  id: string;
  display_name: string;
  provider: string;
  modes: string[];
  resolutions: string[];
  ratios: string[];
  durations: number[];
  max_reference_images: number;
  supports_audio: boolean;
  verified: boolean;
  account_verified: boolean;
  pricing: { per_second_usd: Record<string, number> };
};

export type Capabilities = {
  provider_mode: "mock" | "seedance";
  models: ModelInfo[];
  upload: { max_size_mb: number; allowed_mime: string[]; min_side: number; max_side: number };
  budget: BudgetStatus;
};

export type BudgetReservation = { id: string; generation_id: string | null; amount_usd: number; created_at: string };
export type BudgetCharge = { id: string; generation_id: string | null; amount_usd: number; created_at: string };

export type BudgetStatus = {
  limits: { usd_24h: number; usd_7d: number; approval_threshold_usd?: number };
  spend_24h_usd: number;
  spend_7d_usd: number;
  reserved_usd: number;
  remaining_24h_usd: number;
  remaining_7d_usd: number;
};

export type Generation = {
  id: string;
  project_id: string;
  scene_id: string | null;
  model_id: string;
  provider: string;
  mode: string;
  prompt: string;
  ratio: string;
  resolution: string;
  duration_seconds: number;
  status: string;
  provider_task_id: string | null;
  error_code: string | null;
  error_message: string | null;
  cost_estimate_usd: number;
  cost_actual_usd: number | null;
  output_asset_id: string | null;
  created_at: string;
  updated_at: string;
};

export type ReferenceAsset = {
  id: string;
  role: string;
  entity_id: string;
  filename: string;
  original_filename: string;
  mime_type: string;
  size_bytes: number;
  width: number;
  height: number;
  created_at: string;
};

export type ApiError = { code?: string; message: string };

export class ApiRequestError extends Error {
  code: string;
  constructor(err: ApiError) {
    super(err.message);
    this.code = err.code ?? "error";
  }
}

async function handle<T>(resp: Response): Promise<T> {
  if (!resp.ok) {
    let detail: ApiError = { message: `HTTP ${resp.status}` };
    try {
      const body = await resp.json();
      if (typeof body?.detail === "string") detail = { message: body.detail };
      else if (body?.detail) detail = body.detail;
    } catch {
      /* non-JSON error */
    }
    throw new ApiRequestError(detail);
  }
  return resp.json() as Promise<T>;
}

export const api = {
  health: () => fetch(`${API_BASE}/health`).then((r) => handle<{ status: string; provider_mode: string; missing_settings: string[] }>(r)),
  capabilities: () => fetch(`${API_BASE}/capabilities`).then((r) => handle<Capabilities>(r)),
  listProjects: () => fetch(`${API_BASE}/projects`).then((r) => handle<{ projects: Project[] }>(r)),
  createProject: (title: string, description: string) =>
    fetch(`${API_BASE}/projects`, { method: "POST", body: new URLSearchParams({ title, description }) }).then((r) => handle<Project>(r)),
  project: (id: string) => fetch(`${API_BASE}/projects/${id}`).then((r) => handle<Project>(r)),
  bibleDocs: (pid: string) => fetch(`${API_BASE}/projects/${pid}/bible`).then((r) => handle<{ docs: { name: string; canonical: boolean; size_bytes: number }[] }>(r)),
  readBibleDoc: (pid: string, name: string) =>
    fetch(`${API_BASE}/projects/${pid}/bible/${name}`).then((r) => handle<{ name: string; content: string }>(r)),
  writeBibleDoc: (pid: string, name: string, content: string) =>
    fetch(`${API_BASE}/projects/${pid}/bible/${name}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content }),
    }).then((r) => handle<{ saved: boolean }>(r)),
  scenes: (pid: string) => fetch(`${API_BASE}/projects/${pid}/scenes`).then((r) => handle<{ scenes: { id: string; title: string; summary: string; status: string }[] }>(r)),
  createScene: (pid: string, title: string, summary: string) =>
    fetch(`${API_BASE}/projects/${pid}/scenes`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title, summary }),
    }).then((r) => handle<{ id: string }>(r)),
  references: (pid: string) => fetch(`${API_BASE}/projects/${pid}/references`).then((r) => handle<{ references: ReferenceAsset[] }>(r)),
  uploadReference: (pid: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return fetch(`${API_BASE}/projects/${pid}/references`, { method: "POST", body: form }).then((r) => handle<ReferenceAsset>(r));
  },
  generations: (params: Record<string, string> = {}) => {
    const qs = new URLSearchParams(params).toString();
    return fetch(`${API_BASE}/generations${qs ? `?${qs}` : ""}`).then((r) => handle<{ generations: Generation[] }>(r));
  },
  generation: (id: string) => fetch(`${API_BASE}/generations/${id}`).then((r) => handle<Generation>(r)),
  createGeneration: (body: Record<string, unknown>) =>
    fetch(`${API_BASE}/generations`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then((r) => handle<Generation>(r)),
  retryGeneration: (id: string) => fetch(`${API_BASE}/generations/${id}/retry`, { method: "POST" }).then((r) => handle<Generation>(r)),
  cancelGeneration: (id: string) => fetch(`${API_BASE}/generations/${id}/cancel`, { method: "POST" }).then((r) => handle<Generation>(r)),
  deleteGeneration: (id: string) => fetch(`${API_BASE}/generations/${id}`, { method: "DELETE" }).then((r) => handle<{ deleted: string }>(r)),
  budget: () =>
    fetch(`${API_BASE}/budget`).then((r) =>
      handle<BudgetStatus & { policy: { safety_margin: number; note: string }; active_reservations: BudgetReservation[]; recent_charges: BudgetCharge[] }>(r)
    ),
  videoUrl: (id: string) => `${API_BASE}/generations/${id}/video`,
  referenceFileUrl: (id: string) => `${API_BASE}/projects/references/${id}/file`,
};
