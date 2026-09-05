interface UnavailablePanelProps { title: string; }

export function UnavailablePanel({ title }: UnavailablePanelProps) {
  return (
    <section className="min-h-36 rounded-xl border border-dashed border-slate-700 bg-slate-900/40 p-5">
      <h2 className="text-sm font-semibold text-slate-300">{title}</h2>
      <p className="mt-6 text-sm text-amber-300">Waiting for Market Data</p>
      <p className="mt-1 text-xs text-slate-500">Available in a future phase.</p>
    </section>
  );
}
