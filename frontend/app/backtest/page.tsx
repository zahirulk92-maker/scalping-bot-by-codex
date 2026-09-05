"use client";

import { FormEvent, useState } from "react";

import { botApi } from "@/lib/api";
import type { BacktestResult, BacktestTrade, EquityPoint } from "@/types/bot";

const symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"];

function Metric({ label, value }: { label: string; value: string | number | null }) {
  return <article className="rounded-lg border border-slate-800 bg-slate-900/70 p-4"><p className="text-xs uppercase tracking-wide text-slate-500">{label}</p><p className="mt-2 text-lg font-semibold">{value ?? "--"}</p></article>;
}

function EquityCurve({ points }: { points: EquityPoint[] }) {
  if (points.length < 2) return <p className="p-5 text-sm text-slate-400">Equity curve appears after a completed run.</p>;
  const values = points.map((point) => Number(point.equity));
  const minimum = Math.min(...values); const maximum = Math.max(...values); const range = maximum - minimum || 1;
  const line = values.map((value, index) => `${(index / (values.length - 1)) * 100},${100 - ((value - minimum) / range) * 100}`).join(" ");
  return <svg aria-label="Backtest equity curve" className="h-56 w-full p-5" viewBox="0 0 100 100" preserveAspectRatio="none"><polyline points={line} fill="none" stroke="#22d3ee" strokeWidth="1.5" vectorEffect="non-scaling-stroke" /></svg>;
}

export default function BacktestPage() {
  const [selected, setSelected] = useState<string[]>(["BTCUSDT"]);
  const [start, setStart] = useState("2026-01-01T00:00");
  const [end, setEnd] = useState("2026-01-01T01:00");
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [trades, setTrades] = useState<BacktestTrade[]>([]);
  const [equity, setEquity] = useState<EquityPoint[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setRunning(true); setError(null);
    try {
      const next = await botApi.runBacktest({ symbols: selected, timeframe: "1m", start_time: new Date(`${start}Z`).toISOString(), end_time: new Date(`${end}Z`).toISOString() });
      const [nextTrades, nextEquity] = await Promise.all([botApi.backtestTrades(next.run_id), botApi.backtestEquity(next.run_id)]);
      setResult(next); setTrades(nextTrades); setEquity(nextEquity);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Backtest failed"); } finally { setRunning(false); }
  }

  function toggle(symbol: string) { setSelected((current) => current.includes(symbol) ? current.filter((item) => item !== symbol) : [...current, symbol]); }

  return <main className="mx-auto min-h-screen max-w-7xl px-4 py-5 sm:px-6 lg:px-8"><header className="border-b border-slate-800 pb-5"><p className="text-xs font-bold tracking-[0.24em] text-cyan-400">HISTORICAL SIMULATION</p><h1 className="mt-1 text-2xl font-bold">BACKTEST</h1><p className="mt-2 text-sm text-amber-300">SIMULATION ONLY — RESULTS DO NOT GUARANTEE FUTURE PERFORMANCE</p></header><form className="mt-6 rounded-xl border border-slate-800 bg-slate-900/70 p-5" onSubmit={submit}><div className="flex flex-wrap gap-4">{symbols.map((symbol) => <label className="flex items-center gap-2 text-sm" key={symbol}><input checked={selected.includes(symbol)} onChange={() => toggle(symbol)} type="checkbox" />{symbol}</label>)}</div><div className="mt-4 grid gap-4 sm:grid-cols-2"><label className="text-sm">Start UTC<input className="mt-1 block w-full rounded border border-slate-700 bg-slate-950 p-2" onChange={(event) => setStart(event.target.value)} type="datetime-local" value={start} /></label><label className="text-sm">End UTC<input className="mt-1 block w-full rounded border border-slate-700 bg-slate-950 p-2" onChange={(event) => setEnd(event.target.value)} type="datetime-local" value={end} /></label></div><button className="mt-4 rounded bg-cyan-500 px-4 py-2 text-sm font-bold text-slate-950 disabled:opacity-50" disabled={running || selected.length === 0} type="submit">{running ? "RUNNING…" : "RUN BACKTEST"}</button>{error ? <p className="mt-3 text-sm text-rose-300">{error}</p> : null}</form>{result ? <><section className="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-5"><Metric label="Starting balance" value={`${result.starting_balance} USDT`} /><Metric label="Ending balance" value={`${result.ending_balance} USDT`} /><Metric label="Net PnL" value={`${result.net_pnl} USDT`} /><Metric label="Return" value={`${result.return_percent}%`} /><Metric label="Trades / Win rate" value={`${result.total_trades} / ${result.win_rate ?? "--"}`} /><Metric label="Profit factor" value={result.profit_factor} /><Metric label="Expectancy" value={result.expectancy_per_trade} /><Metric label="Max drawdown" value={`${result.max_drawdown_usdt} USDT`} /><Metric label="Average R" value={result.average_r_multiple} /><Metric label="Total fees" value={`${result.total_fees} USDT`} /></section><section className="mt-6 overflow-hidden rounded-xl border border-slate-800 bg-slate-900/70"><h2 className="p-5 font-semibold">Equity Curve</h2><EquityCurve points={equity} /></section><section className="mt-6 overflow-x-auto rounded-xl border border-slate-800 bg-slate-900/70"><h2 className="p-5 font-semibold">Trade Journal</h2><table className="min-w-full text-left text-xs"><thead className="bg-slate-950/60 text-slate-500"><tr>{["Time", "Symbol", "Direction", "Entry", "Exit", "Reason", "Risk", "Net PnL", "R", "Score"].map((label) => <th className="px-3 py-3" key={label}>{label}</th>)}</tr></thead><tbody>{trades.map((trade, index) => <tr className="border-t border-slate-800" key={`${trade.symbol}-${trade.exit_time}-${index}`}><td className="px-3 py-3">{trade.exit_time}</td><td className="px-3 py-3">{trade.symbol}</td><td className="px-3 py-3 uppercase">{trade.direction}</td><td className="px-3 py-3">{trade.entry_price}</td><td className="px-3 py-3">{trade.exit_price}</td><td className="px-3 py-3">{trade.exit_reason}</td><td className="px-3 py-3">{trade.planned_risk_amount}</td><td className="px-3 py-3">{trade.net_pnl}</td><td className="px-3 py-3">{trade.r_multiple}</td><td className="px-3 py-3">{trade.signal_score}</td></tr>)}</tbody></table></section></> : null}</main>;
}
