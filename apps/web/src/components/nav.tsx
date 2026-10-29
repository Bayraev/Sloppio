"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

const links = [
  { href: "/", label: "Home" },
  { href: "/generate", label: "Generate" },
  { href: "/history", label: "History" },
  { href: "/budget", label: "Budget" },
  { href: "/settings", label: "Settings" },
];

export function Nav() {
  const pathname = usePathname();
  const [mode, setMode] = useState<string>("…");
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    let alive = true;
    const tick = () =>
      api
        .health()
        .then((h) => {
          if (alive) {
            setMode(h.provider_mode);
            setOffline(false);
          }
        })
        .catch(() => alive && setOffline(true));
    tick();
    const t = setInterval(tick, 10000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);

  return (
    <aside className="fixed inset-y-0 left-0 w-56 border-r p-4 flex flex-col gap-4 bg-[var(--panel)]">
      <div>
        <Link href="/" className="flex items-center gap-2 no-underline">
          <span className="inline-block w-3 h-3 rounded-full bg-gradient-to-br from-[var(--accent)] to-[var(--accent-2)]" />
          <span className="font-semibold tracking-tight text-[var(--text)]">AI Film Studio</span>
        </Link>
      </div>
      <nav className="flex flex-col gap-1">
        {links.map((l) => {
          const active = l.href === "/" ? pathname === "/" : pathname.startsWith(l.href);
          return (
            <Link
              key={l.href}
              href={l.href}
              className={`px-3 py-2 rounded-lg text-sm no-underline ${
                active ? "bg-[var(--panel-2)] text-[var(--text)] font-medium" : "text-[var(--muted)] hover:text-[var(--text)]"
              }`}
            >
              {l.label}
            </Link>
          );
        })}
      </nav>
      <div className="mt-auto">
        {offline ? (
          <span className="text-xs text-[var(--err)]">API OFFLINE</span>
        ) : mode === "mock" ? (
          <span className="text-xs px-2 py-1 rounded bg-[var(--warn)]/15 text-[var(--warn)] border border-[var(--warn)]/40" data-testid="mode-badge">
            MOCK MODE — simulated generations
          </span>
        ) : (
          <span className="text-xs px-2 py-1 rounded bg-[var(--ok)]/15 text-[var(--ok)] border border-[var(--ok)]/40" data-testid="mode-badge">
            LIVE — Seedance (paid)
          </span>
        )}
      </div>
    </aside>
  );
}
