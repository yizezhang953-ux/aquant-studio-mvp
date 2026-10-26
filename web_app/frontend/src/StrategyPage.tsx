import { useEffect, useMemo, useState } from "react";
import {
  BacktestReport,
  BacktestRunResponse,
  MarketInstrument,
  MarketKey,
  Notify,
  RuleGroup,
  StrategyJson,
  StrategyRecord,
  StrategyStatus,
  StrategyVersion,
  TemplateDetail,
  TemplateSummary,
  User,
  cleanTemplateName,
  formatNumber,
  frequencyLabels,
  getErrorMessage,
  inferMarket,
  isMarketKey,
  marketAccountLabels,
  marketLabels,
  marketMatchesSymbol,
  marketRuleNotes,
  prettyJson,
  request,
  statusLabels,
  symbolHints,
} from "./api";
import { BacktestView } from "./BacktestView";
import { RuleGroupEditor, describeGroup } from "./RuleEditor";

type StrategyForm = {
  market: MarketKey;
  symbol: string;
  frequency: string;
  startDate: string;
  endDate: string;
  entry: RuleGroup;
  exit: RuleGroup;
  initialCash: string;
  orderSizeValue: string;
  maxPositionPct: string;
  feeRate: string;
  slippageRate: string;
  stopLossPct: string;
  takeProfitPct: string;
  maxDrawdownPct: string;
  maxHoldingBars: string;
  entryPrice: string;
};

const FREQUENCIES = ["1d", "60m", "30m", "15m"];

function str(value: number | null | undefined) {
  return value == null ? "" : String(value);
}

function formFromStrategy(strategy: StrategyJson): StrategyForm {
  const symbol = strategy.universe?.symbols?.[0] || "";
  return {
    market: isMarketKey(strategy.market) ? strategy.market : inferMarket(symbol),
    symbol,
    frequency: strategy.data?.frequency || "1d",
    startDate: strategy.data?.start_date || "2018-01-01",
    endDate: strategy.data?.end_date || "2025-12-31",
    entry: strategy.entry || { logic: "all", conditions: [] },
    exit: strategy.exit || { logic: "any", conditions: [] },
    initialCash: str(strategy.position?.initial_cash ?? 1000000),
    orderSizeValue: str(strategy.position?.order_size_value ?? 0.3),
    maxPositionPct: str(strategy.position?.max_position_pct ?? 0.8),
    feeRate: str(strategy.execution?.commission_rate ?? strategy.execution?.fee_rate ?? 0.00025),
    slippageRate: str(strategy.execution?.slippage_rate ?? 0.0005),
    stopLossPct: str(strategy.risk?.stop_loss_pct),
    takeProfitPct: str(strategy.risk?.take_profit_pct),
    maxDrawdownPct: str(strategy.risk?.max_drawdown_pct),
    maxHoldingBars: str(strategy.risk?.max_holding_bars),
    entryPrice: strategy.execution?.entry_price || "next_open",
  };
}

function num(value: string, fallback: number) {
  const parsed = Number(value);
  return value.trim() !== "" && Number.isFinite(parsed) ? parsed : fallback;
}

function optional(value: string) {
  const parsed = Number(value);
  return value.trim() !== "" && Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

function strategyFromForm(base: StrategyJson, name: string, form: StrategyForm): StrategyJson {
  const { fee_rate: _legacyFee, ...baseExecution } = base.execution || {};
  return {
    ...base,
    name,
    market: form.market,
    universe: { ...(base.universe || {}), type: "single", symbols: [form.symbol.trim().toUpperCase()] },
    data: {
      ...(base.data || {}),
      frequency: form.frequency,
      adjustment: base.data?.adjustment || "forward",
      start_date: form.startDate,
      end_date: form.endDate,
    },
    entry: form.entry,
    exit: form.exit,
    position: {
      ...(base.position || {}),
      initial_cash: num(form.initialCash, 1000000),
      order_size_type: base.position?.order_size_type || "cash_pct",
      order_size_value: num(form.orderSizeValue, 0.3),
      max_position_pct: num(form.maxPositionPct, 0.8),
    },
    execution: {
      ...baseExecution,
      entry_price: form.entryPrice,
      exit_price: form.entryPrice,
      commission_rate: num(form.feeRate, 0.00025),
      slippage_rate: num(form.slippageRate, 0.0005),
    },
    risk: {
      ...(base.risk || {}),
      stop_loss_pct: optional(form.stopLossPct),
      take_profit_pct: optional(form.takeProfitPct),
      max_drawdown_pct: optional(form.maxDrawdownPct),
      max_holding_bars: optional(form.maxHoldingBars) ? Math.round(Number(form.maxHoldingBars)) : null,
    },
    metadata: { ...(base.metadata || {}), updated_from: "structured_editor", updated_at: new Date().toISOString() },
  };
}

/** Fraction stored, percent shown: "0.3" is displayed and typed as 30. */
function PercentInput({
  value,
  onChange,
  placeholder,
  label,
}: {
  value: string;
  onChange: (fraction: string) => void;
  placeholder?: string;
  label: string;
}) {
  const toText = (fraction: string) =>
    fraction.trim() === "" || !Number.isFinite(Number(fraction)) ? "" : String(Number((Number(fraction) * 100).toPrecision(10)));
  const [text, setText] = useState(toText(value));
  useEffect(() => {
    if (Number(text) / 100 !== Number(value) || (value === "" && text !== "")) setText(toText(value));
  }, [value]);
  return (
    <span className="suffix-input">
      <input
        aria-label={label}
        inputMode="decimal"
        value={text}
        placeholder={placeholder}
        onChange={(event) => {
          setText(event.target.value);
          const parsed = Number(event.target.value);
          onChange(event.target.value.trim() === "" ? "" : Number.isFinite(parsed) ? String(parsed / 100) : value);
        }}
      />
      <span>%</span>
    </span>
  );
}

function DataStatus({
  form,
  instrument,
  isAdmin,
  syncing,
  onSync,
  onUseFrequency,
}: {
  form: StrategyForm;
  instrument?: MarketInstrument;
  isAdmin: boolean;
  syncing: boolean;
  onSync: () => void;
  onUseFrequency: (frequency: string) => void;
}) {
  const symbol = form.symbol.trim().toUpperCase();
  if (!symbol) return <p className="data-status warn">先填股票代码，例如 {symbolHints[form.market]}。</p>;
  if (!marketMatchesSymbol(form.market, symbol)) {
    return (
      <p className="data-status bad">
        {form.market === "a_share" ? "A股代码是 6 位数字加 .SH / .SZ / .BJ。" : "港股代码是 5 位数字加 .HK。"}
      </p>
    );
  }
  if (!instrument || instrument.bar_count === 0) {
    return (
      <div className="data-status bad">
        <span>行情库里还没有 {symbol}。</span>
        {isAdmin ? (
          <button type="button" className="text-button strong" onClick={onSync} disabled={syncing}>
            {syncing ? "正在同步…" : `立即同步 ${symbol} 日线`}
          </button>
        ) : (
          <span>请管理员先到「行情数据」同步。</span>
        )}
      </div>
    );
  }
  const range = `${instrument.first_trade_time?.slice(0, 10)} 至 ${instrument.last_trade_time?.slice(0, 10)}`;
  if (!instrument.frequencies.includes(form.frequency)) {
    return (
      <div className="data-status bad">
        <span>
          {symbol} 没有{frequencyLabels[form.frequency] || form.frequency}数据，只有{" "}
          {instrument.frequencies.map((f) => frequencyLabels[f] || f).join("、")}。
        </span>
        <button type="button" className="text-button strong" onClick={() => onUseFrequency(instrument.frequencies[0])}>
          改用{frequencyLabels[instrument.frequencies[0]] || instrument.frequencies[0]}
        </button>
      </div>
    );
  }
  const outside =
    (instrument.last_trade_time && form.startDate > instrument.last_trade_time.slice(0, 10)) ||
    (instrument.first_trade_time && form.endDate < instrument.first_trade_time.slice(0, 10));
  return (
    <p className={outside ? "data-status bad" : "data-status ok"}>
      {instrument.name} · {frequencyLabels[form.frequency] || form.frequency}数据 {range}，共 {formatNumber(instrument.bar_count, 0)} 根
      {outside ? "。回测日期不在这个范围内。" : ""}
      {instrument.exchange === "HK" && !instrument.lot_size ? " · 每手股数未知" : ""}
    </p>
  );
}

type EditorTab = "rules" | "money" | "versions" | "json";

export function StrategyPage({
  token,
  user,
  templates,
  strategies,
  selectedId,
  onSelect,
  instruments,
  reloadStrategies,
  onBacktestSaved,
  syncSymbol,
  notify,
}: {
  token: string;
  user: User;
  templates: TemplateSummary[];
  strategies: StrategyRecord[];
  selectedId: string;
  onSelect: (id: string) => void;
  instruments: MarketInstrument[];
  reloadStrategies: () => Promise<StrategyRecord[]>;
  onBacktestSaved: () => void;
  syncSymbol: (symbol: string, startDate: string) => Promise<boolean>;
  notify: Notify;
}) {
  const selected = useMemo(() => strategies.find((item) => item.strategy_id === selectedId) || null, [strategies, selectedId]);
  const [name, setName] = useState("");
  const [status, setStatus] = useState<StrategyStatus>("draft");
  const [form, setForm] = useState<StrategyForm | null>(null);
  const [jsonText, setJsonText] = useState("{}");
  const [tab, setTab] = useState<EditorTab>("rules");
  const [dirty, setDirty] = useState(false);
  const [versions, setVersions] = useState<StrategyVersion[]>([]);
  const [report, setReport] = useState<BacktestReport | null>(null);
  const [busy, setBusy] = useState<"" | "save" | "run" | "sync" | "copy" | "delete">("");
  const [picking, setPicking] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  useEffect(() => {
    setConfirmDelete(false);
    if (!selected) {
      setForm(null);
      setVersions([]);
      return;
    }
    setName(selected.name);
    setStatus(selected.status);
    setForm(formFromStrategy(selected.strategy));
    setJsonText(prettyJson(selected.strategy));
    setDirty(false);
    setReport(null);
    loadVersions(selected.strategy_id);
  }, [selected?.strategy_id]);

  useEffect(() => {
    if (strategies.length === 0) setPicking(true);
  }, [strategies.length]);

  const instrument = form ? instruments.find((item) => item.symbol === form.symbol.trim().toUpperCase()) : undefined;

  async function loadVersions(strategyId: string) {
    try {
      const payload = await request<{ versions: StrategyVersion[] }>(`/strategies/${strategyId}/versions`, {}, token);
      setVersions(payload.versions);
    } catch (error) {
      notify("error", `版本记录加载失败：${getErrorMessage(error)}`);
    }
  }

  function update<K extends keyof StrategyForm>(key: K, value: StrategyForm[K]) {
    setForm((current) => (current ? { ...current, [key]: value } : current));
    setDirty(true);
  }

  function currentStrategy(): StrategyJson | null {
    if (!selected || !form) return null;
    if (tab === "json") return JSON.parse(jsonText) as StrategyJson;
    return strategyFromForm(selected.strategy, name, form);
  }

  function switchTab(next: EditorTab) {
    if (!selected || !form) return;
    try {
      if (next === "json" && tab !== "json") setJsonText(prettyJson(strategyFromForm(selected.strategy, name, form)));
      if (tab === "json" && next !== "json") setForm(formFromStrategy(JSON.parse(jsonText)));
      setTab(next);
    } catch (error) {
      notify("error", `JSON 格式有误，先改正再切换：${getErrorMessage(error)}`);
    }
  }

  async function copyTemplate(templateId: string) {
    setBusy("copy");
    try {
      const detail = await request<TemplateDetail>(`/templates/${templateId}`);
      const displayName = cleanTemplateName(detail.metadata);
      const created = await request<StrategyRecord>(
        "/strategies",
        {
          method: "POST",
          body: JSON.stringify({
            name: `${displayName}`,
            source_template_id: detail.metadata.template_id,
            strategy: { ...detail.strategy, name: displayName },
          }),
        },
        token,
      );
      await reloadStrategies();
      onSelect(created.strategy_id);
      setPicking(false);
      notify("success", `已新建策略「${displayName}」。先确认股票代码有行情数据，再运行回测。`);
    } catch (error) {
      notify("error", `新建失败：${getErrorMessage(error)}`);
    } finally {
      setBusy("");
    }
  }

  async function save() {
    if (!selected) return;
    setBusy("save");
    try {
      const strategy = currentStrategy();
      const updated = await request<StrategyRecord>(
        `/strategies/${selected.strategy_id}`,
        {
          method: "PUT",
          body: JSON.stringify({ name, status, strategy, change_note: tab === "json" ? "JSON 编辑保存" : "表单编辑保存" }),
        },
        token,
      );
      await reloadStrategies();
      setForm(formFromStrategy(updated.strategy));
      setJsonText(prettyJson(updated.strategy));
      setDirty(false);
      await loadVersions(updated.strategy_id);
      notify("success", "已保存，并生成新版本。");
    } catch (error) {
      notify("error", `保存失败：${getErrorMessage(error)}`);
    } finally {
      setBusy("");
    }
  }

  async function run() {
    if (!selected) return;
    setBusy("run");
    try {
      const strategy = currentStrategy();
      const result = await request<BacktestRunResponse>(
        "/backtests",
        { method: "POST", body: JSON.stringify({ strategy, source_strategy_id: selected.strategy_id }) },
        token,
      );
      setReport(await request<BacktestReport>(`/backtests/mine/${result.backtest_id}`, {}, token));
      onBacktestSaved();
      notify("success", dirty ? "回测完成（用的是当前未保存的设置）。" : "回测完成。");
    } catch (error) {
      notify("error", `回测没有运行：${getErrorMessage(error)}`);
    } finally {
      setBusy("");
    }
  }

  async function remove() {
    if (!selected) return;
    setBusy("delete");
    try {
      await request(`/strategies/${selected.strategy_id}`, { method: "DELETE" }, token);
      const rest = await reloadStrategies();
      onSelect(rest[0]?.strategy_id || "");
      notify("success", `已删除「${selected.name}」。`);
    } catch (error) {
      notify("error", `删除失败：${getErrorMessage(error)}`);
    } finally {
      setBusy("");
      setConfirmDelete(false);
    }
  }

  async function syncForEditor() {
    if (!form) return;
    setBusy("sync");
    const start = `${Math.max(Number(form.startDate.slice(0, 4)) - 1, 2005)}-01-01`;
    await syncSymbol(form.symbol.trim().toUpperCase(), start);
    setBusy("");
  }

  function loadVersion(version: StrategyVersion) {
    setForm(formFromStrategy(version.strategy));
    setJsonText(prettyJson(version.strategy));
    setTab("rules");
    setDirty(true);
    notify("info", `已载入版本 ${version.version}。保存后会生成新版本。`);
  }

  return (
    <div className="studio">
      <aside className="studio-list">
        <div className="list-head">
          <h2>我的策略</h2>
          <button className={picking ? "button" : "button primary"} onClick={() => setPicking(!picking)}>
            {picking ? "收起" : "新建策略"}
          </button>
        </div>
        {picking && (
          <div className="template-picker">
            <p className="muted">从模板开始，之后可以改任何参数。</p>
            {templates.map((template) => {
              const market = (template.default_market || template.market) as MarketKey | undefined;
              return (
                <button key={template.template_id} className="template-item" disabled={busy === "copy"} onClick={() => copyTemplate(template.template_id)}>
                  <strong>{cleanTemplateName(template)}</strong>
                  <span>{template.description}</span>
                  <small>
                    {market && isMarketKey(market) ? marketLabels[market] : "A股"} · {template.default_symbol} ·{" "}
                    {frequencyLabels[template.default_frequency] || template.default_frequency}
                  </small>
                </button>
              );
            })}
          </div>
        )}
        <nav className="strategy-nav" aria-label="策略列表">
          {strategies.map((strategy) => (
            <button
              key={strategy.strategy_id}
              className={strategy.strategy_id === selectedId ? "strategy-link active" : "strategy-link"}
              onClick={() => {
                if (dirty && strategy.strategy_id !== selectedId && !window.confirm("当前策略有未保存的修改，确定切换吗？")) return;
                onSelect(strategy.strategy_id);
              }}
            >
              <strong>{strategy.name}</strong>
              <span>
                {strategy.symbol} · {frequencyLabels[strategy.frequency] || strategy.frequency}
                {strategy.status !== "draft" && ` · ${statusLabels[strategy.status]}`}
              </span>
            </button>
          ))}
        </nav>
      </aside>

      <section className="studio-editor">
        {!selected || !form ? (
          <div className="empty big">
            <h3>{strategies.length ? "选择一个策略" : "还没有策略"}</h3>
            <p>{picking ? "在左边点一个模板，就会新建一个策略。" : "点左上角「新建策略」，从模板开始。"}</p>
          </div>
        ) : (
          <>
            <div className="editor-head">
              <input className="title-input" aria-label="策略名称" value={name} onChange={(e) => { setName(e.target.value); setDirty(true); }} />
              <div className="editor-actions">
                <select aria-label="状态" value={status} onChange={(e) => { setStatus(e.target.value as StrategyStatus); setDirty(true); }}>
                  {(Object.keys(statusLabels) as StrategyStatus[]).map((key) => (
                    <option key={key} value={key}>
                      {statusLabels[key]}
                    </option>
                  ))}
                </select>
                <button className="button" onClick={save} disabled={busy !== ""}>
                  {busy === "save" ? "保存中…" : dirty ? "保存 •" : "保存"}
                </button>
                <button className="button primary" onClick={run} disabled={busy !== ""}>
                  {busy === "run" ? "回测中…" : "运行回测"}
                </button>
              </div>
            </div>

            <div className="setup">
              <div className="segmented" role="radiogroup" aria-label="市场">
                {(Object.keys(marketLabels) as MarketKey[]).map((key) => (
                  <button
                    key={key}
                    role="radio"
                    aria-checked={form.market === key}
                    className={form.market === key ? "active" : ""}
                    title={marketAccountLabels[key]}
                    onClick={() => update("market", key)}
                  >
                    {marketLabels[key]}
                  </button>
                ))}
              </div>
              <div className="setup-grid">
                <label>
                  股票代码
                  <input
                    list="instrument-options"
                    value={form.symbol}
                    placeholder={symbolHints[form.market]}
                    onChange={(e) => update("symbol", e.target.value.toUpperCase())}
                  />
                  <datalist id="instrument-options">
                    {instruments.map((item) => (
                      <option key={item.symbol} value={item.symbol}>
                        {item.name}
                      </option>
                    ))}
                  </datalist>
                </label>
                <label>
                  周期
                  <select value={form.frequency} onChange={(e) => update("frequency", e.target.value)}>
                    {FREQUENCIES.map((f) => (
                      <option key={f} value={f}>
                        {frequencyLabels[f]}
                        {instrument && !instrument.frequencies.includes(f) ? "（无数据）" : ""}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  开始
                  <input type="date" value={form.startDate} onChange={(e) => update("startDate", e.target.value)} />
                </label>
                <label>
                  结束
                  <input type="date" value={form.endDate} onChange={(e) => update("endDate", e.target.value)} />
                </label>
              </div>
              <DataStatus
                form={form}
                instrument={instrument}
                isAdmin={Boolean(user.is_admin)}
                syncing={busy === "sync"}
                onSync={syncForEditor}
                onUseFrequency={(f) => update("frequency", f)}
              />
              <p className="rule-note">{marketRuleNotes[form.market]}</p>
            </div>

            <div className="tabs" role="tablist">
              {([
                ["rules", "买卖规则"],
                ["money", "仓位与风控"],
                ["versions", `版本 ${versions.length}`],
                ["json", "JSON"],
              ] as [EditorTab, string][]).map(([key, label]) => (
                <button key={key} role="tab" aria-selected={tab === key} className={tab === key ? "active" : ""} onClick={() => switchTab(key)}>
                  {label}
                </button>
              ))}
            </div>

            {tab === "rules" && (
              <div className="tab-body">
                <RuleGroupEditor title="买入条件" tone="entry" group={form.entry} onChange={(g) => update("entry", g)} />
                <RuleGroupEditor title="卖出条件" tone="exit" group={form.exit} onChange={(g) => update("exit", g)} />
                <p className="muted small">
                  买入：{describeGroup(form.entry)}。卖出：{describeGroup(form.exit)}。止损、止盈在「仓位与风控」里设置，任一触发都会卖出。
                </p>
              </div>
            )}

            {tab === "money" && (
              <div className="tab-body">
                <div className="field-grid">
                  <label>
                    初始资金（{form.market === "hk_stock" ? "港币" : "人民币"}）
                    <input inputMode="numeric" value={form.initialCash} onChange={(e) => update("initialCash", e.target.value)} />
                  </label>
                  <label>
                    每次买入用资金
                    <PercentInput label="每次买入用资金" value={form.orderSizeValue} onChange={(v) => update("orderSizeValue", v)} />
                  </label>
                  <label>
                    最大仓位
                    <PercentInput label="最大仓位" value={form.maxPositionPct} onChange={(v) => update("maxPositionPct", v)} />
                  </label>
                  <label>
                    成交价
                    <select value={form.entryPrice} onChange={(e) => update("entryPrice", e.target.value)}>
                      <option value="next_open">信号次日开盘价</option>
                      <option value="current_close">信号当日收盘价</option>
                    </select>
                  </label>
                  <label>
                    券商佣金率
                    <PercentInput label="券商佣金率" value={form.feeRate} onChange={(v) => update("feeRate", v)} />
                  </label>
                  <label>
                    滑点
                    <PercentInput label="滑点" value={form.slippageRate} onChange={(v) => update("slippageRate", v)} />
                  </label>
                </div>
                <p className="muted small">印花税、过户费、交易所费用和最低 5 元佣金按市场规则自动计算，这里只填券商佣金。</p>
                <h4 className="sub-head">风险控制</h4>
                <div className="field-grid">
                  <label>
                    止损
                    <PercentInput label="止损" placeholder="不设" value={form.stopLossPct} onChange={(v) => update("stopLossPct", v)} />
                  </label>
                  <label>
                    止盈
                    <PercentInput label="止盈" placeholder="不设" value={form.takeProfitPct} onChange={(v) => update("takeProfitPct", v)} />
                  </label>
                  <label>
                    最大回撤后停止
                    <PercentInput label="最大回撤后停止" placeholder="不设" value={form.maxDrawdownPct} onChange={(v) => update("maxDrawdownPct", v)} />
                  </label>
                  <label>
                    最长持有（根 K 线）
                    <input inputMode="numeric" placeholder="不设" value={form.maxHoldingBars} onChange={(e) => update("maxHoldingBars", e.target.value)} />
                  </label>
                </div>
                <p className="muted small">留空表示不设。回撤超过上限会清仓，并不再开新仓。</p>
              </div>
            )}

            {tab === "versions" && (
              <div className="tab-body">
                {versions.length === 0 ? (
                  <p className="empty">还没有保存过版本。</p>
                ) : (
                  <ol className="version-list">
                    {versions.map((version) => (
                      <li key={version.version}>
                        <div>
                          <strong>版本 {version.version}</strong>
                          <span>{version.change_note}</span>
                          <small>
                            {version.strategy.universe?.symbols?.[0]} · 买入 {describeGroup(version.strategy.entry)}
                          </small>
                        </div>
                        <button className="button small" onClick={() => loadVersion(version)}>
                          载入编辑
                        </button>
                      </li>
                    ))}
                  </ol>
                )}
              </div>
            )}

            {tab === "json" && (
              <div className="tab-body">
                <textarea
                  className="code-editor"
                  aria-label="策略 JSON"
                  value={jsonText}
                  spellCheck={false}
                  onChange={(e) => {
                    setJsonText(e.target.value);
                    setDirty(true);
                  }}
                />
                <p className="muted small">高级用法：直接编辑策略 JSON。切回其他标签页时会自动同步到表单。</p>
              </div>
            )}

            <div className="danger-zone">
              {confirmDelete ? (
                <>
                  <span>删除「{selected.name}」和它的全部版本？</span>
                  <button className="button danger" onClick={remove} disabled={busy !== ""}>
                    确认删除
                  </button>
                  <button className="button" onClick={() => setConfirmDelete(false)}>
                    取消
                  </button>
                </>
              ) : (
                <button className="text-button danger" onClick={() => setConfirmDelete(true)}>
                  删除这个策略
                </button>
              )}
            </div>
          </>
        )}
      </section>

      <section className="studio-result" aria-live="polite">
        {report ? (
          <BacktestView report={report} />
        ) : (
          <div className="empty big">
            <h3>回测结果会显示在这里</h3>
            <p>设置好股票和规则后，点右上角「运行回测」。</p>
          </div>
        )}
      </section>
    </div>
  );
}
