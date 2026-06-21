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
  const [message, setMessage] = useState<{ kind: MessageKind; text: string }>({
    kind: "info",
    text: "登录后可以复制模板，用结构化表单编辑策略并保存版本。",
  });
  const [loading, setLoading] = useState(false);

  const selectedStrategy = useMemo(
    () => strategies.find((item) => item.strategy_id === selectedStrategyId) || null,
    [selectedStrategyId, strategies],
  );

  useEffect(() => {
    loadTemplates();
  }, []);

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

  async function restoreSession(accessToken: string) {
    try {
      const me = await request<User>("/auth/me", {}, accessToken);
      setUser(me);
      await loadStrategies(accessToken);
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
