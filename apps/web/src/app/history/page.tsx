"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { api, Generation } from "@/lib/api";
import { StatusBadge, usd } from "@/components/status-badge";

function HistoryInner() {
  const search = useSearchParams();
  const [gens, setGens] = useState<Generation[]>([]);
  const [projectFilter, setProjectFilter] = useState(search.get("project") ?? "");
  const [statusFilter, setStatusFilter] = useState("");
  const [modelFilter, setModelFilter] = useState("");
  const [detail, setDetail] = useState<Generation | null>(null);
  const [poll, setPoll] = useState(0);

  useEffect(() => {
    const params: Record<string, string> = { limit: "50" };
    if (projectFilter) params.project_id = projectFilter;
    if (statusFilter) params.status = statusFilter;
    if (modelFilter) params.model_id = modelFilter;
    api.generations(params).then((r) => setGens(r.generations)).catch(() => {});
  }, [projectFilter, statusFilter, modelFilter, poll]);

  const hasActive = gens.some((g) => ["submitting", "queued", "processing", "downloading"].includes(g.status));
  useEffect(() => {
    if (!hasActive) return;
    const t = setInterval(() => setPoll((p) => p + 1), 2000);
    return () => clearInterval(t);
  }, [hasActive]);

  async function cancel(id: string) {
    try {
      await api.cancelGeneration(id);
      setPoll((p) => p + 1);
    } catch (e) {
      alert((e as Error).message);
    }
  }
  async function retry(id: string) {
    try {
      const g = await api.retryGeneration(id);
      setDetail(g);
      setPoll((p) => p + 1);
    } catch (e) {
      alert((e as Error).message);
    }
  }
  async function remove(id: string) {
    if (!confirm(`Delete generation ${id} and its output file? This cannot be undone.`)) return;
    try {
      await api.deleteGeneration(id);
      setDetail(null);
      setPoll((p) => p + 1);
    } catch (e) {
      alert((e as Error).message);
    }
  }

  return (
    <div className="space-y-4">
      <header className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Generation History</h1>
          <p className="text-[var(--muted)] text-sm">Every request with prompt, model, cost, and provider task id.</p>
        </div>
      </header>

      <div className="flex gap-3 flex-wrap">
        <input className="input max-w-64" placeholder="Filter by project id" value={projectFilter} onChange={(e) => setProjectFilter(e.target.value)} />
        <select className="select max-w-48" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="">All statuses</option>
          {["completed", "failed", "cancelled", "needs_reconciliation", "processing", "queued", "submitting"].map((s) => <option key={s}>{s}</option>)}
        </select>
        <input className="input max-w-64" placeholder="Filter by model id" value={modelFilter} onChange={(e) => setModelFilter(e.target.value)} />
      </div>

      <div className="panel divide-y" data-testid="history-list">
        {gens.length === 0 && <p className="p-6 text-center text-[var(--muted)] text-sm">No generations match.</p>}
        {gens.map((g) => (
          <div key={g.id} className="p-3 flex items-center gap-3 text-sm">
            {g.status === "completed" ? (
              <video className="w-24 h-14 rounded object-cover border bg-black" src={api.videoUrl(g.id)} muted preload="metadata" />
            ) : (
              <div className="w-24 h-14 rounded border bg-[var(--panel-2)] flex items-center justify-center text-[var(--muted)] text-xs">
                {g.provider === "mock" ? "MOCK" : "—"}
              </div>
            )}
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <StatusBadge status={g.status} />
                <span className="text-[var(--muted)] text-xs">{new Date(g.created_at).toLocaleString()}</span>
                {g.provider === "mock" && <span className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--warn)]/15 text-[var(--warn)] border border-[var(--warn)]/40">MOCK</span>}
              </div>
              <p className="truncate mt-1">{g.prompt}</p>
              <p className="text-xs text-[var(--muted)] truncate">{g.model_id} · {g.resolution} · {g.ratio} · {g.duration_seconds}s {g.provider_task_id ? `· ${g.provider_task_id}` : ""}</p>
            </div>
            <div className="text-right shrink-0 space-y-1">
              <div className="tabular-nums">{usd(g.cost_actual_usd ?? g.cost_estimate_usd)}{g.cost_actual_usd === null && <span className="text-[var(--muted)] text-xs"> est</span>}</div>
              <div className="flex gap-1">
                <button className="btn text-xs px-2 py-1" onClick={() => api.generation(g.id).then(setDetail)}>Details</button>
                {g.status === "completed" && <a className="btn text-xs px-2 py-1" href={api.videoUrl(g.id)} download>Download</a>}
                {["submitting", "queued", "processing", "downloading"].includes(g.status) && <button className="btn text-xs px-2 py-1" onClick={() => cancel(g.id)}>Cancel</button>}
              </div>
            </div>
          </div>
        ))}
      </div>

      {detail && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center p-8" onClick={() => setDetail(null)}>
          <div className="panel bg-[var(--panel)] p-5 max-w-2xl w-full max-h-[80vh] overflow-auto space-y-3" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center gap-2">
              <h2 className="font-semibold">Generation {detail.id}</h2>
              <StatusBadge status={detail.status} />
              <button className="btn ml-auto text-xs" onClick={() => setDetail(null)}>Close</button>
            </div>
            {detail.status === "completed" && <video className="w-full rounded border bg-black" src={api.videoUrl(detail.id)} controls />}
            <dl className="grid grid-cols-2 gap-2 text-sm">
              <dt className="text-[var(--muted)]">Model</dt><dd>{detail.model_id}</dd>
              <dt className="text-[var(--muted)]">Mode</dt><dd>{detail.mode}</dd>
              <dt className="text-[var(--muted)]">Provider task</dt><dd className="font-mono text-xs">{detail.provider_task_id ?? "—"}</dd>
              <dt className="text-[var(--muted)]">Cost estimate / actual</dt><dd>{usd(detail.cost_estimate_usd)} / {usd(detail.cost_actual_usd)}</dd>
              <dt className="text-[var(--muted)]">Ratio / resolution / duration</dt><dd>{detail.ratio} / {detail.resolution} / {detail.duration_seconds}s</dd>
              {detail.error_code && <><dt className="text-[var(--muted)]">Error</dt><dd className="text-[var(--err)]">{detail.error_code}: {detail.error_message}</dd></>}
            </dl>
            <div>
              <p className="label">Prompt</p>
              <p className="text-sm whitespace-pre-wrap">{detail.prompt}</p>
            </div>
            <div className="flex gap-2">
              {["failed", "cancelled", "needs_reconciliation"].includes(detail.status) && <button className="btn" onClick={() => retry(detail.id)}>Retry as new</button>}
              <button className="btn btn-danger" onClick={() => remove(detail.id)}>Delete…</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function HistoryPage() {
  return (
    <Suspense>
      <HistoryInner />
    </Suspense>
  );
}
