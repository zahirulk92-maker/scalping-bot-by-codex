"use client";

import { useEffect, useState } from "react";

import { botApi } from "@/lib/api";
import type { Candle, ClosedPaperTrade, ConnectionState, IndicatorSnapshot, MarketStatus, MarketWebSocketEvent, PaperAccount, PaperPosition, RiskStatus, SignalSnapshot, TradePlan } from "@/types/bot";

const HISTORY_LIMIT = 500;

function webSocketUrl(): string {
  const api = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";
  return `${api.replace(/^http/, "ws").replace(/\/$/, "")}/ws/market`;
}

function mergeCandle(candles: Candle[], next: Candle): Candle[] {
  const index = candles.findIndex((candle) => candle.open_time === next.open_time);
  const merged = index >= 0 ? candles.map((candle, itemIndex) => itemIndex === index ? next : candle) : [...candles, next];
  return merged.toSorted((left, right) => left.open_time.localeCompare(right.open_time)).slice(-HISTORY_LIMIT);
}

function mergeSnapshot(snapshots: IndicatorSnapshot[], next: IndicatorSnapshot): IndicatorSnapshot[] {
  const index = snapshots.findIndex((snapshot) => snapshot.candle_open_time === next.candle_open_time);
  const merged = index >= 0 ? snapshots.map((snapshot, itemIndex) => itemIndex === index ? next : snapshot) : [...snapshots, next];
  return merged.toSorted((left, right) => (left.candle_open_time ?? "").localeCompare(right.candle_open_time ?? "")).slice(-HISTORY_LIMIT);
}

function mergeSignal(signals: SignalSnapshot[], next: SignalSnapshot): SignalSnapshot[] {
  const index = signals.findIndex((signal) => signal.candle_open_time === next.candle_open_time);
  const merged = index >= 0 ? signals.map((signal, itemIndex) => itemIndex === index ? next : signal) : [...signals, next];
  return merged.toSorted((left, right) => (left.candle_open_time ?? "").localeCompare(right.candle_open_time ?? "")).slice(-HISTORY_LIMIT);
}

function isMarketEvent(value: unknown): value is MarketWebSocketEvent {
  return typeof value === "object" && value !== null && "type" in value && "data" in value;
}

export function useMarketData(symbols: string[]) {
  const symbolsKey = symbols.join(",");
  const [status, setStatus] = useState<MarketStatus | null>(null);
  const [candles, setCandles] = useState<Record<string, Candle[]>>({});
  const [indicators, setIndicators] = useState<Record<string, IndicatorSnapshot>>({});
  const [indicatorHistory, setIndicatorHistory] = useState<Record<string, IndicatorSnapshot[]>>({});
  const [signals, setSignals] = useState<Record<string, SignalSnapshot>>({});
  const [signalHistory, setSignalHistory] = useState<Record<string, SignalSnapshot[]>>({});
  const [riskPlans, setRiskPlans] = useState<Record<string, TradePlan>>({});
  const [riskStatus, setRiskStatus] = useState<RiskStatus | null>(null);
  const [paperAccount, setPaperAccount] = useState<PaperAccount | null>(null);
  const [paperPositions, setPaperPositions] = useState<PaperPosition[]>([]);
  const [paperTrades, setPaperTrades] = useState<ClosedPaperTrade[]>([]);
  const [connection, setConnection] = useState<ConnectionState>("checking");

  useEffect(() => {
    const configuredSymbols = symbolsKey.split(",").filter(Boolean);
    let active = true;
    let socket: WebSocket | null = null;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    let attempts = 0;

    const applyCandle = (next: Candle) => setCandles((current) => ({
      ...current,
      [next.symbol]: mergeCandle(current[next.symbol] ?? [], next),
    }));
    const applyIndicator = (next: IndicatorSnapshot) => {
      setIndicators((current) => ({ ...current, [next.symbol]: next }));
      setIndicatorHistory((current) => ({ ...current, [next.symbol]: mergeSnapshot(current[next.symbol] ?? [], next) }));
    };
    const applySignal = (next: SignalSnapshot) => {
      setSignals((current) => ({ ...current, [next.symbol]: next }));
      setSignalHistory((current) => ({ ...current, [next.symbol]: mergeSignal(current[next.symbol] ?? [], next) }));
    };
    const applyRiskPlan = (next: TradePlan) => setRiskPlans((current) => ({ ...current, [next.symbol]: next }));
    const applyPosition = (next: PaperPosition) => setPaperPositions((current) => {
      const index = current.findIndex((position) => position.position_id === next.position_id);
      return index >= 0 ? current.map((position, itemIndex) => itemIndex === index ? next : position) : [...current, next];
    });
    const applyClosedTrade = (next: ClosedPaperTrade) => {
      setPaperPositions((current) => current.filter((position) => position.position_id !== next.position_id));
      setPaperTrades((current) => [next, ...current.filter((trade) => trade.trade_id !== next.trade_id)].slice(0, HISTORY_LIMIT));
    };

    const connect = () => {
      if (!active) return;
      socket = new WebSocket(webSocketUrl());
      socket.onopen = () => { attempts = 0; if (active) setConnection("connected"); };
      socket.onmessage = (message) => {
        try {
          const event: unknown = JSON.parse(message.data as string);
          if (!isMarketEvent(event) || !active) return;
          if (event.type === "market.candle") applyCandle(event.data);
          if (event.type === "market.status") setStatus(event.data);
          if (event.type === "market.snapshot") {
            setStatus(event.data.status);
            event.data.current_candles.forEach(applyCandle);
          }
          if (event.type === "indicator.snapshot") applyIndicator(event.data);
          if (event.type === "strategy.signal") applySignal(event.data);
          if (event.type === "risk.plan") applyRiskPlan(event.data);
          if (event.type === "paper.position_opened" || event.type === "paper.position_updated") applyPosition(event.data);
          if (event.type === "paper.position_closed") applyClosedTrade(event.data);
          if (event.type === "paper.account_updated") setPaperAccount(event.data);
        } catch { /* Ignore malformed server messages without breaking the dashboard. */ }
      };
      socket.onclose = () => {
        if (!active) return;
        setConnection("offline");
        attempts += 1;
        const delay = Math.min(30_000, 1_000 * 2 ** Math.min(attempts - 1, 5));
        retryTimer = setTimeout(connect, delay);
      };
      socket.onerror = () => socket?.close();
    };

    async function bootstrap() {
      try {
        const [nextStatus, nextRiskStatus, nextPaperAccount, nextPositions, nextTrades] = await Promise.all([botApi.marketStatus(), botApi.riskStatus(), botApi.paperAccount(), botApi.paperPositions(), botApi.paperTrades()]);
        const history = await Promise.all(configuredSymbols.map(async (symbol) => {
          const [candleHistory, snapshots, latest, strategyHistory, strategy, risk] = await Promise.all([botApi.candles(symbol), botApi.indicatorHistory(symbol), botApi.indicators(symbol), botApi.strategyHistory(symbol), botApi.strategy(symbol), botApi.risk(symbol)]);
          return [symbol, candleHistory, snapshots, latest, strategyHistory, strategy, risk] as const;
        }));
        if (!active) return;
        setStatus(nextStatus);
        setRiskStatus(nextRiskStatus);
        setPaperAccount(nextPaperAccount);
        setPaperPositions(nextPositions);
        setPaperTrades(nextTrades);
        setCandles(Object.fromEntries(history.map(([symbol, candleHistory]) => [symbol, candleHistory])));
        setIndicatorHistory(Object.fromEntries(history.map(([symbol, , snapshots]) => [symbol, snapshots])));
        setIndicators(Object.fromEntries(history.map(([symbol, , , latest]) => [symbol, latest])));
        setSignalHistory(Object.fromEntries(history.map(([symbol, , , , snapshots]) => [symbol, snapshots])));
        setSignals(Object.fromEntries(history.map(([symbol, , , , , latest]) => [symbol, latest])));
        setRiskPlans(Object.fromEntries(history.map(([symbol, , , , , , plan]) => [symbol, plan])));
      } catch {
        if (active) setConnection("offline");
      }
    }

    void bootstrap();
    connect();
    return () => {
      active = false;
      if (retryTimer) clearTimeout(retryTimer);
      socket?.close();
    };
  }, [symbolsKey]);

  return { status, candles, indicators, indicatorHistory, signals, signalHistory, riskPlans, riskStatus, paperAccount, paperPositions, paperTrades, connection };
}
