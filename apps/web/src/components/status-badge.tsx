const COLORS: Record<string, string> = {
  completed: "var(--ok)",
  succeeded: "var(--ok)",
  failed: "var(--err)",
  needs_reconciliation: "var(--warn)",
  cancelled: "var(--muted)",
  expired: "var(--muted)",
  processing: "var(--accent)",
  running: "var(--accent)",
  queued: "var(--accent-2)",
  downloading: "var(--accent)",
  submitting: "var(--accent-2)",
  validating: "var(--accent-2)",
};

export function StatusBadge({ status }: { status: string }) {
  const color = COLORS[status] ?? "var(--muted)";
  return (
    <span
      data-testid={`status-${status}`}
      className="inline-flex items-center gap-1.5 text-xs font-medium px-2 py-0.5 rounded-full border"
      style={{ color, borderColor: color + "66", background: color + "14" }}
    >
      <span className="w-1.5 h-1.5 rounded-full" style={{ background: color }} />
      {status.replaceAll("_", " ")}
    </span>
  );
}

export function usd(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  return `$${n.toFixed(n < 1 ? 4 : 2)}`;
}
