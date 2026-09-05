import type { IndicatorSnapshot } from "@/types/bot";

export function IndicatorPanel({ snapshot }: { snapshot: IndicatorSnapshot | undefined }) {
  if (!snapshot || !snapshot.is_ready) return <section className="rounded-xl border border-dashed border-slate-700 bg-slate-900/40 p-5"><h2 className="font-semibold">Indicators</h2><p className="mt-4 text-sm text-amber-300">Warming Up / Insufficient Data</p><p className="mt-1 text-xs text-slate-500">Official values use validated closed 1m candles only.</p></section>;
  const values = [["EMA 9", snapshot.ema_9], ["EMA 21", snapshot.ema_21], ["RSI 14", snapshot.rsi_14], ["ATR 14 · Volatility", snapshot.atr_14], ["VWAP", snapshot.vwap], ["Closed volume", snapshot.volume], ["Volume MA 20", snapshot.volume_ma_20]];
  return <section className="rounded-xl border border-slate-800 bg-slate-900/70 p-5"><div className="flex items-center justify-between"><h2 className="font-semibold">Indicators Ready</h2><span className="text-xs text-slate-500">Closed candle</span></div><dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-3 text-sm">{values.map(([label, value]) => <div key={label}><dt className="text-xs uppercase tracking-wide text-slate-500">{label}</dt><dd className="mt-1 font-medium text-slate-200">{value}</dd></div>)}</dl><p className="mt-4 text-xs text-slate-500">Source candle (UTC): {snapshot.candle_close_time ?? "--"}</p></section>;
}
