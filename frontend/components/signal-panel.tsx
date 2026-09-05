import type { SignalSnapshot } from "@/types/bot";

const directionStyles = {
  long: "border-emerald-400/40 bg-emerald-400/10 text-emerald-300",
  short: "border-rose-400/40 bg-rose-400/10 text-rose-300",
  no_trade: "border-slate-600 bg-slate-800/70 text-slate-300",
} as const;

export function SignalPanel({ signal }: { signal: SignalSnapshot | undefined }) {
  if (!signal || !signal.candle_open_time) {
    return <section className="rounded-xl border border-dashed border-slate-700 bg-slate-900/40 p-5"><h2 className="font-semibold">Signal</h2><p className="mt-4 text-sm text-amber-300">Waiting for a closed-candle strategy evaluation</p><p className="mt-1 text-xs text-slate-500">SIGNAL ONLY — EXECUTION DISABLED</p></section>;
  }
  const direction = signal.direction.replace("_", " ").toUpperCase();
  return <section className="rounded-xl border border-slate-800 bg-slate-900/70 p-5"><div className="flex items-center justify-between gap-3"><h2 className="font-semibold">Signal</h2><span className={`rounded-full border px-2.5 py-1 text-xs font-bold tracking-wide ${directionStyles[signal.direction]}`}>{direction}</span></div><p className="mt-2 text-xs font-bold tracking-[0.12em] text-amber-300">SIGNAL ONLY — EXECUTION DISABLED</p><dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-3 text-sm"><div><dt className="text-xs uppercase tracking-wide text-slate-500">Score</dt><dd className="mt-1 font-medium">{signal.score}/100</dd></div><div><dt className="text-xs uppercase tracking-wide text-slate-500">Confidence</dt><dd className="mt-1 font-medium">{(signal.confidence * 100).toFixed(0)}%</dd></div><div><dt className="text-xs uppercase tracking-wide text-slate-500">Actionable</dt><dd className="mt-1 font-medium">{signal.is_actionable ? "Yes" : "No"}</dd></div><div><dt className="text-xs uppercase tracking-wide text-slate-500">Signal candle</dt><dd className="mt-1 text-xs text-slate-300">{signal.candle_close_time ?? "--"}</dd></div></dl><div className="mt-4"><p className="text-xs uppercase tracking-wide text-slate-500">Reasons</p><ul className="mt-2 space-y-1 text-xs text-slate-300">{signal.reasons.map((reason) => <li key={reason}>• {reason}</li>)}</ul></div></section>;
}
