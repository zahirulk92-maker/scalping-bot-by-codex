"use client";

import { useEffect, useState } from "react";

import { CandlestickChart } from "@/components/candlestick-chart";
import { IndicatorPanel } from "@/components/indicator-panel";
import { MarketInfo } from "@/components/market-info";
import { PaperPositionPanel } from "@/components/paper-position-panel";
import { PaperTradeHistory } from "@/components/paper-trade-history";
import { RiskAccountPanel } from "@/components/risk-account-panel";
import { RiskPanel } from "@/components/risk-panel";
import { SignalPanel } from "@/components/signal-panel";
import { StatusCard } from "@/components/status-card";
import { SymbolMarketCard } from "@/components/symbol-market-card";
import { botApi } from "@/lib/api";
import { useMarketData } from "@/lib/use-market-data";
import type { BotStatus, ConnectionState } from "@/types/bot";

const fallbackSymbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"];
export default function DashboardPage() {
  const [connection, setConnection] = useState<ConnectionState>("checking");
  const [botStatus, setBotStatus] = useState<BotStatus | null>(null);
  const [selectedSymbol, setSelectedSymbol] = useState(fallbackSymbols[0]);
  const symbols = botStatus?.symbols ?? fallbackSymbols;
  const market = useMarketData(symbols);

  useEffect(() => {
    let active = true;
    async function loadBotStatus() {
      try {
        const [, nextStatus] = await Promise.all([botApi.health(), botApi.status()]);
        if (!active) return;
        setBotStatus(nextStatus);
        setSelectedSymbol(nextStatus.symbols[0] ?? fallbackSymbols[0]);
        setConnection("connected");
      } catch {
        if (active) setConnection("offline");
      }
    }
    void loadBotStatus();
    return () => { active = false; };
  }, []);

  const latest = market.candles[selectedSymbol]?.at(-1);
  const marketFeed = market.status?.status ?? (market.connection === "connected" ? "connecting" : "disconnected");
  const connectionLabel = connection === "connected" ? "Backend Connected" : connection === "offline" ? "Backend Offline" : "Checking Backend";
  const balance = market.paperAccount ? `${market.paperAccount.equity} USDT` : botStatus ? `${botStatus.starting_balance.toLocaleString()} ${botStatus.currency}` : "--";
  const lossLimit = botStatus ? `${(botStatus.max_daily_loss * 100).toFixed(0)}%` : "--";
  const activePosition = market.paperPositions.find((position) => position.symbol === selectedSymbol);

  return <main className="mx-auto min-h-screen max-w-7xl px-4 py-5 sm:px-6 lg:px-8">
    <header className="flex flex-col gap-4 border-b border-slate-800 pb-5 sm:flex-row sm:items-center sm:justify-between"><div><p className="text-xs font-bold tracking-[0.24em] text-cyan-400">PAPER TRADING DASHBOARD</p><h1 className="mt-1 text-2xl font-bold">SCALPING BOT</h1></div><div className="flex flex-wrap items-center gap-3"><span className="rounded-full border border-amber-400/40 bg-amber-400/10 px-3 py-1 text-xs font-bold tracking-wide text-amber-300">PAPER TRADING ONLY · NO REAL ORDERS</span><span className={`text-sm ${connection === "connected" ? "text-emerald-300" : "text-slate-400"}`}>{connectionLabel}</span><span className="text-sm text-slate-400">Market Feed: <strong className="uppercase text-slate-200">{marketFeed}</strong></span></div></header>
    <section className="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4"><StatusCard label="Paper Equity" value={balance} hint="Simulated account" /><StatusCard label="Realized PnL" value={market.paperAccount ? `${market.paperAccount.realized_pnl} USDT` : "--"} hint="Simulated only" /><StatusCard label="Today's PnL" value={market.paperAccount ? `${market.paperAccount.realized_pnl_today} USDT` : "--"} hint="UTC day" /><StatusCard label="Open Positions" value={market.paperAccount?.open_position_count.toString() ?? "--"} hint={`Limit ${botStatus?.max_open_positions ?? 1} · Daily loss ${lossLimit}`} /></section>
    <section className="mt-6 grid gap-4 md:grid-cols-3">{symbols.map((symbol) => <SymbolMarketCard key={symbol} symbol={symbol} candle={market.candles[symbol]?.at(-1)} status={market.status?.symbols[symbol]} selected={symbol === selectedSymbol} onSelect={() => setSelectedSymbol(symbol)} />)}</section>
    <p className="mt-6 text-xs uppercase tracking-[0.14em] text-slate-500">{selectedSymbol} · Paper simulation only · No real exchange orders</p>
    <section className="mt-4 grid gap-4 xl:grid-cols-3"><div className="xl:col-span-2"><CandlestickChart symbol={selectedSymbol} candles={market.candles[selectedSymbol] ?? []} indicators={market.indicatorHistory[selectedSymbol] ?? []} /></div><MarketInfo candle={latest} status={market.status?.symbols[selectedSymbol]} /></section>
    <section className="mt-4 grid gap-4 xl:grid-cols-3"><div className="xl:col-span-2"><IndicatorPanel snapshot={market.indicators[selectedSymbol]} /></div><SignalPanel signal={market.signals[selectedSymbol]} /></section>
    <section className="mt-4 grid gap-4 xl:grid-cols-3"><div className="xl:col-span-2"><RiskPanel plan={market.riskPlans[selectedSymbol]} /></div><RiskAccountPanel status={market.riskStatus} account={market.paperAccount} /></section>
    <section className="mt-4 grid gap-4 xl:grid-cols-3"><div className="xl:col-span-2"><PaperPositionPanel position={activePosition} /></div></section>
    <section className="mt-4"><PaperTradeHistory trades={market.paperTrades} /></section>
  </main>;
}
