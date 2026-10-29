"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, Project } from "@/lib/api";
import { BudgetBar } from "@/components/budget-bar";

export default function HomePage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = () => api.listProjects().then((r) => setProjects(r.projects)).catch((e) => setError(String(e.message)));
  useEffect(() => {
    load();
  }, []);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await api.createProject(title.trim(), description.trim());
      setTitle("");
      setDescription("");
      await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <header className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Film Projects</h1>
          <p className="text-[var(--muted)] text-sm">Your local production workspace — projects, bibles, and generated shots.</p>
        </div>
        <BudgetBar compact />
      </header>

      <form onSubmit={create} className="panel p-4 flex flex-wrap gap-3 items-end" data-testid="create-project">
        <div className="flex-1 min-w-60">
          <label className="label" htmlFor="title">New film title</label>
          <input id="title" className="input" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Blue Horizon" maxLength={120} />
        </div>
        <div className="flex-1 min-w-60">
          <label className="label" htmlFor="desc">Description (optional)</label>
          <input id="desc" className="input" value={description} onChange={(e) => setDescription(e.target.value)} placeholder="logline or notes" />
        </div>
        <button className="btn btn-primary" disabled={busy || !title.trim()} type="submit">
          {busy ? "Creating…" : "Create project"}
        </button>
      </form>
      {error && <p className="text-[var(--err)] text-sm" role="alert">{error}</p>}

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {projects.map((p) => (
          <Link key={p.id} href={`/projects/${p.id}`} className="panel p-4 block no-underline hover:border-[var(--accent)] transition-colors">
            <h2 className="font-semibold text-lg text-[var(--text)]">{p.title}</h2>
            <p className="text-sm text-[var(--muted)] line-clamp-2 min-h-10">{p.description || "No description"}</p>
            <div className="mt-3 flex gap-4 text-xs text-[var(--muted)]">
              <span>{p.scene_count} scenes</span>
              <span>{p.generation_count} generations</span>
              <span className="ml-auto uppercase">{p.status}</span>
            </div>
          </Link>
        ))}
        {projects.length === 0 && (
          <div className="panel p-8 text-center text-[var(--muted)] md:col-span-2 lg:col-span-3">
            No projects yet — create your first film above. Every project gets a full film bible.
          </div>
        )}
      </div>
    </div>
  );
}
