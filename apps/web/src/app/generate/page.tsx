"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { api, ApiRequestError, Capabilities, Generation, ModelInfo, Project, ReferenceAsset } from "@/lib/api";

const MODE_LABELS: Record<string, string> = {
  text_to_video: "Text → Video",
  image_to_video: "Image → Video (first frame)",
  first_last_frame: "First + Last frame",
  reference_to_video: "Reference images (omni)",
};

function GenerateWorkspace() {
  const search = useSearchParams();
  const [caps, setCaps] = useState<Capabilities | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState(search.get("project") ?? "");
  const [scenes, setScenes] = useState<{ id: string; title: string }[]>([]);
  const [sceneId, setSceneId] = useState("");
  const [modelId, setModelId] = useState("");
  const [mode, setMode] = useState("text_to_video");
  const [ratio, setRatio] = useState("16:9");
  const [resolution, setResolution] = useState("720p");
  const [duration, setDuration] = useState(5);
  const [audio, setAudio] = useState(false);
  const [prompt, setPrompt] = useState("");
  const [refs, setRefs] = useState<ReferenceAsset[]>([]);
  const [bibleDocs, setBibleDocs] = useState<string[]>([]);
  const [availableDocs, setAvailableDocs] = useState<{ name: string }[]>([]);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [needsApproval, setNeedsApproval] = useState(false);
  const [busy, setBusy] = useState(false);
  const [created, setCreated] = useState<Generation | null>(null);

  useEffect(() => {
    api.capabilities().then((c) => {
      setCaps(c);
      const first = c.models.find((m) => m.provider === "mock") ?? c.models[0];
      if (first) {
        setModelId(first.id);
        setResolution(first.resolutions[0]);
      }
    }).catch((e) => setError(e.message));
    api.listProjects().then((r) => {
      setProjects(r.projects);
      if (!projectId && r.projects.length) setProjectId(r.projects[0].id);
    }).catch(() => {});
  }, []);

  const model: ModelInfo | undefined = useMemo(
    () => caps?.models.find((m) => m.id === modelId),
    [caps, modelId]
  );

  useEffect(() => {
    if (!projectId) return;
    api.scenes(projectId).then((r) => setScenes(r.scenes.map((s) => ({ id: s.id, title: s.title })))).catch(() => {});
    api.references(projectId).then((r) => setRefs(r.references)).catch(() => {});
    api.bibleDocs(projectId).then((r) => setAvailableDocs(r.docs.filter((d) => d.name !== "changelog.md"))).catch(() => {});
  }, [projectId]);

  useEffect(() => {
    if (model) {
      if (!model.ratios.includes(ratio)) setRatio(model.ratios[0]);
      if (!model.resolutions.includes(resolution)) setResolution(model.resolutions[0]);
      if (!model.durations.includes(duration)) setDuration(model.durations[0]);
      if (audio && !model.supports_audio) setAudio(false);
    }
  }, [model]);

  const estimate = useMemo(() => {
    if (!model) return null;
    const perSec = model.pricing.per_second_usd[resolution];
    if (!perSec) return null;
    return perSec * duration;
  }, [model, resolution, duration]);

  const remaining = caps?.budget.remaining_24h_usd ?? 0;
  const blocked = estimate !== null && estimate > remaining;

  async function upload(file: File) {
    if (!projectId) return;
    setUploadError(null);
    try {
      const asset = await api.uploadReference(projectId, file);
      setRefs((r) => [asset, ...r]);
    } catch (e) {
      setUploadError(e instanceof ApiRequestError ? e.message : String(e));
    }
  }

  async function generate(approved = false) {
    setError(null);
    setNeedsApproval(false);
    setBusy(true);
    try {
      const gen = await api.createGeneration({
        project_id: projectId,
        scene_id: sceneId || null,
        model_id: modelId,
        mode,
        prompt,
        ratio,
        resolution,
        duration_seconds: duration,
        generate_audio: audio,
        reference_asset_ids: refs.map((r) => r.id).slice(0, requiredImages(mode) === "range" ? 9 : requiredImages(mode) === "one" ? 1 : 2),
        bible_docs: bibleDocs,
        user_approved: approved,
      });
      setCreated(gen);
    } catch (e) {
      if (e instanceof ApiRequestError) {
        if (e.code === "approval_required") setNeedsApproval(true);
        setError(e.message);
      } else setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6 max-w-5xl">
      <header>
        <h1 className="text-2xl font-semibold">Generate Video</h1>
        <p className="text-[var(--muted)] text-sm">
          {caps?.provider_mode === "mock"
            ? "Mock mode — generations are simulated, never billed."
            : "LIVE mode — every generation is a paid BytePlus ModelArk request."}
        </p>
      </header>

      {error && (
        <div className="panel border-[var(--err)]/50 p-3 text-sm text-[var(--err)]" role="alert" data-testid="generate-error">
          {error}
        </div>
      )}
      {created && (
        <div className="panel p-3 text-sm border-[var(--ok)]/40 text-[var(--ok)]" data-testid="generate-created">
          Generation {created.id} submitted ({created.status}). Track it in <a className="underline" href={`/history?project=${created.project_id}`}>History</a>.
        </div>
      )}

      <div className="grid lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 space-y-4">
          <div className="panel p-4 space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="label" htmlFor="project">Project</label>
                <select id="project" className="select" value={projectId} onChange={(e) => { setProjectId(e.target.value); setSceneId(""); }}>
                  <option value="">— select project —</option>
                  {projects.map((p) => <option key={p.id} value={p.id}>{p.title}</option>)}
                </select>
              </div>
              <div>
                <label className="label" htmlFor="scene">Scene (optional)</label>
                <select id="scene" className="select" value={sceneId} onChange={(e) => setSceneId(e.target.value)}>
                  <option value="">— none —</option>
                  {scenes.map((s) => <option key={s.id} value={s.id}>{s.title}</option>)}
                </select>
              </div>
            </div>
            <div>
              <label className="label" htmlFor="prompt">Prompt</label>
              <textarea
                id="prompt"
                className="textarea min-h-36"
                placeholder="Describe the shot. Use @Image1 to refer to the first attached reference…"
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                maxLength={8000}
              />
            </div>
          </div>

          <div className="panel p-4 space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="font-medium text-sm">Reference images</h2>
              <label className="btn cursor-pointer">
                Upload…
                <input
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  className="hidden"
                  onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])}
                />
              </label>
            </div>
            {uploadError && <p className="text-xs text-[var(--err)]">{uploadError}</p>}
            <div className="flex flex-wrap gap-2" data-testid="reference-list">
              {refs.map((r) => (
                <div key={r.id} className="w-24 group relative">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={api.referenceFileUrl(r.id)} alt={r.original_filename} className="w-24 h-16 object-cover rounded-md border" />
                  <button
                    className="absolute top-1 right-1 hidden group-hover:block bg-black/70 text-white text-xs rounded px-1"
                    onClick={() => setRefs((list) => list.filter((x) => x.id !== r.id))}
                    aria-label={`Remove ${r.original_filename}`}
                  >
                    ✕
                  </button>
                  <p className="text-[10px] text-[var(--muted)] truncate mt-1">{r.original_filename}</p>
                </div>
              ))}
              {refs.length === 0 && <p className="text-xs text-[var(--muted)]">No references attached. Upload or pick from the project library.</p>}
            </div>
          </div>

          <div className="panel p-4 space-y-2">
            <h2 className="font-medium text-sm">Bible context (selected docs only)</h2>
            <div className="flex flex-wrap gap-2">
              {availableDocs.map((d) => {
                const on = bibleDocs.includes(d.name);
                return (
                  <button
                    key={d.name}
                    className={`text-xs px-2 py-1 rounded-full border ${on ? "border-[var(--accent)] text-[var(--accent)]" : "text-[var(--muted)]"}`}
                    onClick={() => setBibleDocs((docs) => (on ? docs.filter((x) => x !== d.name) : [...docs, d.name]))}
                  >
                    {d.name}
                  </button>
                );
              })}
              {availableDocs.length === 0 && <p className="text-xs text-[var(--muted)]">Select a project to choose bible context.</p>}
            </div>
          </div>
        </div>

        <div className="space-y-4">
          <div className="panel p-4 space-y-3">
            <div>
              <label className="label" htmlFor="model">Model</label>
              <select id="model" className="select" value={modelId} onChange={(e) => setModelId(e.target.value)}>
                {caps?.models.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.display_name}{m.account_verified ? " ✓" : ""}
                  </option>
                ))}
              </select>
              {model && !model.account_verified && (
                <p className="text-[10px] text-[var(--warn)] mt-1">Unverified for this account until a successful generation.</p>
              )}
            </div>
            <div>
              <label className="label" htmlFor="mode">Mode</label>
              <select id="mode" className="select" value={mode} onChange={(e) => setMode(e.target.value)}>
                {(model?.modes ?? []).map((m) => <option key={m} value={m}>{MODE_LABELS[m] ?? m}</option>)}
              </select>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="label" htmlFor="ratio">Ratio</label>
                {mode === "image_to_video" || mode === "first_last_frame" ? (
                  <select className="select" disabled value="">
                    <option>follows first-frame image</option>
                  </select>
                ) : (
                  <select id="ratio" className="select" value={ratio} onChange={(e) => setRatio(e.target.value)}>
                    {(model?.ratios ?? []).map((r) => <option key={r}>{r}</option>)}
                  </select>
                )}
              </div>
              <div>
                <label className="label" htmlFor="res">Resolution</label>
                <select id="res" className="select" value={resolution} onChange={(e) => setResolution(e.target.value)}>
                  {(model?.resolutions ?? []).map((r) => <option key={r}>{r}</option>)}
                </select>
              </div>
              <div>
                <label className="label" htmlFor="dur">Duration</label>
                <select id="dur" className="select" value={duration} onChange={(e) => setDuration(Number(e.target.value))}>
                  {(model?.durations ?? []).map((d) => <option key={d} value={d}>{d}s</option>)}
                </select>
              </div>
              <div>
                <label className="label" htmlFor="audio">Audio</label>
                <select id="audio" className="select" value={audio ? "on" : "off"} onChange={(e) => setAudio(e.target.value === "on")} disabled={!model?.supports_audio}>
                  <option value="off">Off</option>
                  <option value="on" disabled={!model?.supports_audio}>On</option>
                </select>
              </div>
            </div>
          </div>

          <div className="panel p-4 space-y-2 text-sm" data-testid="cost-panel">
            <div className="flex justify-between">
              <span className="text-[var(--muted)]">Estimated cost</span>
              <span className="tabular-nums font-medium">{estimate === null ? "unknown" : `$${estimate.toFixed(4)}`}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-[var(--muted)]">Remaining today</span>
              <span className="tabular-nums">${(caps?.budget.remaining_24h_usd ?? 0).toFixed(2)}</span>
            </div>
            {caps?.provider_mode === "seedance" && (
              <p className="text-xs text-[var(--warn)]">This will incur a real paid charge at BytePlus.</p>
            )}
            <button
              className="btn btn-primary w-full justify-center"
              disabled={busy || !projectId || !prompt.trim() || blocked}
              onClick={() => generate(false)}
              data-testid="generate-button"
            >
              {busy ? "Submitting…" : "Generate"}
            </button>
            {blocked && (
              <p className="text-xs text-[var(--err)]" data-testid="budget-blocked">
                Estimate exceeds today&apos;s remaining budget — generation blocked by the budget manager.
              </p>
            )}
            {needsApproval && (
              <div className="space-y-2">
                <p className="text-xs text-[var(--warn)]">This operation exceeds the per-operation approval threshold.</p>
                <button className="btn w-full justify-center" onClick={() => generate(true)} data-testid="approve-button">
                  Approve and generate
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function requiredImages(mode: string): "zero" | "one" | "two" | "range" {
  if (mode === "text_to_video") return "zero";
  if (mode === "image_to_video") return "one";
  if (mode === "first_last_frame") return "two";
  return "range";
}

export default function GeneratePage() {
  return (
    <Suspense fallback={<p className="text-[var(--muted)]">Loading workspace…</p>}>
      <GenerateWorkspace />
    </Suspense>
  );
}
