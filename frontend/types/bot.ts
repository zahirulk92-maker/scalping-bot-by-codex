export type ConnectionState = "checking" | "connected" | "offline";

export interface BotStatus {
  mode: "paper";
  starting_balance: number;
  currency: "USDT";
  symbols: string[];
  timeframe: string;
  risk_per_trade: number;
  max_daily_loss: number;
  max_open_positions: number;
}

export type FeedState = "connecting" | "connected" | "reconnecting" | "disconnected" | "stale" | "error";

export interface Candle {
  symbol: string;
  timeframe: string;
  open_time: string;
  close_time: string;
  open: string;
  high: string;
  low: string;
  close: string;
  volume: string;
  is_closed: boolean;
}

export interface SymbolFeedStatus {
  status: FeedState;
  last_update: string | null;
}

export interface MarketStatus {
  exchange: "binance";
  status: FeedState;
  timeframe: string;
  symbols: Record<string, SymbolFeedStatus>;
}

export interface IndicatorSnapshot {
  symbol: string;
  timeframe: string;
  candle_open_time: string | null;
  candle_close_time: string | null;
  close: string | null;
  ema_9: string | null;
  ema_21: string | null;
  rsi_14: string | null;
  atr_14: string | null;
  vwap: string | null;
  volume: string | null;
  volume_ma_20: string | null;
  is_ready: boolean;
  calculated_at: string | null;
}

export type SignalDirection = "long" | "short" | "no_trade";

export interface SignalContext {
  close: string | null;
  ema_9: string | null;
  ema_21: string | null;
  rsi_14: string | null;
  atr_14: string | null;
  vwap: string | null;
  volume: string | null;
  volume_ma_20: string | null;
}

export interface SignalSnapshot {
  symbol: string;
  timeframe: string;
  direction: SignalDirection;
  score: number;
  confidence: number;
  reasons: string[];
  candle_open_time: string | null;
  candle_close_time: string | null;
  generated_at: string | null;
  is_actionable: boolean;
  context: SignalContext;
}

export interface TradePlan {
  symbol: string;
  timeframe: string;
  direction: SignalDirection;
  signal_score: number;
  signal_confidence: number;
  entry_reference_price: string | null;
  stop_loss_price: string | null;
  take_profit_price: string | null;
  stop_distance: string | null;
  stop_distance_bps: string | null;
  planned_risk_amount_usdt: string | null;
  actual_risk_amount_usdt: string | null;
  risk_amount_usdt: string | null;
  position_notional_usdt: string | null;
  estimated_quantity: string | null;
  reward_amount_usdt: string | null;
  risk_reward_ratio: string | null;
  estimated_fees_usdt: string | null;
  estimated_slippage_usdt: string | null;
  net_reward_usdt: string | null;
  approved: boolean;
  rejection_reasons: string[];
  generated_at: string | null;
  source_candle_open_time: string | null;
  source_candle_close_time: string | null;
}

export interface RiskStatus {
  equity: string;
  risk_per_trade: string;
  risk_per_trade_usdt: string;
  max_daily_loss: string;
  max_daily_loss_usdt: string;
  realized_pnl_today: string;
  daily_loss_used: string;
  open_positions: number;
  max_open_positions: number;
  execution_enabled: false;
}

export type PositionStatus = "pending" | "open" | "closed" | "cancelled" | "rejected";
export type ExitReason = "take_profit" | "stop_loss" | "safety_close" | "manual_test_close";

export interface PaperAccount {
  starting_balance: string;
  cash_balance: string;
  equity: string;
  realized_pnl: string;
  realized_pnl_today: string;
  gross_pnl: string;
  fees_paid: string;
  open_position_count: number;
  closed_trade_count: number;
  winning_trade_count: number;
  losing_trade_count: number;
  win_rate: string;
  statistics_day: string;
}

export interface PaperPosition {
  position_id: string;
  plan_identity: string;
  symbol: string;
  timeframe: string;
  direction: SignalDirection;
  entry_reference_price: string;
  entry_fill_price: string;
  current_price: string;
  quantity: string;
  position_notional: string;
  stop_loss_price: string;
  take_profit_price: string;
  risk_amount_usdt: string;
  entry_fee_usdt: string;
  estimated_exit_fee_usdt: string;
  unrealized_gross_pnl: string;
  unrealized_net_pnl: string;
  opened_at: string;
  source_signal_time: string | null;
  source_candle_open_time: string;
  source_candle_close_time: string;
  status: PositionStatus;
}

export interface ClosedPaperTrade {
  trade_id: string;
  position_id: string;
  symbol: string;
  direction: SignalDirection;
  entry_fill_price: string;
  exit_fill_price: string;
  quantity: string;
  gross_pnl_usdt: string;
  fees_usdt: string;
  net_pnl_usdt: string;
  exit_reason: ExitReason;
  opened_at: string;
  closed_at: string;
  source_signal_time: string | null;
}

export interface BacktestTrade {
  symbol: string;
  direction: SignalDirection;
  signal_time: string | null;
  entry_time: string;
  entry_price: string;
  stop_loss_price: string | null;
  take_profit_price: string | null;
  exit_time: string;
  exit_price: string;
  exit_reason: string;
  quantity: string;
  planned_risk_amount: string | null;
  gross_pnl: string;
  fees: string;
  net_pnl: string;
  r_multiple: string | null;
  signal_score: number;
}

export interface EquityPoint { timestamp: string; equity: string; drawdown_usdt: string; drawdown_percent: string; }

export interface PerformanceSlice { trades: number; wins: number; net_pnl: string; profit_factor: string | null; average_r: string | null; }

export interface BacktestResult {
  run_id: string; symbols: string[]; timeframe: string; start_time: string; end_time: string;
  starting_balance: string; ending_balance: string; total_trades: number; wins: number; losses: number;
  net_pnl: string; total_fees: string; total_slippage_cost: string; win_rate: string | null;
  profit_factor: string | null; expectancy_per_trade: string | null; max_drawdown_usdt: string;
  max_drawdown_percent: string; average_r_multiple: string | null; return_percent: string;
  signal_counts: Record<string, number>; approved_plans: number; rejected_plans: number;
  symbol_performance: Record<string, PerformanceSlice>; direction_performance: Record<string, PerformanceSlice>;
  config_snapshot: Record<string, string | number>;
}

export interface EvaluationMetrics {
  total_trades: number; net_pnl: string; return_percent: string; win_rate: string | null;
  profit_factor: string | null; expectancy_per_trade: string | null; average_r_multiple: string | null;
  max_drawdown_usdt: string; max_drawdown_percent: string; total_fees: string;
  symbol_net_pnl: Record<string, string>;
}

export interface CostStressResult { scenario: "normal" | "high" | "stress"; cost_multiplier: number; metrics: EvaluationMetrics; }
export interface WalkForwardFold { train_start: string; train_end: string; validation_start: string; validation_end: string; validation_metrics: EvaluationMetrics; }
export interface OptimizationCandidate {
  candidate_id: string; is_baseline: boolean; parameters: Record<string, number>; train_metrics: EvaluationMetrics;
  validation_metrics: EvaluationMetrics; validation_score: string | null; selection_eligible: boolean;
  warnings: string[]; stability_score: string | null; cost_stress: CostStressResult[]; walk_forward: WalkForwardFold[];
  test_metrics: EvaluationMetrics | null;
}
export interface OptimizationRun {
  run_id: string; created_at: string; symbols: string[]; timeframe: string; start_time: string; end_time: string;
  train_end: string; validation_end: string; holdout_start: string; baseline: OptimizationCandidate;
  candidates: OptimizationCandidate[]; selected_candidate_id: string | null; selection_reason: string;
  invalid_candidates: Record<string, string>; final_holdout_evaluated: boolean;
}
export interface OptimizationRequest {
  symbols: string[]; timeframe: string; start_time: string; end_time: string;
  parameter_grid: Record<string, number[]>; search_method?: "grid"; train_fraction?: number; validation_fraction?: number;
  walk_forward_train_days?: number; walk_forward_validation_days?: number; walk_forward_step_days?: number;
}

export interface PaperSession { session_id: string; started_at: string; starting_balance: string; strategy_profile: "baseline" | "research_candidate"; strategy_config_snapshot: Record<string, unknown>; status: "active" | "paused" | "completed"; }
export interface ForwardMetrics { session_id: string; elapsed_seconds: number; signals: number; actionable_signals: number; risk_approvals: number; risk_rejections: number; paper_entries: number; closed_trades: number; wins: number; losses: number; gross_pnl: string; net_pnl: string; fees: string; win_rate: string | null; profit_factor: string | null; expectancy_per_trade: string | null; average_r_multiple: string | null; max_drawdown_percent: string; current_drawdown_percent: string; current_equity: string; }
export interface DailyMetric { date: string; starting_equity: string; ending_equity: string; trades: number; wins: number; losses: number; net_pnl: string; fees: string; max_drawdown_percent: string; daily_return_percent: string; }
export interface SymbolMetric { symbol: string; trades: number; wins: number; net_pnl: string; win_rate: string | null; profit_factor: string | null; average_r_multiple: string | null; }
export interface SystemHealth { overall: string; database: string; market: string; indicators: string; strategy: string; risk: string; paper_execution: string; recovery: string; freshness: Record<string, string | null>; }
export interface AlertEvent { alert_id: string; code: string; severity: "info" | "warning" | "critical"; message: string; symbol: string | null; created_at: string; count: number; resolved_at: string | null; }
export interface AuditEvent { event_id: string; event_type: string; created_at: string; data: Record<string, unknown>; }
export interface ForwardEquityPoint { timestamp: string; equity: string; }
export interface Readiness { status: "ready" | "not_ready"; degraded: boolean; health: SystemHealth; }
export interface SystemVersion { version: string; environment: string; build_commit: string | null; build_timestamp: string | null; }
export interface OperationalMetrics { market_messages_received: number; valid_candles: number; invalid_candles: number; active_ws_clients: number; signals_generated: number; risk_plans: number; paper_entries: number; paper_closes: number; db_errors: number; }
export type ValidationStatus = "pass" | "fail" | "insufficient_data" | "paused";
export type ValidationRuleStatus = "pass" | "fail" | "warning" | "not_enough_data";
export interface ValidationRule { rule_id: string; name: string; status: ValidationRuleStatus; actual_value: unknown; required_value: unknown; message: string; hard: boolean; }
export interface ValidationSnapshot { snapshot_id: string; status: ValidationStatus; evaluated_at: string; session_id: string; reasons: string[]; warnings: string[]; metrics_snapshot: Record<string, unknown>; rule_results: ValidationRule[]; data_quality_status: string; transition_from: ValidationStatus | null; }

export type MarketWebSocketEvent =
  | { type: "market.candle"; data: Candle }
  | { type: "market.status"; data: MarketStatus }
  | { type: "market.snapshot"; data: { status: MarketStatus; current_candles: Candle[] } }
  | { type: "indicator.snapshot"; data: IndicatorSnapshot }
  | { type: "strategy.signal"; data: SignalSnapshot }
  | { type: "risk.plan"; data: TradePlan }
  | { type: "paper.plan_pending"; data: TradePlan }
  | { type: "paper.position_opened"; data: PaperPosition }
  | { type: "paper.position_updated"; data: PaperPosition }
  | { type: "paper.position_closed"; data: ClosedPaperTrade }
  | { type: "paper.account_updated"; data: PaperAccount };
