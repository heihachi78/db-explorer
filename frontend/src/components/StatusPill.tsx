interface StatusPillProps {
  ok: boolean;
  children: React.ReactNode;
}

export function StatusPill({ ok, children }: StatusPillProps) {
  return <span className={`status-pill ${ok ? "status-pill--ok" : "status-pill--muted"}`}>{children}</span>;
}
