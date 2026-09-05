"use client";

import { CandlestickSeries, ColorType, createChart, LineSeries, type IChartApi, type UTCTimestamp } from "lightweight-charts";
import { useEffect, useRef } from "react";

import type { Candle, IndicatorSnapshot } from "@/types/bot";

type ChartCandle = { time: UTCTimestamp; open: number; high: number; low: number; close: number };
type CandleSeriesHandle = { setData: (data: ChartCandle[]) => void };
type LinePoint = { time: UTCTimestamp; value: number };
type LineSeriesHandle = { setData: (data: LinePoint[]) => void };

function toChartCandle(candle: Candle): ChartCandle {
  return { time: Math.floor(new Date(candle.open_time).getTime() / 1_000) as UTCTimestamp, open: Number(candle.open), high: Number(candle.high), low: Number(candle.low), close: Number(candle.close) };
}

export function CandlestickChart({ symbol, candles, indicators }: { symbol: string; candles: Candle[]; indicators: IndicatorSnapshot[] }) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<CandleSeriesHandle | null>(null);
  const emaFastRef = useRef<LineSeriesHandle | null>(null);
  const emaSlowRef = useRef<LineSeriesHandle | null>(null);
  const vwapRef = useRef<LineSeriesHandle | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const chart = createChart(container, { autoSize: true, height: 360, layout: { background: { type: ColorType.Solid, color: "#0f172a" }, textColor: "#94a3b8" }, grid: { vertLines: { color: "#1e293b" }, horzLines: { color: "#1e293b" } }, rightPriceScale: { borderColor: "#334155" }, timeScale: { borderColor: "#334155", timeVisible: true } });
    const series = chart.addSeries(CandlestickSeries, { upColor: "#34d399", downColor: "#fb7185", borderVisible: false, wickUpColor: "#34d399", wickDownColor: "#fb7185" });
    chartRef.current = chart;
    seriesRef.current = series;
    emaFastRef.current = chart.addSeries(LineSeries, { color: "#22d3ee", lineWidth: 2, title: "EMA 9" });
    emaSlowRef.current = chart.addSeries(LineSeries, { color: "#a78bfa", lineWidth: 2, title: "EMA 21" });
    vwapRef.current = chart.addSeries(LineSeries, { color: "#fbbf24", lineWidth: 2, title: "VWAP" });
    return () => { chart.remove(); chartRef.current = null; seriesRef.current = null; emaFastRef.current = null; emaSlowRef.current = null; vwapRef.current = null; };
  }, []);

  useEffect(() => {
    if (!seriesRef.current) return;
    seriesRef.current.setData(candles.map(toChartCandle));
    chartRef.current?.timeScale().fitContent();
  }, [candles]);

  useEffect(() => {
    const points = (field: "ema_9" | "ema_21" | "vwap") => indicators.flatMap((snapshot) => snapshot.candle_open_time && snapshot[field] ? [{ time: Math.floor(new Date(snapshot.candle_open_time).getTime() / 1_000) as UTCTimestamp, value: Number(snapshot[field]) }] : []);
    emaFastRef.current?.setData(points("ema_9"));
    emaSlowRef.current?.setData(points("ema_21"));
    vwapRef.current?.setData(points("vwap"));
  }, [indicators]);

  return <section className="rounded-xl border border-slate-800 bg-slate-900/70 p-5"><div className="flex items-center justify-between"><h2 className="font-semibold">{symbol} · 1m Candles</h2><span className="text-xs text-slate-500">Price only</span></div><div className="relative mt-4 h-[360px]"><div ref={containerRef} className="h-full" />{candles.length === 0 ? <p className="absolute inset-0 grid place-items-center text-sm text-amber-300">Waiting for Market Data</p> : null}</div></section>;
}
