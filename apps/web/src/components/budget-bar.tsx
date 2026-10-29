"use client";

import { useEffect, useState } from "react";
import { api, BudgetStatus } from "@/lib/api";

export function BudgetBar({ compact = false }: { compact?: boolean }) {
  const [budget, setBudget] = useState<BudgetStatus | null>(null);
  useEffect(() => {
    let alive = true;
    const load = () => api.budget().then((b) => alive && setBudget(b)).catch(() => {});
    load();
    const t = setInterval(load, 5000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);
  if (!budget) return null;
  const pct24 = Math.min(100, (budget.spend_24h_usd / budget.limits.usd_24h) * 100);
  return (
    <div className={compact ? "text-xs space-y-1" : "panel p-4 space-y-3"} data-testid="budget-bar">
      <div className="flex justify-between items-baseline">
        <span className="text-[var(--muted)] uppercase tracking-wide text-xs">Budget · 24h</span>
        <span className="tabular-nums">
          ${budget.spend_24h_usd.toFixed(2)} / ${budget.limits.usd_24h.toFixed(2)}
          {budget.reserved_usd > 0 && (
            <span className="text-[var(--warn)]"> (+${budget.reserved_usd.toFixed(2)} reserved)</span>
          )}
        </span>
      </div>
      <div className="h-2 rounded-full bg-[var(--panel-2)] overflow-hidden border border-[var(--line)]">
        <div
          className="h-full rounded-full transition-all"
          style={{
            width: `${pct24}%`,
            background: pct24 > 85 ? "var(--err)" : pct24 > 60 ? "var(--warn)" : "linear-gradient(90deg, var(--accent), var(--accent-2))",
          }}
        />
      </div>
      <div className="flex justify-between text-[var(--muted)] text-xs">
        <span>7-day: ${budget.spend_7d_usd.toFixed(2)} / ${budget.limits.usd_7d.toFixed(2)}</span>
        <span>remaining today: ${budget.remaining_24h_usd.toFixed(2)}</span>
      </div>
    </div>
  );
}
