export function Placeholder({ phase, children }: { phase: number; children: React.ReactNode }) {
  return (
    <div className="rounded-2xl border border-dashed border-border bg-card p-5 text-sm text-muted">
      <p className="mb-1 font-medium text-foreground">Coming in Phase {phase}</p>
      <p>{children}</p>
    </div>
  );
}
