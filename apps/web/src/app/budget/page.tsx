"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { BudgetBar } from "@/components/budget-bar";

type FullBudget = {
  limits: { usd_24h: number; usd_7d: number; approval_threshold_usd?: number };
  spend_24h_usd: number;
  spend_7d_usd: number;
  reserved_usd: number;
  remaining_24h_usd: number;
  remaining_7d_usd: number;
  policy: { safety_margin: number; note: string };
  active_reservations: { id: string; generation_id: string | null; amount_usd: number; created_at: string }[];
  recent_charges: { id: string; generation_id: string | null; amount_usd: number; created_at: string }[];
};

export default function BudgetPage() {
  const [b, setB] = useState<FullBudget | null>(null);
  useEffect(() => {
    const load = () => api.budget().then(setB).catch(() => {});
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, []);
  if (!b) return <p className="text-[var(--muted)]">Loading…</p>;
  return (
    <div className="space-y-6 max-w-4xl">
      <header>
        <h1 className="text-2xl font-semibold">Budget &amp; Usage</h1>
        <p className="text-[var(--muted)] text-sm">Application-side spending controls. Limits change only with your explicit approval.</p>
      </header>
      <BudgetBar />
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          ["Spent 24h", `$${b.spend_24h_usd.toFixed(4)}`],
          ["Spent 7d", `$${b.spend_7d_usd.toFixed(4)}`],
          ["Reserved (in flight)", `$${b.reserved_usd.toFixed(4)}`],
          ["Approval threshold", `$${(b.limits.approval_threshold_usd ?? 2).toFixed(2)}`],
        ].map(([label, value]) => (
          <div key={label} className="panel p-4">
            <div className="text-lg font-semibold tabular-nums">{value}</div>
            <div className="text-xs text-[var(--muted)]">{label.toUpperCase()}</div>
          </div>
        ))}
      </div>

      <section className="panel p-4">
        <h2 className="font-medium mb-2">Active reservations</h2>
        {b.active_reservations.length === 0 && <p className="text-sm text-[var(--muted)]">No outstanding reservations.</p>}
        <ul className="divide-y text-sm">
          {b.active_reservations.map((r) => (
            <li key={r.id} className="py-2 flex justify-between">
              <span className="font-mono text-xs">{r.generation_id ?? r.id}</span>
              <span className="text-[var(--warn)] tabular-nums">${r.amount_usd.toFixed(4)}</span>
            </li>
          ))}
        </ul>
      </section>

      <section className="panel p-4">
        <h2 className="font-medium mb-2">Recent charges</h2>
        {b.recent_charges.length === 0 && <p className="text-sm text-[var(--muted)]">No charges yet.</p>}
        <ul className="divide-y text-sm">
          {b.recent_charges.map((c) => (
            <li key={c.id} className="py-2 flex justify-between">
              <span className="text-[var(--muted)] text-xs">{new Date(c.created_at).toLocaleString()}</span>
              <span className="tabular-nums">${c.amount_usd.toFixed(4)}</span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
