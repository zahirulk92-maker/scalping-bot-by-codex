"use client";

import { useEffect, useState } from "react";
import { AlertCircle, CheckCircle2, AlertTriangle, ShieldX } from "lucide-react";

export default function FuturesValidationDashboard() {
  const [snapshot, setSnapshot] = useState<any>(null);

  useEffect(() => {
    // Mock polling
    const fetchVal = async () => {
      try {
        const res = await fetch(process.env.NEXT_PUBLIC_API_URL + "/api/futures-validation/status");
        if (res.ok) {
          const data = await res.json();
          setSnapshot(data);
        }
      } catch (err) {}
    };
    
    fetchVal();
    const int = setInterval(fetchVal, 5000);
    return () => clearInterval(int);
  }, []);

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      <div className="bg-blue-500/10 border border-blue-500/20 rounded-lg p-4">
        <h3 className="font-semibold text-blue-500 uppercase">FUTURES FORWARD VALIDATION</h3>
        <p className="text-sm text-blue-400 mt-1">
          Evaluates the robustness of the Futures Demo Engine. PASS does not authorize real-money trading.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
          <div className="text-sm text-slate-400">Current Status</div>
          <div className="text-2xl font-bold mt-1 text-yellow-500">
            {snapshot?.status || "INSUFFICIENT_DATA"}
          </div>
        </div>
      </div>
      
      <div className="bg-slate-900 border border-slate-800 rounded-lg p-6 mt-6">
        <h2 className="text-lg font-semibold mb-4">Cost Stress Analysis</h2>
        <div className="grid grid-cols-3 gap-4">
            <div className="p-3 border border-slate-800 rounded text-center">
                <div className="text-sm text-slate-400">NORMAL</div>
                <div>0.00</div>
            </div>
            <div className="p-3 border border-slate-800 rounded text-center">
                <div className="text-sm text-slate-400">HIGH COST (1.5x)</div>
                <div>0.00</div>
            </div>
            <div className="p-3 border border-slate-800 rounded text-center">
                <div className="text-sm text-slate-400">EXTREME COST (2.0x)</div>
                <div>0.00</div>
            </div>
        </div>
      </div>
      
      <div className="bg-slate-900 border border-slate-800 rounded-lg p-6 mt-6">
        <h2 className="text-lg font-semibold mb-4">Leverage Safety Scenarios</h2>
        <div className="text-sm text-slate-400">Evaluating 1x, 2x, 3x, 5x, 10x margin profiles...</div>
      </div>
      
      <div className="bg-slate-900 border border-slate-800 rounded-lg p-6 mt-6">
        <h2 className="text-lg font-semibold mb-4">Monte Carlo / Resampling</h2>
        <div className="text-sm text-slate-400">
          <strong>SIMULATION / NOT A GUARANTEE</strong>
        </div>
        <div className="mt-2 text-sm">Median ending equity: 100.00</div>
      </div>
    </div>
  );
}
