"use client";

import { useEffect, useState } from "react";
import { AlertCircle } from "lucide-react";

export default function FuturesDemoDashboard() {
  const [account, setAccount] = useState<any>(null);
  const [positions, setPositions] = useState<any[]>([]);
  const [error, setError] = useState<string>("");

  useEffect(() => {
    // Basic polling mock for the futures demo since we just generated the engine
    const fetchFutures = async () => {
      try {
        const res = await fetch(process.env.NEXT_PUBLIC_API_URL + "/api/paper/account");
        if (res.ok) {
          const data = await res.json();
          setAccount({
             wallet_balance: data.cash_balance,
             equity: data.equity,
             available_balance: data.cash_balance,
             used_margin: "0",
             free_margin: data.cash_balance,
             unrealized_pnl: "0",
             realized_pnl: data.realized_pnl
          });
        }
      } catch (err) {
        setError("Could not fetch demo futures state");
      }
    };
    
    fetchFutures();
    const int = setInterval(fetchFutures, 2000);
    return () => clearInterval(int);
  }, []);

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-4 flex items-start gap-3">
        <AlertCircle className="text-red-500 w-5 h-5 shrink-0 mt-0.5" />
        <div>
          <h3 className="font-semibold text-red-500 uppercase">LOCAL FUTURES DEMO — NO REAL ORDERS</h3>
          <p className="text-sm text-red-400 mt-1">
            This dashboard simulates an exchange-grade futures engine using public market data. No real money or Binance API keys are involved.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
          <div className="text-sm text-slate-400">Equity (USDT)</div>
          <div className="text-2xl font-semibold mt-1">{account?.equity || "0.00"}</div>
        </div>
        <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
          <div className="text-sm text-slate-400">Wallet Balance</div>
          <div className="text-2xl font-semibold mt-1">{account?.wallet_balance || "0.00"}</div>
        </div>
        <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
          <div className="text-sm text-slate-400">Used Margin</div>
          <div className="text-2xl font-semibold mt-1">{account?.used_margin || "0.00"}</div>
        </div>
        <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
          <div className="text-sm text-slate-400">Unrealized PnL</div>
          <div className="text-2xl font-semibold mt-1">{account?.unrealized_pnl || "0.00"}</div>
        </div>
      </div>
      
      <div className="bg-slate-900 border border-slate-800 rounded-lg p-6">
        <h2 className="text-lg font-semibold mb-4">Open Positions</h2>
        {positions.length === 0 ? (
          <div className="text-center text-slate-500 py-8">No open simulated futures positions</div>
        ) : (
          <div>Loading positions...</div>
        )}
      </div>
    </div>
  );
}
