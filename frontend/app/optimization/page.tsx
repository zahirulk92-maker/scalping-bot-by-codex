"use client";

import { FormEvent, useState } from "react";

import { botApi } from "@/lib/api";
import type { EvaluationMetrics, OptimizationCandidate, OptimizationRun } from "@/types/bot";

const symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"];
const defaultGrid = JSON.stringify({ EMA_FAST_PERIOD: [7, 9], EMA_SLOW_PERIOD: [18, 21] }, null, 2);

function metricsLine(metrics: EvaluationMetrics) {
  return `${metrics.total_trades} trades · ${metrics.net_pnl} USDT · PF ${metrics.profit_factor ?? "--"} · DD ${metrics.max_drawdown_percent}%`;
}

function CandidateRow({ candidate, selected }: { candidate: OptimizationCandidate; selected: boolean }) {
  return <tr className={`border-t border-slate-800 ${selected ? "bg-cyan-400/10" : ""}`}>
    <td className="px-3 py-3 font-medium">{candidate.is_baseline ? "Baseline" : candidate.candidate_id}</td>
    <td className="px-3 py-3 text-slate-300">{Object.entries(candidate.parameters).map(([key, value]) => `${key}=${value}`).join(", ") || "Current settings"}</td>
    <td className="px-3 py-3">{candidate.validation_score ?? "--"}</td>
    <td className="px-3 py-3">{metricsLine(candidate.validation_metrics)}</td>
    <td className="px-3 py-3">{candidate.selection_eligible ? "Eligible" : "Filtered"}</td>
    <td className="px-3 py-3 text-amber-200">{candidate.warnings.join(", ") || "—"}</td>
  </tr>;
}

export default function OptimizationPage() {
  const [selected, setSelected] = useState<string[]>(["BTCUSDT"]);
  const [start, setStart] = useState("2026-01-01T00:00");
  const [end, setEnd] = useState("2026-01-31T00:00");
  const [grid, setGrid] = useState(defaultGrid);
  const [result, setResult] = useState<OptimizationRun | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  function toggle(symbol: string) { setSelected((current) => current.includes(symbol) ? current.filter((item) => item !== symbol) : [...current, symbol]); }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError(null); setRunning(true);
    try {
      const parameterGrid = JSON.parse(grid) as Record<string, number[]>;
      const next = await botApi.runOptimization({ symbols: selected, timeframe: "1m", start_time: new Date(`${start}Z`).toISOString(), end_time: new Date(`${end}Z`).toISOString(), parameter_grid: parameterGrid, search_method: "grid" });
      setResult(next);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Optimization failed"); } finally { setRunning(false); }
  }

  async function finalEvaluate() {
    if (!result) return;
    setError(null); setRunning(true);
    try { setResult(await botApi.finalEvaluateOptimization(result.run_id)); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Final evaluation failed"); }
    finally { setRunning(false); }
  }

  const selectedCandidate = result?.candidates.find((candidate) => candidate.candidate_id === result.selected_candidate_id);
  return <main className="mx-auto min-h-screen max-w-7xl px-4 py-5 sm:px-6 lg:px-8">
    <header className="border-b border-slate-800 pb-5"><p className="text-xs font-bold tracking-[0.24em] text-cyan-400">RESEARCH WORKBENCH</p><h1 className="mt-1 text-2xl font-bold">STRATEGY OPTIMIZATION</h1><p className="mt-2 text-sm text-amber-300">SIMULATION ONLY — CANDIDATES NEVER CHANGE PAPER SETTINGS OR PLACE ORDERS</p></header>
    <form className="mt-6 rounded-xl border border-slate-800 bg-slate-900/70 p-5" onSubmit={submit}>
      <div className="flex flex-wrap gap-4">{symbols.map((symbol) => <label className="flex items-center gap-2 text-sm" key={symbol}><input checked={selected.includes(symbol)} onChange={() => toggle(symbol)} type="checkbox" />{symbol}</label>)}</div>
      <div className="mt-4 grid gap-4 sm:grid-cols-2"><label className="text-sm">Start UTC<input className="mt-1 block w-full rounded border border-slate-700 bg-slate-950 p-2" onChange={(event) => setStart(event.target.value)} type="datetime-local" value={start} /></label><label className="text-sm">End UTC<input className="mt-1 block w-full rounded border border-slate-700 bg-slate-950 p-2" onChange={(event) => setEnd(event.target.value)} type="datetime-local" value={end} /></label></div>
      <label className="mt-4 block text-sm">Bounded parameter grid (JSON; supported fields include EMA_FAST_PERIOD, EMA_SLOW_PERIOD, RSI bounds, score, VWAP/EMA/volume/ATR filters, ATR_STOP_MULTIPLIER, TARGET_RR)<textarea className="mt-1 block min-h-36 w-full rounded border border-slate-700 bg-slate-950 p-3 font-mono text-xs" onChange={(event) => setGrid(event.target.value)} value={grid} /></label>
      <button className="mt-4 rounded bg-cyan-500 px-4 py-2 text-sm font-bold text-slate-950 disabled:opacity-50" disabled={running || selected.length === 0} type="submit">{running ? "EVALUATING…" : "RUN OPTIMIZATION"}</button>{error ? <p className="mt-3 text-sm text-rose-300">{error}</p> : null}
    </form>
    {result ? <>
      <section className="mt-6 rounded-xl border border-slate-800 bg-slate-900/70 p-5"><h2 className="font-semibold">Chronological protocol</h2><p className="mt-2 text-sm text-slate-300">Train ends {result.train_end}; validation ends {result.validation_end}; the holdout begins {result.holdout_start}. Ranking uses validation only.</p><p className="mt-2 text-sm text-cyan-200">{result.selection_reason}</p>{selectedCandidate && !result.final_holdout_evaluated ? <button className="mt-4 rounded border border-amber-400/70 px-4 py-2 text-sm font-bold text-amber-200 disabled:opacity-50" disabled={running} onClick={finalEvaluate} type="button">FINAL EVALUATE SELECTED CANDIDATE ON HOLDOUT</button> : null}</section>
      <section className="mt-6 overflow-x-auto rounded-xl border border-slate-800 bg-slate-900/70"><h2 className="p-5 font-semibold">Baseline and candidate ranking</h2><table className="min-w-full text-left text-xs"><thead className="bg-slate-950/60 text-slate-500"><tr>{["Candidate", "Parameters", "Score", "Validation", "Status", "Warnings"].map((label) => <th className="px-3 py-3" key={label}>{label}</th>)}</tr></thead><tbody><CandidateRow candidate={result.baseline} selected={false} />{result.candidates.map((candidate) => <CandidateRow candidate={candidate} key={candidate.candidate_id} selected={candidate.candidate_id === result.selected_candidate_id} />)}</tbody></table></section>
      {selectedCandidate ? <section className="mt-6 rounded-xl border border-slate-800 bg-slate-900/70 p-5"><h2 className="font-semibold">Selected-candidate diagnostics</h2><p className="mt-2 text-sm">Stability score: {selectedCandidate.stability_score ?? "not available"}</p><p className="mt-2 text-sm">Cost stress: {selectedCandidate.cost_stress.map((item) => `${item.scenario} ${metricsLine(item.metrics)}`).join(" | ") || "Not evaluated"}</p><p className="mt-2 text-sm">Walk-forward folds: {selectedCandidate.walk_forward.length}</p>{selectedCandidate.test_metrics ? <p className="mt-2 text-sm text-amber-200">Final holdout: {metricsLine(selectedCandidate.test_metrics)}</p> : null}</section> : null}
    </> : null}
  </main>;
}
