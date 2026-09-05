import type { Candle, SymbolFeedStatus } from "@/types/bot";

export function MarketInfo({ candle, status }: { candle: Candle | undefined; status: SymbolFeedStatus | undefined }) {
  if (!candle) return <section className="rounded-xl border border-dashed border-slate-700 bg-slate-900/40 p-5"><h2 className="font-semibold">Market Information</h2><p className="mt-5 text-sm text-amber-300">Waiting for Market Data</p></section>;
  const fields = [["Current price", candle.close], ["Open", candle.open], ["High", candle.high], ["Low", candle.low], ["Volume", candle.volume], ["Candle", candle.is_closed ? "CLOSED" : "OPEN"], ["Feed", status?.status ?? "waiting"], ["Last update", status?.last_update ? new Date(status.last_update).toLocaleTimeString() : "--"]];
  return <section className="rounded-xl border border-slate-800 bg-slate-900/70 p-5"><h2 className="font-semibold">Market Information</h2><dl className="mt-4 grid grid-cols-2 gap-x-5 gap-y-4 text-sm">{fields.map(([label, value]) => <div key={label}><dt className="text-xs uppercase tracking-wide text-slate-500">{label}</dt><dd className="mt-1 font-medium text-slate-200">{value}</dd></div>)}</dl></section>;
}
