// Types, API client and formatting helpers shared by every page.

// Same origin when the backend serves the built app (start.bat); the Vite dev server (5173) talks to :8000.
export const API_BASE =
  import.meta.env.VITE_API_BASE_URL ||
  (window.location.port === "5173" ? "http://localhost:8000/api/v1" : `${window.location.origin}/api/v1`);

export type MarketKey = "a_share" | "hk_stock" | "hk_connect";
export type StrategyStatus = "draft" | "active" | "archived";
export type LogicMode = "all" | "any";
export type NoticeKind = "info" | "success" | "error";
export type Notify = (kind: NoticeKind, text: string) => void;

export type User = { id: number; email: string; display_name: string; is_admin?: boolean };

export type TemplateSummary = {
  template_id: string;
  name: string;
  category: string;
  risk_level: string;
  default_symbol: string;
  default_frequency: string;
  default_market?: MarketKey;
  market?: MarketKey;
  description: string;
  /** Where a strategy from public research / open-source code came from. */
  source?: { name: string; url: string; license: string };
};

export type TemplateDetail = { metadata: TemplateSummary; strategy: StrategyJson };

export type StrategyRecord = {
  strategy_id: string;
  name: string;
  market: string;
  symbol: string;
  frequency: string;
  source_template_id: string | null;
  status: StrategyStatus;
  strategy: StrategyJson;
};

export type StrategyVersion = { version: number; change_note: string; strategy: StrategyJson };

export type BacktestRunResponse = { backtest_id: string; status: string; metrics: Record<string, number> };

export type ParameterSnapshot = {
  symbol?: string;
  frequency?: string;
  start_date?: string;
  end_date?: string;
  entry_operator?: string;
  entry_value?: number;
  exit_operator?: string;
  exit_value?: number;
  order_size_value?: number;
  max_position_pct?: number;
  stop_loss_pct?: number;
  take_profit_pct?: number;
  max_drawdown_pct?: number;
};

export type BacktestHistoryItem = {
  backtest_id: string;
  strategy_id: string;
  source_strategy_id: string | null;
  strategy_version: number | null;
  strategy_name: string;
  display_name: string;
  symbol: string;
  frequency: string;
  status: string;
  start_date?: string | null;
  end_date?: string | null;
  created_at?: string | null;
  metrics: Record<string, number>;
  parameter_snapshot: ParameterSnapshot | null;
};

export type BacktestTrade = {
  symbol: string;
  entry_time: string;
  exit_time: string;
  entry_price: number;
  exit_price: number;
  quantity: number;
  net_pnl: number;
  return_pct: number;
  exit_reason: string;
};

export type EquityPoint = { trade_time: string; equity: number; drawdown_pct: number; close?: number };

export type BacktestReport = {
  backtest_id?: string;
  strategy_name: string;
  symbol: string;
  frequency: string;
  start_date?: string;
  end_date?: string;
  market?: MarketKey;
  currency?: string;
  lot_size?: number;
  lot_source?: string;
  warnings?: string[];
  metrics: Record<string, number>;
  trades: BacktestTrade[];
  equity_curve: EquityPoint[];
  open_position?: { entry_time: string; quantity: number; entry_price: number; unrealized_pnl: number } | null;
  analysis?: ReportAnalysis;
};

export type DrawdownEpisode = {
  start: string;
  trough: string;
  end: string;
  recovered: boolean;
  depth: number;
  days: number;
  fall_days: number;
  recover_days: number | null;
};

export type ReportAnalysis = {
  days: string[];
  benchmarks: {
    code: string;
    name: string;
    available: boolean;
    total_return?: number;
    annualized_return?: number | null;
    excess_return?: number | null;
    growth?: number[];
  }[];
  monthly_returns: { year: number; months: (number | null)[]; total: number | null }[];
  drawdown: { longest: DrawdownEpisode | null; deepest: DrawdownEpisode | null; count: number; underwater_pct: number | null } | null;
};

export type MarketInstrument = {
  symbol: string;
  name: string;
  market: string;
  exchange: string;
  asset_type: string;
  currency?: string;
  lot_size?: number | null;
  listed_date: string | null;
  status: string;
  bar_count: number;
  first_trade_time: string | null;
  last_trade_time: string | null;
  latest_close: number | null;
  frequencies: string[];
};

export type MarketBar = {
  trade_time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  amount: number;
  adj_factor: number;
  source: string;
};

export type MarketQuality = {
  checked_bar_count: number;
  issue_count: number;
  error_count: number;
  warning_count: number;
  quality_score: number;
  calendar_name: string;
  missing_trading_days: string[];
  issue_summary: Record<string, number>;
  issues: { symbol: string; frequency: string; trade_time: string; issue_type: string; severity: string; message: string }[];
};

export type MarketImportBatch = {
  id: number;
  import_type: string;
  symbol: string;
  frequency: string | null;
  inserted_bars: number;
  updated_bars: number;
  skipped_rows: number;
  issue_count: number;
  status: string;
  created_at: string;
};

export type MarketImportBatchDetail = MarketImportBatch & {
  message: string;
  source: string | null;
  errors: string[];
  payload: Record<string, unknown>;
};

export type MarketSyncResponse = {
  symbol: string;
  fetched_bars: number;
  inserted_bars: number;
  updated_bars: number;
  corporate_actions: number;
  fx_rates: number;
};

export type MarketImportResponse = { symbol: string; inserted_bars: number; updated_bars: number; total_bars: number; message: string };
export type MarketCsvImportResponse = MarketImportResponse & { parsed_rows: number; skipped_rows: number; errors: string[] };

export type Operand = {
  type?: string; // price | indicator | constant
  field?: string;
  name?: string;
  params?: Record<string, number | string>;
  value?: number;
};

export type RuleCondition = { left?: Operand; operator?: string; right?: Operand };
export type RuleGroup = { logic?: LogicMode; conditions?: RuleCondition[] };

export type StrategyJson = {
  schema_version?: string;
  strategy_id?: string;
  name?: string;
  description?: string;
  market?: string;
  universe?: { type?: string; symbols?: string[] };
  data?: { frequency?: string; adjustment?: string; start_date?: string; end_date?: string };
  entry?: RuleGroup;
  exit?: RuleGroup;
  position?: { initial_cash?: number; order_size_type?: string; order_size_value?: number; max_position_pct?: number };
  execution?: {
    entry_price?: string;
    exit_price?: string;
    fee_rate?: number;
    commission_rate?: number;
    min_commission?: number;
    slippage_rate?: number;
    [key: string]: unknown;
  };
  risk?: { stop_loss_pct?: number | null; take_profit_pct?: number | null; max_drawdown_pct?: number | null; max_holding_bars?: number | null };
  metadata?: Record<string, unknown>;
  [key: string]: unknown;
};

// ---- API client ----

const FIELD_LABELS: Record<string, string> = { email: "邮箱", password: "密码", display_name: "显示名称" };

function errorMessage(response: Response, body: any): string {
  const detail = body?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length) {
    // FastAPI validation errors: [{loc: ["body", "password"], type: "string_too_short", ctx: {min_length: 8}}]
    return detail
      .map((item: any) => {
        const field = String(item?.loc?.[item.loc.length - 1] ?? "");
        const label = FIELD_LABELS[field] || field || "输入";
        if (item?.type === "string_too_short") {
          return item?.ctx?.min_length > 1 ? `${label}至少 ${item.ctx.min_length} 个字符` : `请填写${label}`;
        }
        if (item?.type === "string_pattern_mismatch") return `${label}格式不正确`;
        if (item?.type === "missing") return `请填写${label}`;
        return `${label}：${item?.msg ?? "格式不正确"}`;
      })
      .join("；");
  }
  if (detail?.errors?.length) {
    const extra = (detail.errors as string[]).filter((item) => item !== detail.message);
    if (!extra.length) return detail.message;
    const head = detail.message === "strategy is invalid" ? "策略设置有误" : detail.message;
    return `${head}：${extra.join("；")}`;
  }
  return detail?.message || `HTTP ${response.status}: ${response.statusText}`;
}

export async function request<T>(path: string, options: RequestInit = {}, token = ""): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });
  if (!response.ok) throw new Error(errorMessage(response, await response.json().catch(() => null)));
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export async function requestFormData<T>(path: string, formData: FormData, token = ""): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: formData,
  });
  if (!response.ok) throw new Error(errorMessage(response, await response.json().catch(() => null)));
  return response.json() as Promise<T>;
}

export function getErrorMessage(error: unknown) {
  return error instanceof Error ? error.message : "请求失败";
}

// ---- domain labels ----

export const marketLabels: Record<MarketKey, string> = {
  a_share: "A股",
  hk_stock: "港股",
  hk_connect: "港股通",
};

export const marketAccountLabels: Record<MarketKey, string> = {
  a_share: "A股（人民币账户）",
  hk_stock: "港股（港币账户）",
  hk_connect: "港股通（人民币账户买港股）",
};

export const marketRuleNotes: Record<MarketKey, string> = {
  a_share: "100 股整手（科创板 200 股起），T+1，涨跌停，按日期计印花税。",
  hk_stock: "按该股每手股数，T+0，无涨跌停，港币计价。",
  hk_connect: "港币价格按每日汇率折成人民币，只在两地都开市的日子成交，股息按 20% 预扣。",
};

export const symbolHints: Record<MarketKey, string> = {
  a_share: "600519.SH",
  hk_stock: "00700.HK",
  hk_connect: "00700.HK",
};

export const statusLabels: Record<StrategyStatus, string> = { draft: "草稿", active: "使用中", archived: "已归档" };

export const frequencyLabels: Record<string, string> = { "1d": "日线", "60m": "60 分钟", "30m": "30 分钟", "15m": "15 分钟" };

export const templateNames: Record<string, string> = {
  tpl_double_ma_trend: "双均线趋势",
  tpl_rsi_reversal: "RSI 波段反转",
  tpl_price_breakout: "价格突破",
  tpl_volume_breakout: "成交量突破",
  tpl_return_momentum: "收益率动量",
  tpl_hk_connect_ma_trend: "港股通双均线趋势",
  tpl_hk_rsi_pullback: "港股 RSI 回调",
};

export function cleanTemplateName(template: TemplateSummary) {
  return templateNames[template.template_id] || template.name;
}

export function exchangeOf(symbol: string) {
  const parts = symbol.trim().toUpperCase().split(".");
  return parts.length > 1 ? parts[parts.length - 1] : "";
}

export function inferMarket(symbol: string): MarketKey {
  return exchangeOf(symbol) === "HK" ? "hk_connect" : "a_share";
}

export function marketMatchesSymbol(market: MarketKey, symbol: string) {
  const isHk = exchangeOf(symbol) === "HK";
  return market === "a_share" ? !isHk : isHk;
}

export function isMarketKey(value: unknown): value is MarketKey {
  return value === "a_share" || value === "hk_stock" || value === "hk_connect";
}

// ---- formatting ----

export function formatNumber(value: number | null | undefined, digits = 2) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "-";
  return value.toLocaleString("zh-CN", { maximumFractionDigits: digits, minimumFractionDigits: 0 });
}

export function formatMoney(value: number | null | undefined) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "-";
  return value.toLocaleString("zh-CN", { maximumFractionDigits: 0 });
}

export function formatPercent(value: number | null | undefined, signed = false) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "-";
  const text = `${(value * 100).toFixed(2)}%`;
  return signed && value > 0 ? `+${text}` : text;
}

export function formatVersion(value: number | null | undefined) {
  return value ? `v${value}` : "-";
}

/** CSS class for a signed number, Chinese market convention: red up, green down. */
export function trendClass(value: number | null | undefined) {
  if (typeof value !== "number" || !Number.isFinite(value) || value === 0) return "flat";
  return value > 0 ? "up" : "down";
}

/** Server timestamps are UTC without a zone suffix; show them in local time. */
export function formatTimestamp(value: string | null | undefined) {
  if (!value) return "-";
  const iso = value.replace(" ", "T");
  const date = new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`);
  if (Number.isNaN(date.getTime())) return value.slice(0, 16).replace("T", " ");
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export function today() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function prettyJson(value: unknown) {
  return JSON.stringify(value, null, 2);
}
