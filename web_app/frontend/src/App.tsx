import { FormEvent, useEffect, useMemo, useState } from "react";

const API_BASE = "http://localhost:8000/api/v1";

type AuthMode = "login" | "register";
type EditorMode = "form" | "json";
type MessageKind = "info" | "success" | "error";
type StrategyStatus = "draft" | "active" | "archived";
type LogicMode = "all" | "any";

type User = {
  id: number;
  email: string;
  display_name: string;
};

type TemplateSummary = {
  template_id: string;
  name: string;
  category: string;
  risk_level: string;
  default_symbol: string;
  default_frequency: string;
  description: string;
};

type TemplateDetail = {
  metadata: TemplateSummary;
  strategy: StrategyJson;
};

type StrategyRecord = {
  strategy_id: string;
  name: string;
  market: string;
  symbol: string;
  frequency: string;
  source_template_id: string | null;
  status: StrategyStatus;
  strategy: StrategyJson;
};

type StrategyVersion = {
  version: number;
  change_note: string;
  strategy: StrategyJson;
};

type BacktestRunResponse = {
  backtest_id: string;
  status: string;
  metrics: Record<string, number>;
  report_path: string;
};

type BacktestHistoryItem = {
  backtest_id: string;
  strategy_id: string;
  source_strategy_id: string | null;
  strategy_version: number | null;
  strategy_name: string;
  symbol: string;
  frequency: string;
  status: string;
  metrics: Record<string, number>;
  parameter_snapshot: ParameterSnapshot | null;
};

type ParameterSnapshot = {
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

type DiffField = {
  key: keyof ParameterSnapshot;
  label: string;
  format: (value: unknown) => string;
};

type BacktestTrade = {
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

type EquityPoint = {
  trade_time: string;
  equity: number;
  drawdown_pct: number;
};

type BacktestReport = {
  backtest_id?: string;
  strategy_name: string;
  symbol: string;
  frequency: string;
  metrics: Record<string, number>;
  trades: BacktestTrade[];
  equity_curve: EquityPoint[];
};

type MarketInstrument = {
  symbol: string;
  name: string;
  market: string;
  exchange: string;
  asset_type: string;
  listed_date: string | null;
  status: string;
  bar_count: number;
  first_trade_time: string | null;
  last_trade_time: string | null;
  latest_close: number | null;
  frequencies: string[];
};

type MarketBar = {
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

type MarketCoverageItem = {
  symbol: string;
  name: string;
  frequencies: string[];
  bar_count: number;
  first_trade_time: string | null;
  last_trade_time: string | null;
  quality_status: string;
};

type MarketCoverage = {
  market: string;
  instrument_count: number;
  total_bar_count: number;
  coverage: MarketCoverageItem[];
};

type MarketQuality = {
  checked_bar_count: number;
  issue_count: number;
  error_count: number;
  warning_count: number;
  quality_score: number;
  calendar_name: string;
  missing_trading_days: string[];
  issue_summary: Record<string, number>;
  issues: {
    symbol: string;
    frequency: string;
    trade_time: string;
    issue_type: string;
    severity: string;
    message: string;
  }[];
};

type MarketImportDraft = {
  symbol: string;
  name: string;
  exchange: string;
  tradeTime: string;
  close: string;
};

type MarketCsvImportDraft = {
  symbol: string;
  name: string;
  exchange: string;
  frequency: string;
  csvText: string;
};

type MarketFileImportDraft = {
  symbol: string;
  name: string;
  exchange: string;
  frequency: string;
  file: File | null;
};

type MarketImportResponse = {
  symbol: string;
  inserted_bars: number;
  updated_bars: number;
  total_bars: number;
  message: string;
};

type MarketCsvImportResponse = MarketImportResponse & {
  parsed_rows: number;
  skipped_rows: number;
  errors: string[];
};

type MarketImportBatch = {
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

type MarketImportBatchDetail = MarketImportBatch & {
  message: string;
  source: string | null;
  errors: string[];
  payload: Record<string, unknown>;
};

type StrategyJson = {
  schema_version?: string;
  strategy_id?: string;
  name?: string;
  description?: string;
  market?: string;
  universe?: {
    type?: string;
    symbols?: string[];
  };
  data?: {
    frequency?: string;
    adjustment?: string;
    start_date?: string;
    end_date?: string;
  };
  entry?: RuleGroup;
  exit?: RuleGroup;
  position?: {
    initial_cash?: number;
    order_size_type?: string;
    order_size_value?: number;
    max_position_pct?: number;
  };
  execution?: {
    entry_price?: string;
    exit_price?: string;
    fee_rate?: number;
    slippage_rate?: number;
  };
  risk?: {
    stop_loss_pct?: number;
    take_profit_pct?: number;
    max_drawdown_pct?: number;
    max_holding_bars?: number | null;
  };
  metadata?: Record<string, unknown>;
  [key: string]: unknown;
};

type RuleGroup = {
  logic?: LogicMode;
  conditions?: RuleCondition[];
};

type RuleCondition = {
  left?: {
    type?: string;
    field?: string;
  };
  operator?: string;
  right?: {
    type?: string;
    value?: number;
  };
};

type StrategyForm = {
  symbol: string;
  frequency: string;
  startDate: string;
  endDate: string;
  entryLogic: LogicMode;
  entryOperator: string;
  entryValue: string;
  exitLogic: LogicMode;
  exitOperator: string;
  exitValue: string;
  initialCash: string;
  orderSizeValue: string;
  maxPositionPct: string;
  feeRate: string;
  slippageRate: string;
  stopLossPct: string;
  takeProfitPct: string;
  maxDrawdownPct: string;
};

const defaultForm: StrategyForm = {
  symbol: "600519.SH",
  frequency: "1d",
  startDate: "2024-01-02",
  endDate: "2024-01-08",
  entryLogic: "all",
  entryOperator: "gt",
  entryValue: "1680",
  exitLogic: "any",
  exitOperator: "lt",
  exitValue: "1670",
  initialCash: "100000",
  orderSizeValue: "0.3",
  maxPositionPct: "0.8",
  feeRate: "0.0003",
  slippageRate: "0.0005",
  stopLossPct: "0.08",
  takeProfitPct: "0.2",
  maxDrawdownPct: "0.15",
};

const templateNames: Record<string, string> = {
  tpl_double_ma_trend: "双均线趋势策略",
  tpl_rsi_reversal: "RSI 波段反转策略",
  tpl_price_breakout: "价格突破策略",
  tpl_volume_breakout: "成交量突破策略",
  tpl_return_momentum: "收益率动量策略",
};

const operatorLabels: Record<string, string> = {
  gt: "> 大于",
  gte: ">= 大于等于",
  lt: "< 小于",
  lte: "<= 小于等于",
};

const diffFields: DiffField[] = [
  { key: "symbol", label: "股票", format: String },
  { key: "frequency", label: "周期", format: String },
  { key: "start_date", label: "开始", format: String },
  { key: "end_date", label: "结束", format: String },
  { key: "entry_operator", label: "入场方向", format: String },
  { key: "entry_value", label: "入场阈值", format: (value) => formatNumber(value as number) },
  { key: "exit_operator", label: "出场方向", format: String },
  { key: "exit_value", label: "出场阈值", format: (value) => formatNumber(value as number) },
  { key: "order_size_value", label: "单笔仓位", format: (value) => formatPercent(value as number) },
  { key: "max_position_pct", label: "最大仓位", format: (value) => formatPercent(value as number) },
  { key: "stop_loss_pct", label: "止损", format: (value) => formatPercent(value as number) },
  { key: "take_profit_pct", label: "止盈", format: (value) => formatPercent(value as number) },
  { key: "max_drawdown_pct", label: "最大回撤约束", format: (value) => formatPercent(value as number) },
];

const emptyLogin = {
  email: "demo@example.com",
  password: "strong-password-123",
  displayName: "Demo User",
};

function getStoredToken() {
  return window.localStorage.getItem("aquant_token") || "";
}

function getErrorMessage(error: unknown) {
  if (error instanceof Error) return error.message;
  return "请求失败";
}

function prettyJson(value: unknown) {
  return JSON.stringify(value, null, 2);
}

function cleanTemplateName(template: TemplateSummary) {
  return templateNames[template.template_id] || template.name;
}

function formatNumber(value: number | undefined, digits = 2) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "-";
  return value.toLocaleString("zh-CN", { maximumFractionDigits: digits });
}

function formatPercent(value: number | undefined) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "-";
  return `${(value * 100).toFixed(2)}%`;
}

function formatVersion(value: number | null | undefined) {
  return value ? `v${value}` : "v-";
}

function summarizeParams(snapshot: ParameterSnapshot | null) {
  if (!snapshot) return "参数摘要暂无";
  const entry = `${snapshot.entry_operator || "?"} ${snapshot.entry_value ?? "-"}`;
  const exit = `${snapshot.exit_operator || "?"} ${snapshot.exit_value ?? "-"}`;
  const size = snapshot.order_size_value != null ? `${(snapshot.order_size_value * 100).toFixed(0)}%仓位` : "仓位-";
  return `入场 ${entry} / 出场 ${exit} / ${size}`;
}

function normalizeDiffValue(value: unknown) {
  if (typeof value === "number") return Number(value.toFixed(8));
  return value ?? "";
}

function fieldHasDifference(items: BacktestHistoryItem[], field: DiffField) {
  const values = items.map((item) => normalizeDiffValue(item.parameter_snapshot?.[field.key]));
  return new Set(values).size > 1;
}

function formatDiffValue(item: BacktestHistoryItem, field: DiffField) {
  const value = item.parameter_snapshot?.[field.key];
  if (value === undefined || value === null || value === "") return "-";
  return field.format(value);
}

function toNumber(value: string, fallback: number) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function firstCondition(group?: RuleGroup): RuleCondition {
  return group?.conditions?.[0] || {};
}

function formFromStrategy(strategy: StrategyJson): StrategyForm {
  const entry = firstCondition(strategy.entry);
  const exit = firstCondition(strategy.exit);
  const symbol = strategy.universe?.symbols?.[0] || defaultForm.symbol;
  return {
    symbol,
    frequency: strategy.data?.frequency || defaultForm.frequency,
    startDate: strategy.data?.start_date || defaultForm.startDate,
    endDate: strategy.data?.end_date || defaultForm.endDate,
    entryLogic: strategy.entry?.logic || defaultForm.entryLogic,
    entryOperator: entry.operator || defaultForm.entryOperator,
    entryValue: String(entry.right?.value ?? defaultForm.entryValue),
    exitLogic: strategy.exit?.logic || defaultForm.exitLogic,
    exitOperator: exit.operator || defaultForm.exitOperator,
    exitValue: String(exit.right?.value ?? defaultForm.exitValue),
    initialCash: String(strategy.position?.initial_cash ?? defaultForm.initialCash),
    orderSizeValue: String(strategy.position?.order_size_value ?? defaultForm.orderSizeValue),
    maxPositionPct: String(strategy.position?.max_position_pct ?? defaultForm.maxPositionPct),
    feeRate: String(strategy.execution?.fee_rate ?? defaultForm.feeRate),
    slippageRate: String(strategy.execution?.slippage_rate ?? defaultForm.slippageRate),
    stopLossPct: String(strategy.risk?.stop_loss_pct ?? defaultForm.stopLossPct),
    takeProfitPct: String(strategy.risk?.take_profit_pct ?? defaultForm.takeProfitPct),
    maxDrawdownPct: String(strategy.risk?.max_drawdown_pct ?? defaultForm.maxDrawdownPct),
  };
}

function strategyFromForm(base: StrategyJson, name: string, form: StrategyForm): StrategyJson {
  return {
    ...base,
    name,
    market: "a_share",
    universe: {
      ...(base.universe || {}),
      type: "single",
      symbols: [form.symbol.trim() || defaultForm.symbol],
    },
    data: {
      ...(base.data || {}),
      frequency: form.frequency,
      adjustment: base.data?.adjustment || "forward",
      start_date: form.startDate,
      end_date: form.endDate,
    },
    entry: {
      logic: form.entryLogic,
      conditions: [
        {
          left: { type: "price", field: "close" },
          operator: form.entryOperator,
          right: { type: "constant", value: toNumber(form.entryValue, 0) },
        },
      ],
    },
    exit: {
      logic: form.exitLogic,
      conditions: [
        {
          left: { type: "price", field: "close" },
          operator: form.exitOperator,
          right: { type: "constant", value: toNumber(form.exitValue, 0) },
        },
      ],
    },
    position: {
      ...(base.position || {}),
      initial_cash: toNumber(form.initialCash, 100000),
      order_size_type: base.position?.order_size_type || "cash_pct",
      order_size_value: toNumber(form.orderSizeValue, 0.3),
      max_position_pct: toNumber(form.maxPositionPct, 0.8),
    },
    execution: {
      ...(base.execution || {}),
      entry_price: base.execution?.entry_price || "current_close",
      exit_price: base.execution?.exit_price || "current_close",
      fee_rate: toNumber(form.feeRate, 0.0003),
      slippage_rate: toNumber(form.slippageRate, 0.0005),
    },
    risk: {
      ...(base.risk || {}),
      stop_loss_pct: toNumber(form.stopLossPct, 0.08),
      take_profit_pct: toNumber(form.takeProfitPct, 0.2),
      max_drawdown_pct: toNumber(form.maxDrawdownPct, 0.15),
    },
    metadata: {
      ...(base.metadata || {}),
      updated_from: "structured_editor",
      updated_at: new Date().toISOString(),
    },
  };
}

async function request<T>(path: string, options: RequestInit = {}, token = ""): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail = body?.detail;
    const message =
      typeof detail === "string"
        ? detail
        : detail?.message || `HTTP ${response.status}: ${response.statusText}`;
    throw new Error(message);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

async function requestFormData<T>(path: string, formData: FormData, token = ""): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: formData,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail = body?.detail;
    const message =
      typeof detail === "string"
        ? detail
        : detail?.message || `HTTP ${response.status}: ${response.statusText}`;
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export default function App() {
  const [authMode, setAuthMode] = useState<AuthMode>("login");
  const [editorMode, setEditorMode] = useState<EditorMode>("form");
  const [email, setEmail] = useState(emptyLogin.email);
  const [password, setPassword] = useState(emptyLogin.password);
  const [displayName, setDisplayName] = useState(emptyLogin.displayName);
  const [token, setToken] = useState(getStoredToken);
  const [user, setUser] = useState<User | null>(null);
  const [templates, setTemplates] = useState<TemplateSummary[]>([]);
  const [strategies, setStrategies] = useState<StrategyRecord[]>([]);
  const [selectedStrategyId, setSelectedStrategyId] = useState("");
  const [selectedTemplateId, setSelectedTemplateId] = useState("");
  const [strategyName, setStrategyName] = useState("");
  const [strategyStatus, setStrategyStatus] = useState<StrategyStatus>("draft");
  const [editorText, setEditorText] = useState("{}");
  const [strategyForm, setStrategyForm] = useState<StrategyForm>(defaultForm);
  const [versions, setVersions] = useState<StrategyVersion[]>([]);
  const [backtestRun, setBacktestRun] = useState<BacktestRunResponse | null>(null);
  const [backtestReport, setBacktestReport] = useState<BacktestReport | null>(null);
  const [backtestHistory, setBacktestHistory] = useState<BacktestHistoryItem[]>([]);
  const [comparisonIds, setComparisonIds] = useState<string[]>([]);
  const [marketInstruments, setMarketInstruments] = useState<MarketInstrument[]>([]);
  const [selectedMarketSymbol, setSelectedMarketSymbol] = useState("");
  const [marketFrequency, setMarketFrequency] = useState("1d");
  const [marketBars, setMarketBars] = useState<MarketBar[]>([]);
  const [marketCoverage, setMarketCoverage] = useState<MarketCoverage | null>(null);
  const [marketQuality, setMarketQuality] = useState<MarketQuality | null>(null);
  const [marketImports, setMarketImports] = useState<MarketImportBatch[]>([]);
  const [selectedMarketImport, setSelectedMarketImport] = useState<MarketImportBatchDetail | null>(null);
  const [message, setMessage] = useState<{ kind: MessageKind; text: string }>({
    kind: "info",
    text: "登录后可以复制模板，用结构化表单编辑策略并保存版本。",
  });
  const [loading, setLoading] = useState(false);

  const selectedStrategy = useMemo(
    () => strategies.find((item) => item.strategy_id === selectedStrategyId) || null,
    [selectedStrategyId, strategies],
  );
  const selectedMarketInstrument = useMemo(
    () => marketInstruments.find((item) => item.symbol === selectedMarketSymbol) || null,
    [marketInstruments, selectedMarketSymbol],
  );

  useEffect(() => {
    loadTemplates();
    loadMarketOverview();
  }, []);

  useEffect(() => {
    if (selectedMarketSymbol) {
      loadMarketBars(selectedMarketSymbol, marketFrequency);
    }
  }, [selectedMarketSymbol, marketFrequency]);

  useEffect(() => {
    if (!selectedMarketInstrument) return;
    if (selectedMarketInstrument.frequencies.length > 0 && !selectedMarketInstrument.frequencies.includes(marketFrequency)) {
      setMarketFrequency(selectedMarketInstrument.frequencies[0]);
    }
  }, [selectedMarketInstrument, marketFrequency]);

  useEffect(() => {
    if (!token) return;
    window.localStorage.setItem("aquant_token", token);
    restoreSession(token);
  }, [token]);

  useEffect(() => {
    if (!selectedStrategy) {
      setVersions([]);
      return;
    }
    setStrategyName(selectedStrategy.name);
    setStrategyStatus(selectedStrategy.status);
    setEditorText(prettyJson(selectedStrategy.strategy));
    setStrategyForm(formFromStrategy(selectedStrategy.strategy));
    setBacktestRun(null);
    setBacktestReport(null);
    loadVersions(selectedStrategy.strategy_id);
  }, [selectedStrategy]);

  function updateForm<K extends keyof StrategyForm>(key: K, value: StrategyForm[K]) {
    setStrategyForm((current) => current && { ...current, [key]: value });
  }

  async function loadTemplates() {
    try {
      const payload = await request<{ templates: TemplateSummary[] }>("/templates");
      setTemplates(payload.templates);
      if (payload.templates.length > 0) setSelectedTemplateId(payload.templates[0].template_id);
    } catch (error) {
      setMessage({ kind: "error", text: `模板加载失败：${getErrorMessage(error)}` });
    }
  }

  async function loadMarketOverview() {
    try {
      const [instrumentPayload, coveragePayload] = await Promise.all([
        request<{ instruments: MarketInstrument[] }>("/market/instruments"),
        request<MarketCoverage>("/market/coverage"),
      ]);
      setMarketInstruments(instrumentPayload.instruments);
      setMarketCoverage(coveragePayload);
      if (!selectedMarketSymbol && instrumentPayload.instruments.length > 0) {
        setSelectedMarketSymbol(instrumentPayload.instruments[0].symbol);
      }
    } catch (error) {
      setMessage({ kind: "error", text: `行情数据加载失败：${getErrorMessage(error)}` });
    }
  }

  async function loadMarketBars(symbol: string, frequency: string) {
    try {
      const payload = await request<{ bars: MarketBar[] }>(
        `/market/bars?symbol=${encodeURIComponent(symbol)}&frequency=${encodeURIComponent(frequency)}&limit=80`,
      );
      setMarketBars(payload.bars);
      await loadMarketQuality(symbol);
    } catch (error) {
      setMarketBars([]);
      setMessage({ kind: "error", text: `K线数据加载失败：${getErrorMessage(error)}` });
    }
  }

  async function loadMarketQuality(symbol: string) {
    try {
      const payload = await request<MarketQuality>(
        `/market/quality?symbol=${encodeURIComponent(symbol)}&limit=200`,
      );
      setMarketQuality(payload);
    } catch (error) {
      setMarketQuality(null);
      setMessage({ kind: "error", text: `数据质量检查失败：${getErrorMessage(error)}` });
    }
  }

  async function loadMarketImports(accessToken = token) {
    if (!accessToken) return;
    try {
      const payload = await request<{ imports: MarketImportBatch[] }>("/market/imports", {}, accessToken);
      setMarketImports(payload.imports);
      if (payload.imports.length === 0) setSelectedMarketImport(null);
    } catch (error) {
      setMessage({ kind: "error", text: `导入历史加载失败：${getErrorMessage(error)}` });
    }
  }

  async function openMarketImport(batchId: number) {
    if (!token) return;
    try {
      const payload = await request<MarketImportBatchDetail>(`/market/imports/${batchId}`, {}, token);
      setSelectedMarketImport(payload);
    } catch (error) {
      setMessage({ kind: "error", text: `导入详情加载失败：${getErrorMessage(error)}` });
    }
  }

  async function importMarketBar(draft: MarketImportDraft) {
    if (!token) return;
    const close = toNumber(draft.close, 0);
    if (!draft.symbol.trim() || !draft.name.trim() || !draft.tradeTime.trim() || close <= 0) {
      setMessage({ kind: "error", text: "请填写股票代码、名称、日期和大于 0 的收盘价。" });
      return;
    }
    setLoading(true);
    try {
      const symbol = draft.symbol.trim().toUpperCase();
      const result = await request<MarketImportResponse>(
        "/market/import",
        {
          method: "POST",
          body: JSON.stringify({
            instrument: {
              symbol,
              name: draft.name.trim(),
              market: "a_share",
              exchange: draft.exchange,
              asset_type: "stock",
              status: "active",
            },
            bars: [
              {
                symbol,
                frequency: "1d",
                trade_time: draft.tradeTime.trim(),
                open: close,
                high: close,
                low: close,
                close,
                volume: 0,
                amount: 0,
                adj_factor: 1,
                source: "manual",
              },
            ],
          }),
        },
        token,
      );
      await loadMarketOverview();
      setSelectedMarketSymbol(result.symbol);
      setMarketFrequency("1d");
      await loadMarketBars(result.symbol, "1d");
      await loadMarketImports();
      setMessage({
        kind: "success",
        text: `行情已导入：新增 ${result.inserted_bars} 条，更新 ${result.updated_bars} 条。`,
      });
    } catch (error) {
      setMessage({ kind: "error", text: `行情导入失败：${getErrorMessage(error)}` });
    } finally {
      setLoading(false);
    }
  }

  async function importMarketCsv(draft: MarketCsvImportDraft) {
    if (!token) return;
    if (!draft.symbol.trim() || !draft.name.trim() || !draft.csvText.trim()) {
      setMessage({ kind: "error", text: "请填写股票代码、名称和 CSV 内容。" });
      return;
    }
    setLoading(true);
    try {
      const symbol = draft.symbol.trim().toUpperCase();
      const result = await request<MarketCsvImportResponse>(
        "/market/import/csv",
        {
          method: "POST",
          body: JSON.stringify({
            symbol,
            name: draft.name.trim(),
            exchange: draft.exchange,
            frequency: draft.frequency,
            csv_text: draft.csvText,
            source: "csv",
          }),
        },
        token,
      );
      await loadMarketOverview();
      setSelectedMarketSymbol(result.symbol);
      setMarketFrequency(draft.frequency);
      await loadMarketBars(result.symbol, draft.frequency);
      await loadMarketImports();
      setMessage({
        kind: "success",
        text: `CSV 已导入：解析 ${result.parsed_rows} 行，新增 ${result.inserted_bars} 条，更新 ${result.updated_bars} 条。`,
      });
    } catch (error) {
      setMessage({ kind: "error", text: `CSV 导入失败：${getErrorMessage(error)}` });
    } finally {
      setLoading(false);
    }
  }

  async function importMarketFile(draft: MarketFileImportDraft) {
    if (!token) return;
    if (!draft.symbol.trim() || !draft.name.trim() || !draft.file) {
      setMessage({ kind: "error", text: "请选择 CSV 文件，并填写股票代码和名称。" });
      return;
    }
    setLoading(true);
    try {
      const symbol = draft.symbol.trim().toUpperCase();
      const formData = new FormData();
      formData.append("symbol", symbol);
      formData.append("name", draft.name.trim());
      formData.append("exchange", draft.exchange);
      formData.append("frequency", draft.frequency);
      formData.append("file", draft.file);
      const result = await requestFormData<MarketCsvImportResponse>("/market/import/file", formData, token);
      await loadMarketOverview();
      setSelectedMarketSymbol(result.symbol);
      setMarketFrequency(draft.frequency);
      await loadMarketBars(result.symbol, draft.frequency);
      await loadMarketImports();
      setMessage({
        kind: "success",
        text: `文件已导入：解析 ${result.parsed_rows} 行，新增 ${result.inserted_bars} 条，更新 ${result.updated_bars} 条。`,
      });
    } catch (error) {
      setMessage({ kind: "error", text: `文件导入失败：${getErrorMessage(error)}` });
    } finally {
      setLoading(false);
    }
  }

  async function restoreSession(accessToken: string) {
    try {
      const me = await request<User>("/auth/me", {}, accessToken);
      setUser(me);
      await loadStrategies(accessToken);
      await loadBacktestHistory(accessToken);
      await loadMarketImports(accessToken);
      setMessage({ kind: "success", text: `已登录：${me.display_name}` });
    } catch {
      window.localStorage.removeItem("aquant_token");
      setToken("");
      setUser(null);
    }
  }

  async function loadStrategies(accessToken = token) {
    if (!accessToken) return;
    const payload = await request<{ strategies: StrategyRecord[] }>("/strategies", {}, accessToken);
    setStrategies(payload.strategies);
    if (!selectedStrategyId && payload.strategies.length > 0) {
      setSelectedStrategyId(payload.strategies[0].strategy_id);
    }
    if (payload.strategies.length === 0) {
      setSelectedStrategyId("");
      setStrategyName("");
      setEditorText("{}");
      setStrategyForm(defaultForm);
      setVersions([]);
    }
  }

  async function loadVersions(strategyId: string) {
    if (!token) return;
    try {
      const payload = await request<{ versions: StrategyVersion[] }>(
        `/strategies/${strategyId}/versions`,
        {},
        token,
      );
      setVersions(payload.versions);
    } catch (error) {
      setMessage({ kind: "error", text: `版本历史加载失败：${getErrorMessage(error)}` });
    }
  }

  async function loadBacktestHistory(accessToken = token) {
    if (!accessToken) return;
    try {
      const payload = await request<{ backtests: BacktestHistoryItem[] }>("/backtests", {}, accessToken);
      setBacktestHistory(payload.backtests);
      setComparisonIds((current) =>
        current.filter((id) => payload.backtests.some((item) => item.backtest_id === id)),
      );
    } catch (error) {
      setMessage({ kind: "error", text: `回测历史加载失败：${getErrorMessage(error)}` });
    }
  }

  async function handleAuth(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    try {
      const path = authMode === "login" ? "/auth/login" : "/auth/register";
      const body =
        authMode === "login" ? { email, password } : { email, password, display_name: displayName };
      const payload = await request<{ access_token: string; user: User }>(path, {
        method: "POST",
        body: JSON.stringify(body),
      });
      setToken(payload.access_token);
      setUser(payload.user);
      setMessage({ kind: "success", text: `${authMode === "login" ? "登录" : "注册"}成功` });
    } catch (error) {
      setMessage({ kind: "error", text: getErrorMessage(error) });
    } finally {
      setLoading(false);
    }
  }

  async function handleLogout() {
    if (token) await request("/auth/logout", { method: "POST" }, token).catch(() => undefined);
    window.localStorage.removeItem("aquant_token");
    setToken("");
    setUser(null);
    setStrategies([]);
    setBacktestHistory([]);
    setComparisonIds([]);
    setMarketImports([]);
    setSelectedMarketImport(null);
    setSelectedStrategyId("");
    setMessage({ kind: "info", text: "已退出登录。" });
  }

  async function copyTemplate() {
    if (!token || !selectedTemplateId) return;
    setLoading(true);
    try {
      const detail = await request<TemplateDetail>(`/templates/${selectedTemplateId}`);
      const displayName = cleanTemplateName(detail.metadata);
      const created = await request<StrategyRecord>(
        "/strategies",
        {
          method: "POST",
          body: JSON.stringify({
            name: `${displayName} - 我的策略`,
            source_template_id: detail.metadata.template_id,
            strategy: { ...detail.strategy, name: displayName },
          }),
        },
        token,
      );
      await loadStrategies();
      setSelectedStrategyId(created.strategy_id);
      setMessage({ kind: "success", text: "模板已复制为个人策略。" });
    } catch (error) {
      setMessage({ kind: "error", text: `复制失败：${getErrorMessage(error)}` });
    } finally {
      setLoading(false);
    }
  }

  async function saveStrategy() {
    if (!selectedStrategy || !token) return;
    setLoading(true);
    try {
      const parsed =
        editorMode === "json"
          ? (JSON.parse(editorText) as StrategyJson)
          : strategyFromForm(selectedStrategy.strategy, strategyName, strategyForm);
      const updated = await request<StrategyRecord>(
        `/strategies/${selectedStrategy.strategy_id}`,
        {
          method: "PUT",
          body: JSON.stringify({
            name: strategyName,
            status: strategyStatus,
            strategy: parsed,
            change_note: editorMode === "form" ? "Structured editor save" : "JSON editor save",
          }),
        },
        token,
      );
      await loadStrategies();
      setSelectedStrategyId(updated.strategy_id);
      setEditorText(prettyJson(updated.strategy));
      setStrategyForm(formFromStrategy(updated.strategy));
      await loadVersions(updated.strategy_id);
      setMessage({ kind: "success", text: "策略已保存，并生成新版本。" });
    } catch (error) {
      setMessage({ kind: "error", text: `保存失败：${getErrorMessage(error)}` });
    } finally {
      setLoading(false);
    }
  }

  function getCurrentStrategyJson() {
    if (!selectedStrategy) return null;
    if (editorMode === "json") return JSON.parse(editorText) as StrategyJson;
    return strategyFromForm(selectedStrategy.strategy, strategyName, strategyForm);
  }

  async function runCurrentBacktest() {
    if (!selectedStrategy) return;
    setLoading(true);
    try {
      const strategy = getCurrentStrategyJson();
      if (!strategy) return;
      const run = await request<BacktestRunResponse>("/backtests", {
        method: "POST",
        body: JSON.stringify({ strategy, source_strategy_id: selectedStrategy.strategy_id }),
      }, token);
      const report = await request<BacktestReport>(`/backtests/mine/${run.backtest_id}`, {}, token);
      setBacktestRun(run);
      setBacktestReport(report);
      await loadBacktestHistory();
      setMessage({ kind: "success", text: "回测已完成，结果已更新。" });
    } catch (error) {
      setMessage({ kind: "error", text: `回测失败：${getErrorMessage(error)}` });
    } finally {
      setLoading(false);
    }
  }

  async function openHistoricalBacktest(backtestId: string) {
    if (!token) return;
    setLoading(true);
    try {
      const report = await request<BacktestReport>(`/backtests/mine/${backtestId}`, {}, token);
      setBacktestRun({
        backtest_id: backtestId,
        status: "completed",
        metrics: report.metrics,
        report_path: "",
      });
      setBacktestReport(report);
      setMessage({ kind: "info", text: "已载入历史回测报告。" });
    } catch (error) {
      setMessage({ kind: "error", text: `载入历史回测失败：${getErrorMessage(error)}` });
    } finally {
      setLoading(false);
    }
  }

  function toggleComparison(backtestId: string) {
    setComparisonIds((current) => {
      if (current.includes(backtestId)) {
        return current.filter((id) => id !== backtestId);
      }
      return [...current, backtestId].slice(-4);
    });
  }

  function clearComparison() {
    setComparisonIds([]);
  }

  async function deleteStrategy() {
    if (!selectedStrategy || !token) return;
    setLoading(true);
    try {
      await request(`/strategies/${selectedStrategy.strategy_id}`, { method: "DELETE" }, token);
      setMessage({ kind: "success", text: "策略已删除。" });
      setSelectedStrategyId("");
      await loadStrategies();
    } catch (error) {
      setMessage({ kind: "error", text: `删除失败：${getErrorMessage(error)}` });
    } finally {
      setLoading(false);
    }
  }

  function syncJsonFromForm() {
    if (!selectedStrategy) return;
    const next = strategyFromForm(selectedStrategy.strategy, strategyName, strategyForm);
    setEditorText(prettyJson(next));
    setMessage({ kind: "info", text: "已把表单内容同步到 JSON。" });
  }

  function loadVersionIntoEditor(version: StrategyVersion) {
    setEditorText(prettyJson(version.strategy));
    setStrategyForm(formFromStrategy(version.strategy));
    setEditorMode("form");
    setMessage({ kind: "info", text: `已载入版本 ${version.version}，保存后会生成新版本。` });
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <span className="eyebrow">AQuant Studio</span>
          <h1>策略工作台</h1>
        </div>
        <div className="system-state">
          <span>A 股</span>
          <span>模拟环境</span>
          <strong>实盘禁用</strong>
        </div>
      </header>

      <section className={`notice ${message.kind}`}>{message.text}</section>

      {!user ? (
        <section className="auth-layout">
          <form className="panel auth-panel" onSubmit={handleAuth}>
            <div className="panel-title">
              <h2>{authMode === "login" ? "登录账户" : "注册账户"}</h2>
              <div className="segmented">
                <button type="button" className={authMode === "login" ? "active" : ""} onClick={() => setAuthMode("login")}>
                  登录
                </button>
                <button type="button" className={authMode === "register" ? "active" : ""} onClick={() => setAuthMode("register")}>
                  注册
                </button>
              </div>
            </div>
            <label>
              邮箱
              <input value={email} onChange={(event) => setEmail(event.target.value)} />
            </label>
            {authMode === "register" && (
              <label>
                显示名称
                <input value={displayName} onChange={(event) => setDisplayName(event.target.value)} />
              </label>
            )}
            <label>
              密码
              <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} />
            </label>
            <button className="primary-action" type="submit" disabled={loading}>
              {loading ? "处理中" : authMode === "login" ? "登录" : "注册并进入"}
            </button>
          </form>
          <aside className="panel compact-panel">
            <h2>本阶段能力</h2>
            <ul>
              <li>通过表单编辑策略核心参数</li>
              <li>保留 JSON 高级编辑模式</li>
              <li>保存后自动生成策略版本</li>
              <li>继续保持实盘交易禁用</li>
            </ul>
          </aside>
        </section>
      ) : (
        <section className="workspace">
          <aside className="panel sidebar">
            <div className="account-row">
              <div>
                <span>当前用户</span>
                <strong>{user.display_name}</strong>
              </div>
              <button className="ghost-button" onClick={handleLogout}>
                退出
              </button>
            </div>

            <div className="section-block">
              <h2>模板库</h2>
              <select value={selectedTemplateId} onChange={(event) => setSelectedTemplateId(event.target.value)}>
                {templates.map((template) => (
                  <option key={template.template_id} value={template.template_id}>
                    {cleanTemplateName(template)}
                  </option>
                ))}
              </select>
              <button className="primary-action" onClick={copyTemplate} disabled={loading || !selectedTemplateId}>
                复制模板
              </button>
            </div>

            <div className="section-block strategy-list">
              <div className="section-heading">
                <h2>我的策略</h2>
                <span>{strategies.length}</span>
              </div>
              {strategies.length === 0 ? (
                <p className="muted">先从模板复制一个策略。</p>
              ) : (
                strategies.map((strategy) => (
                  <button
                    key={strategy.strategy_id}
                    className={strategy.strategy_id === selectedStrategyId ? "strategy-item active" : "strategy-item"}
                    onClick={() => setSelectedStrategyId(strategy.strategy_id)}
                  >
                    <strong>{strategy.name}</strong>
                    <span>
                      {strategy.symbol} · {strategy.frequency} · {strategy.status}
                    </span>
                  </button>
                ))
              )}
            </div>
          </aside>

          <section className="panel editor-panel">
            <div className="panel-title">
              <h2>策略编辑器</h2>
              <div className="editor-actions">
                <button className="ghost-button danger" onClick={deleteStrategy} disabled={!selectedStrategy || loading}>
                  删除
                </button>
                <button className="ghost-button" onClick={runCurrentBacktest} disabled={!selectedStrategy || loading}>
                  运行回测
                </button>
                <button className="primary-action" onClick={saveStrategy} disabled={!selectedStrategy || loading}>
                  保存策略
                </button>
              </div>
            </div>

            {selectedStrategy ? (
              <>
                <div className="form-grid">
                  <label>
                    策略名称
                    <input value={strategyName} onChange={(event) => setStrategyName(event.target.value)} />
                  </label>
                  <label>
                    状态
                    <select value={strategyStatus} onChange={(event) => setStrategyStatus(event.target.value as StrategyStatus)}>
                      <option value="draft">draft</option>
                      <option value="active">active</option>
                      <option value="archived">archived</option>
                    </select>
                  </label>
                </div>
                <div className="meta-strip">
                  <span>{selectedStrategy.market}</span>
                  <span>{selectedStrategy.symbol}</span>
                  <span>{selectedStrategy.frequency}</span>
                  <span>{selectedStrategy.source_template_id || "custom"}</span>
                </div>
                <div className="segmented editor-switch">
                  <button type="button" className={editorMode === "form" ? "active" : ""} onClick={() => setEditorMode("form")}>
                    表单编辑
                  </button>
                  <button type="button" className={editorMode === "json" ? "active" : ""} onClick={() => setEditorMode("json")}>
                    JSON
                  </button>
                </div>

                {editorMode === "form" ? (
                  <StructuredEditor form={strategyForm} updateForm={updateForm} syncJsonFromForm={syncJsonFromForm} />
                ) : (
                  <textarea
                    className="json-editor"
                    value={editorText}
                    onChange={(event) => setEditorText(event.target.value)}
                    spellCheck={false}
                  />
                )}
              </>
            ) : (
              <div className="empty-state">选择一个策略，或先复制模板生成个人策略。</div>
            )}
          </section>

          <aside className="panel versions-panel">
            <MarketDataPanel
              instruments={marketInstruments}
              selectedSymbol={selectedMarketSymbol}
              selectedInstrument={selectedMarketInstrument}
              frequency={marketFrequency}
              bars={marketBars}
              coverage={marketCoverage}
              quality={marketQuality}
              imports={marketImports}
              selectedImport={selectedMarketImport}
              loading={loading}
              onSymbolChange={setSelectedMarketSymbol}
              onFrequencyChange={setMarketFrequency}
              onImportBar={importMarketBar}
              onImportCsv={importMarketCsv}
              onImportFile={importMarketFile}
              onOpenImport={openMarketImport}
            />

            <div className="backtest-panel">
              <div className="panel-title">
                <h2>回测结果</h2>
                <span className="count-pill">{backtestRun?.status || "待运行"}</span>
              </div>
              {backtestReport ? (
                <BacktestSummary report={backtestReport} />
              ) : (
                <p className="muted">点击“运行回测”后，这里会显示指标、权益曲线和交易明细。</p>
              )}
            </div>

            <div className="backtest-history">
              <div className="panel-title">
                <h2>我的回测记录</h2>
                <span className="count-pill">{backtestHistory.length}</span>
              </div>
              {backtestHistory.length === 0 ? (
                <p className="muted">暂无历史回测。</p>
              ) : (
                <div className="history-list">
                  {backtestHistory.slice(0, 8).map((item) => (
                    <div className="history-row" key={item.backtest_id}>
                      <button onClick={() => openHistoricalBacktest(item.backtest_id)}>
                        <strong>
                          {item.symbol} · {item.frequency} · {formatVersion(item.strategy_version)}
                        </strong>
                        <span>
                          {formatPercent(item.metrics.total_return)} / {formatPercent(item.metrics.max_drawdown)}
                        </span>
                        <small>{summarizeParams(item.parameter_snapshot)}</small>
                      </button>
                      <label className="compare-toggle">
                        <input
                          type="checkbox"
                          checked={comparisonIds.includes(item.backtest_id)}
                          onChange={() => toggleComparison(item.backtest_id)}
                        />
                        对比
                      </label>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <BacktestComparison
              items={backtestHistory.filter((item) => comparisonIds.includes(item.backtest_id))}
              clearComparison={clearComparison}
            />

            <div className="panel-title">
              <h2>版本历史</h2>
              <span className="count-pill">{versions.length}</span>
            </div>
            {versions.length === 0 ? (
              <p className="muted">暂无版本记录。</p>
            ) : (
              <div className="version-list">
                {versions.map((version) => (
                  <button key={version.version} onClick={() => loadVersionIntoEditor(version)}>
                    <strong>版本 {version.version}</strong>
                    <span>{version.change_note}</span>
                  </button>
                ))}
              </div>
            )}
          </aside>
        </section>
      )}
    </main>
  );
}

function BacktestSummary({ report }: { report: BacktestReport }) {
  const metrics = report.metrics || {};
  const equity = report.equity_curve || [];
  const values = equity.map((point) => point.equity);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;

  return (
    <div className="backtest-content">
      <div className="metrics-grid">
        <Metric label="总收益" value={formatPercent(metrics.total_return)} />
        <Metric label="最大回撤" value={formatPercent(metrics.max_drawdown)} />
        <Metric label="胜率" value={formatPercent(metrics.win_rate)} />
        <Metric label="交易数" value={formatNumber(metrics.trade_count, 0)} />
        <Metric label="最终权益" value={formatNumber(metrics.final_equity)} />
        <Metric label="夏普" value={formatNumber(metrics.sharpe)} />
      </div>

      <div className="equity-card">
        <div className="section-heading">
          <h3>权益曲线</h3>
          <span>{equity.length} 点</span>
        </div>
        {equity.length > 0 ? (
          <div className="equity-bars">
            {equity.map((point) => (
              <span
                key={point.trade_time}
                title={`${point.trade_time}: ${formatNumber(point.equity)}`}
                style={{ height: `${30 + ((point.equity - min) / range) * 70}%` }}
              />
            ))}
          </div>
        ) : (
          <p className="muted">暂无权益曲线。</p>
        )}
      </div>

      <div className="trades-table">
        <div className="section-heading">
          <h3>交易明细</h3>
          <span>{report.trades.length}</span>
        </div>
        {report.trades.length === 0 ? (
          <p className="muted">本次回测没有成交。</p>
        ) : (
          report.trades.slice(0, 6).map((trade, index) => (
            <div className="trade-row" key={`${trade.entry_time}-${index}`}>
              <strong>{trade.symbol}</strong>
              <span>{trade.entry_time} → {trade.exit_time}</span>
              <span>{formatNumber(trade.net_pnl)} / {formatPercent(trade.return_pct)}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function MarketDataPanel({
  instruments,
  selectedSymbol,
  selectedInstrument,
  frequency,
  bars,
  coverage,
  quality,
  imports,
  selectedImport,
  loading,
  onSymbolChange,
  onFrequencyChange,
  onImportBar,
  onImportCsv,
  onImportFile,
  onOpenImport,
}: {
  instruments: MarketInstrument[];
  selectedSymbol: string;
  selectedInstrument: MarketInstrument | null;
  frequency: string;
  bars: MarketBar[];
  coverage: MarketCoverage | null;
  quality: MarketQuality | null;
  imports: MarketImportBatch[];
  selectedImport: MarketImportBatchDetail | null;
  loading: boolean;
  onSymbolChange: (value: string) => void;
  onFrequencyChange: (value: string) => void;
  onImportBar: (draft: MarketImportDraft) => Promise<void>;
  onImportCsv: (draft: MarketCsvImportDraft) => Promise<void>;
  onImportFile: (draft: MarketFileImportDraft) => Promise<void>;
  onOpenImport: (batchId: number) => Promise<void>;
}) {
  const [importDraft, setImportDraft] = useState<MarketImportDraft>({
    symbol: selectedSymbol || "600519.SH",
    name: selectedInstrument?.name || "贵州茅台",
    exchange: selectedInstrument?.exchange || "SH",
    tradeTime: "",
    close: selectedInstrument?.latest_close ? String(selectedInstrument.latest_close) : "",
  });
  const [csvDraft, setCsvDraft] = useState<MarketCsvImportDraft>({
    symbol: selectedSymbol || "600519.SH",
    name: selectedInstrument?.name || "贵州茅台",
    exchange: selectedInstrument?.exchange || "SH",
    frequency,
    csvText: "trade_time,open,high,low,close,volume,amount\n2024-02-01,1660,1680,1650,1672,1000,1672000",
  });
  const [fileDraft, setFileDraft] = useState<MarketFileImportDraft>({
    symbol: selectedSymbol || "600519.SH",
    name: selectedInstrument?.name || "贵州茅台",
    exchange: selectedInstrument?.exchange || "SH",
    frequency,
    file: null,
  });
  const closes = bars.map((bar) => bar.close);
  const minClose = Math.min(...closes);
  const maxClose = Math.max(...closes);
  const closeRange = maxClose - minClose || 1;
  const coverageItem = coverage?.coverage.find((item) => item.symbol === selectedSymbol);
  const frequencies = selectedInstrument?.frequencies.length ? selectedInstrument.frequencies : ["1d"];

  useEffect(() => {
    if (!selectedInstrument) return;
    setImportDraft((current) => ({
      ...current,
      symbol: selectedInstrument.symbol,
      name: selectedInstrument.name,
      exchange: selectedInstrument.exchange,
      close: selectedInstrument.latest_close ? String(selectedInstrument.latest_close) : current.close,
    }));
    setCsvDraft((current) => ({
      ...current,
      symbol: selectedInstrument.symbol,
      name: selectedInstrument.name,
      exchange: selectedInstrument.exchange,
    }));
    setFileDraft((current) => ({
      ...current,
      symbol: selectedInstrument.symbol,
      name: selectedInstrument.name,
      exchange: selectedInstrument.exchange,
    }));
  }, [selectedInstrument]);

  useEffect(() => {
    setCsvDraft((current) => ({ ...current, frequency }));
    setFileDraft((current) => ({ ...current, frequency }));
  }, [frequency]);

  function updateDraft<K extends keyof MarketImportDraft>(key: K, value: MarketImportDraft[K]) {
    setImportDraft((current) => ({ ...current, [key]: value }));
  }

  function updateCsvDraft<K extends keyof MarketCsvImportDraft>(key: K, value: MarketCsvImportDraft[K]) {
    setCsvDraft((current) => ({ ...current, [key]: value }));
  }

  function updateFileDraft<K extends keyof MarketFileImportDraft>(key: K, value: MarketFileImportDraft[K]) {
    setFileDraft((current) => ({ ...current, [key]: value }));
  }

  async function handleImport(event: FormEvent) {
    event.preventDefault();
    await onImportBar(importDraft);
  }

  async function handleCsvImport(event: FormEvent) {
    event.preventDefault();
    await onImportCsv(csvDraft);
  }

  async function handleFileImport(event: FormEvent) {
    event.preventDefault();
    await onImportFile(fileDraft);
  }

  return (
    <div className="market-panel">
      <div className="panel-title">
        <h2>行情数据</h2>
        <span className="count-pill">{coverage?.instrument_count || instruments.length}</span>
      </div>

      <div className="market-controls">
        <label>
          标的
          <select value={selectedSymbol} onChange={(event) => onSymbolChange(event.target.value)}>
            {instruments.map((instrument) => (
              <option key={instrument.symbol} value={instrument.symbol}>
                {instrument.symbol} {instrument.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          频率
          <select value={frequency} onChange={(event) => onFrequencyChange(event.target.value)}>
            {frequencies.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </label>
      </div>

      {selectedInstrument ? (
        <>
          <div className="market-stats">
            <Metric label="最新收盘" value={formatNumber(selectedInstrument.latest_close || undefined)} />
            <Metric label="K线数量" value={formatNumber(coverageItem?.bar_count || selectedInstrument.bar_count, 0)} />
            <Metric label="起始日期" value={selectedInstrument.first_trade_time || "-"} />
            <Metric label="结束日期" value={selectedInstrument.last_trade_time || "-"} />
          </div>
          <div className="market-quality">
            <span>{selectedInstrument.exchange}</span>
            <span>{coverageItem?.quality_status || "ready"}</span>
            <span>{coverage?.total_bar_count || selectedInstrument.bar_count} bars</span>
            <span>{quality ? `${quality.issue_count} issues` : "quality -"}</span>
          </div>
          <div className="market-chart">
            <div className="section-heading">
              <h3>收盘价走势</h3>
              <span>{bars.length}</span>
            </div>
            {bars.length > 0 ? (
              <div className="price-bars">
                {bars.map((bar) => (
                  <span
                    key={bar.trade_time}
                    title={`${bar.trade_time}: ${formatNumber(bar.close)}`}
                    style={{ height: `${24 + ((bar.close - minClose) / closeRange) * 76}%` }}
                  />
                ))}
              </div>
            ) : (
              <p className="muted">当前频率暂无K线数据。</p>
            )}
          </div>
          <div className="quality-box">
            <div className="section-heading">
              <h3>质量检查</h3>
              <span>{quality ? `${quality.quality_score}/100` : "-"}</span>
            </div>
            {quality && (
              <>
                <div className="quality-score">
                  <strong>{quality.quality_score}</strong>
                  <span>{quality.error_count} errors / {quality.warning_count} warnings</span>
                  <small>{quality.checked_bar_count} bars checked</small>
                </div>
                <div className="calendar-strip">
                  <span>{quality.calendar_name || "calendar -"}</span>
                  <span>{quality.missing_trading_days.length} missing days</span>
                </div>
                {Object.keys(quality.issue_summary).length > 0 && (
                  <div className="quality-summary">
                    {Object.entries(quality.issue_summary).map(([key, value]) => (
                      <span key={key}>{key}: {value}</span>
                    ))}
                  </div>
                )}
                {quality.missing_trading_days.length > 0 && (
                  <div className="missing-days">
                    {quality.missing_trading_days.slice(0, 6).map((day) => (
                      <span key={day}>{day}</span>
                    ))}
                  </div>
                )}
              </>
            )}
            {quality && quality.issue_count > 0 ? (
              quality.issues.slice(0, 4).map((issue) => (
                <p
                  key={`${issue.symbol}-${issue.trade_time}-${issue.issue_type}`}
                  className={`quality-issue ${issue.severity}`}
                >
                  {issue.trade_time} {issue.issue_type} · {issue.severity}
                </p>
              ))
            ) : (
              <p className="muted">最近数据未发现 OHLC 或成交量异常。</p>
            )}
          </div>
          <form className="market-import" onSubmit={handleImport}>
            <div className="section-heading">
              <h3>手动导入日线</h3>
            </div>
            <div className="form-grid compact">
              <label>
                代码
                <input value={importDraft.symbol} onChange={(event) => updateDraft("symbol", event.target.value)} />
              </label>
              <label>
                名称
                <input value={importDraft.name} onChange={(event) => updateDraft("name", event.target.value)} />
              </label>
              <label>
                交易所
                <select value={importDraft.exchange} onChange={(event) => updateDraft("exchange", event.target.value)}>
                  <option value="SH">SH</option>
                  <option value="SZ">SZ</option>
                </select>
              </label>
              <label>
                日期
                <input
                  placeholder="2024-02-01"
                  value={importDraft.tradeTime}
                  onChange={(event) => updateDraft("tradeTime", event.target.value)}
                />
              </label>
              <label>
                收盘价
                <input value={importDraft.close} onChange={(event) => updateDraft("close", event.target.value)} />
              </label>
            </div>
            <button className="ghost-button" type="submit" disabled={loading}>
              导入/更新
            </button>
          </form>
          <form className="market-import csv-import" onSubmit={handleCsvImport}>
            <div className="section-heading">
              <h3>CSV 批量导入</h3>
            </div>
            <div className="form-grid compact">
              <label>
                代码
                <input value={csvDraft.symbol} onChange={(event) => updateCsvDraft("symbol", event.target.value)} />
              </label>
              <label>
                名称
                <input value={csvDraft.name} onChange={(event) => updateCsvDraft("name", event.target.value)} />
              </label>
              <label>
                频率
                <select value={csvDraft.frequency} onChange={(event) => updateCsvDraft("frequency", event.target.value)}>
                  <option value="1d">1d</option>
                  <option value="15m">15m</option>
                  <option value="30m">30m</option>
                  <option value="60m">60m</option>
                </select>
              </label>
            </div>
            <label>
              CSV
              <textarea
                className="csv-editor"
                value={csvDraft.csvText}
                onChange={(event) => updateCsvDraft("csvText", event.target.value)}
                spellCheck={false}
              />
            </label>
            <button className="ghost-button" type="submit" disabled={loading}>
              批量导入
            </button>
          </form>
          <form className="market-import file-import" onSubmit={handleFileImport}>
            <div className="section-heading">
              <h3>CSV 文件上传</h3>
            </div>
            <div className="form-grid compact">
              <label>
                代码
                <input value={fileDraft.symbol} onChange={(event) => updateFileDraft("symbol", event.target.value)} />
              </label>
              <label>
                名称
                <input value={fileDraft.name} onChange={(event) => updateFileDraft("name", event.target.value)} />
              </label>
              <label>
                频率
                <select value={fileDraft.frequency} onChange={(event) => updateFileDraft("frequency", event.target.value)}>
                  <option value="1d">1d</option>
                  <option value="15m">15m</option>
                  <option value="30m">30m</option>
                  <option value="60m">60m</option>
                </select>
              </label>
            </div>
            <label>
              文件
              <input
                type="file"
                accept=".csv,text/csv"
                onChange={(event) => updateFileDraft("file", event.target.files?.[0] || null)}
              />
            </label>
            <button className="ghost-button" type="submit" disabled={loading}>
              上传导入
            </button>
          </form>
          <div className="import-history">
            <div className="section-heading">
              <h3>导入批次</h3>
              <span>{imports.length}</span>
            </div>
            {imports.length === 0 ? (
              <p className="muted">暂无导入批次。</p>
            ) : (
              imports.slice(0, 5).map((item) => (
                <button
                  className={selectedImport?.id === item.id ? "import-row active" : "import-row"}
                  key={item.id}
                  type="button"
                  onClick={() => onOpenImport(item.id)}
                >
                  <strong>
                    {item.symbol} · {item.import_type}
                  </strong>
                  <span>
                    +{item.inserted_bars} / 更新 {item.updated_bars} / 跳过 {item.skipped_rows}
                  </span>
                  <small>{item.status} · {item.frequency || "-"} · {item.created_at}</small>
                </button>
              ))
            )}
            {selectedImport && (
              <div className="import-detail">
                <div className="section-heading">
                  <h3>批次详情</h3>
                  <span>{selectedImport.status}</span>
                </div>
                <p>{selectedImport.message}</p>
                <small>{selectedImport.source || "source -"}</small>
                {selectedImport.errors.length > 0 ? (
                  <div className="import-errors">
                    {selectedImport.errors.slice(0, 4).map((error, index) => (
                      <span key={`${selectedImport.id}-${index}`}>{error}</span>
                    ))}
                  </div>
                ) : (
                  <p className="muted">暂无错误行。</p>
                )}
              </div>
            )}
          </div>
        </>
      ) : (
        <p className="muted">暂无可浏览的行情标的。</p>
      )}
    </div>
  );
}

function BacktestComparison({
  items,
  clearComparison,
}: {
  items: BacktestHistoryItem[];
  clearComparison: () => void;
}) {
  if (items.length === 0) {
    return (
      <div className="comparison-panel">
        <div className="panel-title">
          <h2>回测对比</h2>
          <span className="count-pill">0</span>
        </div>
        <p className="muted">在回测记录里勾选“对比”，最多比较 4 条。</p>
      </div>
    );
  }

  return (
    <div className="comparison-panel">
      <div className="panel-title">
        <h2>回测对比</h2>
        <button className="ghost-button mini" type="button" onClick={clearComparison}>
          清空
        </button>
      </div>
      <div className="comparison-table">
        <div className="comparison-row header">
          <span>标的</span>
          <span>版本</span>
          <span>收益</span>
          <span>回撤</span>
          <span>胜率</span>
          <span>交易</span>
        </div>
        {items.map((item) => (
          <div className="comparison-row" key={item.backtest_id}>
            <span title={item.source_strategy_id || item.strategy_id}>
              {item.symbol}
              <small>{item.frequency}</small>
            </span>
            <span>{formatVersion(item.strategy_version)}</span>
            <strong>{formatPercent(item.metrics.total_return)}</strong>
            <span>{formatPercent(item.metrics.max_drawdown)}</span>
            <span>{formatPercent(item.metrics.win_rate)}</span>
            <span>{formatNumber(item.metrics.trade_count, 0)}</span>
            <small className="comparison-params">{summarizeParams(item.parameter_snapshot)}</small>
          </div>
        ))}
      </div>
      <ParameterDiff items={items} />
    </div>
  );
}

function ParameterDiff({ items }: { items: BacktestHistoryItem[] }) {
  if (items.length < 2) {
    return <p className="muted">至少选择 2 条回测后显示参数差异。</p>;
  }
  const changedFields = diffFields.filter((field) => fieldHasDifference(items, field));
  if (changedFields.length === 0) {
    return <p className="muted">所选回测的核心参数一致。</p>;
  }
  return (
    <div className="diff-panel">
      <div className="section-heading">
        <h3>参数差异</h3>
        <span>{changedFields.length}</span>
      </div>
      <div className="diff-table">
        <div className="diff-row header">
          <span>参数</span>
          {items.map((item) => (
            <span key={item.backtest_id}>{formatVersion(item.strategy_version)}</span>
          ))}
        </div>
        {changedFields.map((field) => (
          <div className="diff-row changed" key={field.key}>
            <strong>{field.label}</strong>
            {items.map((item) => (
              <span key={item.backtest_id}>{formatDiffValue(item, field)}</span>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

function StructuredEditor({
  form,
  updateForm,
  syncJsonFromForm,
}: {
  form: StrategyForm;
  updateForm: <K extends keyof StrategyForm>(key: K, value: StrategyForm[K]) => void;
  syncJsonFromForm: () => void;
}) {
  return (
    <div className="structured-editor">
      <section className="editor-section">
        <div className="section-heading">
          <h3>标的与周期</h3>
        </div>
        <div className="form-grid three">
          <label>
            股票代码
            <input value={form.symbol} onChange={(event) => updateForm("symbol", event.target.value)} />
          </label>
          <label>
            频率
            <select value={form.frequency} onChange={(event) => updateForm("frequency", event.target.value)}>
              <option value="1d">1d 日线</option>
              <option value="60m">60m</option>
              <option value="30m">30m</option>
              <option value="15m">15m</option>
            </select>
          </label>
          <label>
            开始日期
            <input value={form.startDate} onChange={(event) => updateForm("startDate", event.target.value)} />
          </label>
          <label>
            结束日期
            <input value={form.endDate} onChange={(event) => updateForm("endDate", event.target.value)} />
          </label>
        </div>
      </section>

      <section className="editor-section">
        <div className="section-heading">
          <h3>交易规则</h3>
        </div>
        <div className="rule-grid">
          <RuleBox
            title="入场"
            logic={form.entryLogic}
            operator={form.entryOperator}
            value={form.entryValue}
            onLogic={(value) => updateForm("entryLogic", value)}
            onOperator={(value) => updateForm("entryOperator", value)}
            onValue={(value) => updateForm("entryValue", value)}
          />
          <RuleBox
            title="出场"
            logic={form.exitLogic}
            operator={form.exitOperator}
            value={form.exitValue}
            onLogic={(value) => updateForm("exitLogic", value)}
            onOperator={(value) => updateForm("exitOperator", value)}
            onValue={(value) => updateForm("exitValue", value)}
          />
        </div>
      </section>

      <section className="editor-section">
        <div className="section-heading">
          <h3>资金与执行</h3>
        </div>
        <div className="form-grid three">
          <label>
            初始资金
            <input value={form.initialCash} onChange={(event) => updateForm("initialCash", event.target.value)} />
          </label>
          <label>
            单笔资金比例
            <input value={form.orderSizeValue} onChange={(event) => updateForm("orderSizeValue", event.target.value)} />
          </label>
          <label>
            最大仓位比例
            <input value={form.maxPositionPct} onChange={(event) => updateForm("maxPositionPct", event.target.value)} />
          </label>
          <label>
            手续费率
            <input value={form.feeRate} onChange={(event) => updateForm("feeRate", event.target.value)} />
          </label>
          <label>
            滑点率
            <input value={form.slippageRate} onChange={(event) => updateForm("slippageRate", event.target.value)} />
          </label>
        </div>
      </section>

      <section className="editor-section">
        <div className="section-heading">
          <h3>风险控制</h3>
        </div>
        <div className="form-grid three">
          <label>
            止损比例
            <input value={form.stopLossPct} onChange={(event) => updateForm("stopLossPct", event.target.value)} />
          </label>
          <label>
            止盈比例
            <input value={form.takeProfitPct} onChange={(event) => updateForm("takeProfitPct", event.target.value)} />
          </label>
          <label>
            最大回撤比例
            <input value={form.maxDrawdownPct} onChange={(event) => updateForm("maxDrawdownPct", event.target.value)} />
          </label>
        </div>
      </section>

      <button className="ghost-button sync-button" type="button" onClick={syncJsonFromForm}>
        同步到 JSON 预览
      </button>
    </div>
  );
}

function RuleBox({
  title,
  logic,
  operator,
  value,
  onLogic,
  onOperator,
  onValue,
}: {
  title: string;
  logic: LogicMode;
  operator: string;
  value: string;
  onLogic: (value: LogicMode) => void;
  onOperator: (value: string) => void;
  onValue: (value: string) => void;
}) {
  return (
    <div className="rule-box">
      <strong>{title}</strong>
      <div className="form-grid compact">
        <label>
          逻辑
          <select value={logic} onChange={(event) => onLogic(event.target.value as LogicMode)}>
            <option value="all">all</option>
            <option value="any">any</option>
          </select>
        </label>
        <label>
          条件
          <select value={operator} onChange={(event) => onOperator(event.target.value)}>
            {Object.entries(operatorLabels).map(([key, label]) => (
              <option key={key} value={key}>
                收盘价 {label}
              </option>
            ))}
          </select>
        </label>
        <label>
          阈值
          <input value={value} onChange={(event) => onValue(event.target.value)} />
        </label>
      </div>
    </div>
  );
}
