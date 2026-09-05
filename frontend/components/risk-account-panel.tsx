import type { PaperAccount, RiskStatus } from "@/types/bot";

export function RiskAccountPanel({ status, account }: { status: RiskStatus | null; account: PaperAccount | null }) {
  if (!status) return <section className="rounded-xl border border-dashed border-slate-700 bg-slate-900/40 p-5"><h2 className="font-semibold">Account Risk</h2><p className="mt-4 text-sm text-amber-300">Risk account state unavailable</p></section>;
  const equity = account?.equity ?? status.equity;
  const dailyPnl = account?.realized_pnl_today ?? status.realized_pnl_today;
  const nextRisk = Number(equity) * Number(status.risk_per_trade);
  const dailyLimit = Number(equity) * Number(status.max_daily_loss);
  const values = [["Equity", `${equity} USDT`], ["Risk per trade", `${(Number(status.risk_per_trade) * 100).toFixed(2)}% · ${nextRisk.toFixed(4)} USDT`], ["Daily realized PnL", `${dailyPnl} USDT`], ["Daily loss limit", `${dailyLimit.toFixed(4)} USDT`], ["Open positions", `${account?.open_position_count ?? status.open_positions} / ${status.max_open_positions}`]];
  const locked = Number(dailyPnl) <= -dailyLimit;
  return <section className="rounded-xl border border-slate-800 bg-slate-900/70 p-5"><h2 className="font-semibold">Account Risk</h2><p className="mt-2 text-xs font-bold tracking-[0.12em] text-amber-300">PAPER RISK ONLY — NO REAL ORDERS</p>{locked ? <p className="mt-3 rounded bg-rose-400/10 p-2 text-xs font-bold text-rose-300">DAILY LOSS LIMIT REACHED</p> : null}<dl className="mt-4 space-y-3 text-sm">{values.map(([label, value]) => <div key={label}><dt className="text-xs uppercase tracking-wide text-slate-500">{label}</dt><dd className="mt-1 font-medium text-slate-200">{value}</dd></div>)}</dl></section>;
}
