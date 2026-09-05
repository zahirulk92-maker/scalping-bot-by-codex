interface StatusCardProps {
  label: string;
  value: string;
  hint?: string;
}

export function StatusCard({ label, value, hint }: StatusCardProps) {
  return (
    <article className="rounded-xl border border-slate-800 bg-slate-900/70 p-5 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">{label}</p>
      <p className="mt-3 text-2xl font-semibold tracking-tight text-slate-100">{value}</p>
      {hint ? <p className="mt-1 text-xs text-slate-500">{hint}</p> : null}
    </article>
  );
}
