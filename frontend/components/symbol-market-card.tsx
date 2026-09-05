import type { Candle, SymbolFeedStatus } from "@/types/bot";

interface SymbolMarketCardProps {
  symbol: string;
  candle: Candle | undefined;
  status: SymbolFeedStatus | undefined;
  selected: boolean;
  onSelect: () => void;
}

export function SymbolMarketCard({ symbol, candle, status, selected, onSelect }: SymbolMarketCardProps) {
  const lastUpdate = status?.last_update ? new Date(status.last_update).toLocaleTimeString() : "--";
  return (
    <button type="button" onClick={onSelect} className={`rounded-xl border p-4 text-left transition ${selected ? "border-cyan-400 bg-cyan-400/10" : "border-slate-800 bg-slate-900/70 hover:border-slate-600"}`}>
      <div className="flex items-center justify-between"><span className="font-semibold">{symbol}</span><span className="text-xs uppercase text-slate-500">{status?.status ?? "waiting"}</span></div>
      <p className="mt-3 text-xl font-semibold text-slate-100">{candle ? candle.close : "Waiting for Market Data"}</p>
      <p className="mt-2 text-xs text-slate-500">Last update: {lastUpdate}</p>
    </button>
  );
}
