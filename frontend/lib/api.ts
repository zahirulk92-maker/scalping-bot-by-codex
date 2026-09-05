import type { AlertEvent, AuditEvent, BacktestResult, BacktestTrade, BotStatus, Candle, ClosedPaperTrade, DailyMetric, EquityPoint, ForwardEquityPoint, ForwardMetrics, IndicatorSnapshot, MarketStatus, OperationalMetrics, OptimizationRequest, OptimizationRun, PaperAccount, PaperPosition, PaperSession, Readiness, RiskStatus, SignalSnapshot, SymbolMetric, SystemHealth, SystemVersion, TradePlan, ValidationRule, ValidationSnapshot } from "@/types/bot";

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

async function request<T>(path: string): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, { cache: "no-store" });
  if (!response.ok) throw new Error(`API request failed (${response.status})`);
  return response.json() as Promise<T>;
}

async function post<T>(path: string, body: object): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!response.ok) throw new Error(`API request failed (${response.status})`);
  return response.json() as Promise<T>;
}

export const botApi = {
  health: () => request<{ status: string }>("/api/health"),
  status: () => request<BotStatus>("/api/status"),
  marketStatus: () => request<MarketStatus>("/api/market/status"),
  candles: (symbol: string, limit = 500) => request<Candle[]>(`/api/market/${symbol}/candles?limit=${limit}`),
  indicators: (symbol: string) => request<IndicatorSnapshot>(`/api/indicators/${symbol}`),
  indicatorHistory: (symbol: string, limit = 500) => request<IndicatorSnapshot[]>(`/api/indicators/${symbol}/history?limit=${limit}`),
  strategy: (symbol: string) => request<SignalSnapshot>(`/api/strategy/${symbol}`),
  strategyHistory: (symbol: string, limit = 100) => request<SignalSnapshot[]>(`/api/strategy/${symbol}/history?limit=${limit}`),
  risk: (symbol: string) => request<TradePlan>(`/api/risk/${symbol}`),
  riskStatus: () => request<RiskStatus>("/api/risk/status"),
  paperAccount: () => request<PaperAccount>("/api/paper/account"),
  paperPositions: () => request<PaperPosition[]>("/api/paper/positions"),
  paperTrades: (limit = 100) => request<ClosedPaperTrade[]>(`/api/paper/trades?limit=${limit}`),
  runBacktest: (body: { symbols: string[]; timeframe: string; start_time: string; end_time: string }) => post<BacktestResult>("/api/backtest/run", body),
  backtestTrades: (runId: string) => request<BacktestTrade[]>(`/api/backtest/${runId}/trades?limit=100&offset=0`),
  backtestEquity: (runId: string) => request<EquityPoint[]>(`/api/backtest/${runId}/equity`),
  runOptimization: (body: OptimizationRequest) => post<OptimizationRun>("/api/optimization/run", body),
  optimization: (runId: string) => request<OptimizationRun>(`/api/optimization/${runId}`),
  finalEvaluateOptimization: (runId: string) => post<OptimizationRun>(`/api/optimization/${runId}/final-evaluate`, {}),
  paperSession: () => request<PaperSession>("/api/paper/session"),
  paperMetrics: () => request<ForwardMetrics>("/api/paper/metrics"),
  paperDailyMetrics: () => request<DailyMetric[]>("/api/paper/metrics/daily?limit=30"),
  paperEquityMetrics: () => request<ForwardEquityPoint[]>("/api/paper/metrics/equity?limit=1000"),
  paperSymbolMetrics: () => request<SymbolMetric[]>("/api/paper/metrics/symbols"),
  paperAudit: () => request<AuditEvent[]>("/api/paper/audit?limit=25&offset=0"),
  systemHealth: () => request<SystemHealth>("/api/system/health"),
  systemAlerts: () => request<AlertEvent[]>("/api/system/alerts"),
  systemReady: () => request<Readiness>("/api/system/ready"),
  systemVersion: () => request<SystemVersion>("/api/system/version"),
  systemDiagnostics: () => request<Record<string, unknown>>("/api/system/diagnostics"),
  systemMetrics: () => request<OperationalMetrics>("/api/system/metrics"),
  validationStatus: () => request<ValidationSnapshot>("/api/validation/status"),
  validationRules: () => request<ValidationRule[]>("/api/validation/rules"),
  validationHistory: (limit = 20) => request<ValidationSnapshot[]>(`/api/validation/history?limit=${limit}&offset=0`),
};
