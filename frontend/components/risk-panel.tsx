import type { TradePlan } from "@/types/bot";

const statusStyles = {
  approved: "border-emerald-400/40 bg-emerald-400/10 text-emerald-300",
  rejected: "border-rose-400/40 bg-rose-400/10 text-rose-300",
} as const;

function Value({ label, value }: { label: string; value: string | null }) {
  return <div><dt className="text-xs uppercase tracking-wide text-slate-500">{label}</dt><dd className="mt-1 break-all font-medium text-slate-200">{value ?? "--"}</dd></div>;
}

export function RiskPanel({ plan }: { plan: TradePlan | undefined }) {
  if (!plan || !plan.source_candle_open_time) {
    return <section className="rounded-xl border border-dashed border-slate-700 bg-slate-900/40 p-5"><h2 className="font-semibold">Risk Plan</h2><p className="mt-4 text-sm text-amber-300">Waiting for an actionable closed-candle signal</p><p className="mt-1 text-xs text-slate-500">RISK PLAN ONLY — EXECUTION DISABLED</p></section>;
  }
  const status = plan.approved ? "approved" : "rejected";
  return <section className="rounded-xl border border-slate-800 bg-slate-900/70 p-5"><div className="flex items-center justify-between gap-3"><h2 className="font-semibold">Risk Plan</h2><span className={`rounded-full border px-2.5 py-1 text-xs font-bold tracking-wide ${statusStyles[status]}`}>{status.toUpperCase()}</span></div><p className="mt-2 text-xs font-bold tracking-[0.12em] text-amber-300">RISK PLAN ONLY — EXECUTION DISABLED</p><dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-3 text-sm"><Value label="Direction" value={plan.direction.replace("_", " ").toUpperCase()} /><Value label="Entry reference" value={plan.entry_reference_price} /><Value label="Stop loss" value={plan.stop_loss_price} /><Value label="Take profit" value={plan.take_profit_price} /><Value label="Risk amount" value={plan.risk_amount_usdt ? `${plan.risk_amount_usdt} USDT` : null} /><Value label="Position notional" value={plan.position_notional_usdt ? `${plan.position_notional_usdt} USDT` : null} /><Value label="Estimated quantity" value={plan.estimated_quantity} /><Value label="Risk : Reward" value={plan.risk_reward_ratio} /><Value label="Estimated fees" value={plan.estimated_fees_usdt ? `${plan.estimated_fees_usdt} USDT` : null} /><Value label="Estimated slippage" value={plan.estimated_slippage_usdt ? `${plan.estimated_slippage_usdt} USDT` : null} /></dl>{!plan.approved && plan.rejection_reasons.length > 0 ? <div className="mt-4"><p className="text-xs uppercase tracking-wide text-slate-500">Rejection reasons</p><ul className="mt-2 space-y-1 text-xs text-rose-200">{plan.rejection_reasons.map((reason) => <li key={reason}>• {reason}</li>)}</ul></div> : null}</section>;
}
