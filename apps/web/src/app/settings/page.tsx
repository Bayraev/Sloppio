"use client";

import { useEffect, useState } from "react";
import { api, Capabilities } from "@/lib/api";

export default function SettingsPage() {
  const [caps, setCaps] = useState<Capabilities | null>(null);
  const [missing, setMissing] = useState<string[]>([]);
  useEffect(() => {
    api.capabilities().then(setCaps).catch(() => {});
    api.health().then((h) => setMissing(h.missing_settings)).catch(() => {});
  }, []);
  return (
    <div className="space-y-6 max-w-3xl">
      <header>
        <h1 className="text-2xl font-semibold">Settings</h1>
        <p className="text-[var(--muted)] text-sm">Configuration lives in <code>.env</code> at the repository root. The API key never reaches this page or the browser.</p>
      </header>

      <section className="panel p-4 space-y-2">
        <h2 className="font-medium">Provider</h2>
        <p>
          Mode:{" "}
          <strong className={caps?.provider_mode === "mock" ? "text-[var(--warn)]" : "text-[var(--ok)]"}>
            {caps?.provider_mode ?? "…"}
          </strong>
        </p>
        {caps?.provider_mode === "mock" && (
          <p className="text-sm text-[var(--muted)]">
            Mock mode is active. To generate with real Seedance models: fill <code>ARK_API_KEY</code> and
            <code> ARK_MODEL_ID</code> in <code>.env</code>, then set <code>USE_MOCK_PROVIDER=false</code> and restart the backend.
          </p>
        )}
        {missing.length > 0 && <p className="text-sm text-[var(--err)]">Missing settings: {missing.join(", ")}</p>}
      </section>

      <section className="panel p-4 space-y-2">
        <h2 className="font-medium">Model registry (verified configuration)</h2>
        <p className="text-sm text-[var(--muted)]">
          Models come from <code>data/config/models.json</code> with pricing verified against the official BytePlus pricing page.
          A model is marked <em>account-verified</em> after the first successful generation. Unknown or unverified model ids are rejected.
        </p>
        <ul className="divide-y text-sm">
          {caps?.models.map((m) => (
            <li key={m.id} className="py-2 flex items-center gap-2">
              <span className="font-mono text-xs">{m.id}</span>
              {m.account_verified ? (
                <span className="text-xs text-[var(--ok)]">account-verified</span>
              ) : m.provider === "mock" ? (
                <span className="text-xs text-[var(--warn)]">mock</span>
              ) : (
                <span className="text-xs text-[var(--muted)]">not yet verified for this account</span>
              )}
              <span className="ml-auto text-xs text-[var(--muted)]">
                {m.resolutions.join(", ")} · {m.durations.map((d) => `${d}s`).join(", ")}
              </span>
            </li>
          ))}
        </ul>
      </section>

      <section className="panel p-4 space-y-1">
        <h2 className="font-medium">Spending policy</h2>
        <p className="text-sm text-[var(--muted)]">
          Limits: ${caps?.budget.limits.usd_24h ?? 7} / rolling 24h and ${caps?.budget.limits.usd_7d ?? 50} / rolling 7d.
          Enforced by the central budget service before every paid request. Reservations survive restarts; unknown cost fails closed.
          There is intentionally no UI and no API to raise limits — edit <code>.env</code> deliberately and restart.
        </p>
      </section>
    </div>
  );
}
