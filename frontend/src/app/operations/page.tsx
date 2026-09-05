"use client";

import { useEffect, useState } from "react";
import { Activity, Database, HeartPulse, Server, ShieldCheck, AlertCircle } from "lucide-react";

export default function OperationsDashboard() {
  const [health, setHealth] = useState<any>(null);
  const [ready, setReady] = useState<any>(null);
  const [version, setVersion] = useState<any>(null);

  useEffect(() => {
    const fetchOps = async () => {
      try {
        const [hRes, rRes, vRes] = await Promise.all([
          fetch(process.env.NEXT_PUBLIC_API_URL + "/api/futures-demo/health"),
          fetch(process.env.NEXT_PUBLIC_API_URL + "/api/system/ready"),
          fetch(process.env.NEXT_PUBLIC_API_URL + "/api/system/version"),
        ]);
        if (hRes.ok) setHealth(await hRes.json());
        if (rRes.ok) setReady(await rRes.json());
        if (vRes.ok) setVersion(await vRes.json());
      } catch (err) {}
    };
    fetchOps();
    const int = setInterval(fetchOps, 5000);
    return () => clearInterval(int);
  }, []);

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-lg p-4 flex items-start gap-3">
        <ShieldCheck className="text-emerald-500 w-5 h-5 shrink-0 mt-0.5" />
        <div>
          <h3 className="font-semibold text-emerald-500 uppercase">SYSTEM OPERATIONS CENTER</h3>
          <p className="text-sm text-emerald-400 mt-1">
            FUTURES DEMO ONLY — NO REAL MONEY EXECUTION. Version {version?.version}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
          <div className="flex items-center gap-2 text-slate-400 mb-2">
            <HeartPulse className="w-4 h-4" /> <span className="text-sm">Readiness</span>
          </div>
          <div className="text-2xl font-semibold text-emerald-500">{ready?.status || "UNKNOWN"}</div>
        </div>
        <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
          <div className="flex items-center gap-2 text-slate-400 mb-2">
            <Server className="w-4 h-4" /> <span className="text-sm">Environment</span>
          </div>
          <div className="text-2xl font-semibold">{version?.environment || "unknown"}</div>
        </div>
        <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
          <div className="flex items-center gap-2 text-slate-400 mb-2">
            <Activity className="w-4 h-4" /> <span className="text-sm">Kill Switch</span>
          </div>
          <div className={	ext-2xl font-semibold }>
            {health?.kill_switch_active ? "ACTIVE" : "INACTIVE"}
          </div>
        </div>
        <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
          <div className="flex items-center gap-2 text-slate-400 mb-2">
            <Database className="w-4 h-4" /> <span className="text-sm">Account Consistency</span>
          </div>
          <div className="text-2xl font-semibold text-emerald-500">{health?.account_consistency || "UNKNOWN"}</div>
        </div>
      </div>
      
      <div className="bg-slate-900 border border-slate-800 rounded-lg p-6 mt-6">
        <h2 className="text-lg font-semibold mb-4">Component Health</h2>
        <div className="space-y-3">
            {ready?.components && Object.entries(ready.components).map(([key, val]) => (
                <div key={key} className="flex justify-between items-center border-b border-slate-800 pb-2">
                    <span className="capitalize">{key.replace('_', ' ')}</span>
                    <span className="text-emerald-500">{val as string}</span>
                </div>
            ))}
        </div>
      </div>
    </div>
  );
}
