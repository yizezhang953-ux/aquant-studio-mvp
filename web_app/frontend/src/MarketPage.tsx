import { FormEvent, MouseEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  MarketBar,
  MarketCsvImportResponse,
  MarketImportBatch,
  MarketImportBatchDetail,
  MarketImportResponse,
  MarketInstrument,
  MarketQuality,
  Notify,
  exchangeOf,
  formatNumber,
  formatTimestamp,
  frequencyLabels,
  getErrorMessage,
  request,
  requestFormData,
  today,
  trendClass,
} from "./api";
import { PriceChart } from "./charts";
import { ContextMenu, MenuItem, MenuState } from "./ContextMenu";

const IMPORT_TYPES: Record<string, string> = {
  data_source_sync: "同步",
  csv: "CSV 粘贴",
  csv_file: "CSV 文件",
  manual: "手动",
  api: "接口导入",
};

const RANGES: [string, number][] = [
  ["3 个月", 63],
  ["1 年", 250],
  ["3 年", 750],
  ["全部", 5000],
];

type ImportTab = "csv" | "file" | "single";

function SyncBar({
  isAdmin,
  busy,
  onSync,
  onBoardLots,
}: {
  isAdmin: boolean;
  busy: string;
  onSync: (provider: string, symbol: string, start: string, end: string) => void;
  onBoardLots: () => void;
}) {
  const [provider, setProvider] = useState("tencent");
  const [symbol, setSymbol] = useState("");
  const [start, setStart] = useState("2015-01-01");
  const [end, setEnd] = useState(today());
  if (!isAdmin) {
    return <p className="sync-bar muted">行情数据所有账户共用。同步和导入需要管理员账户（本地运行时是第一个注册的账户）。</p>;
  }
  return (
    <form
      className="sync-bar"
      onSubmit={(event) => {
        event.preventDefault();
        onSync(provider, symbol.trim().toUpperCase(), start, end);
      }}
    >
      <label>
        股票代码
        <input value={symbol} placeholder="600519.SH 或 00700.HK" onChange={(e) => setSymbol(e.target.value.toUpperCase())} />
      </label>
      <label>
        从
        <input type="date" value={start} onChange={(e) => setStart(e.target.value)} />
      </label>
      <label>
        到
        <input type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
      </label>
      <label>
        数据源
        <select value={provider} onChange={(e) => setProvider(e.target.value)}>
          <option value="tencent">腾讯行情（真实日线）</option>
          <option value="demo">合成演示数据</option>
        </select>
      </label>
      <button className="button primary" type="submit" disabled={busy !== "" || !symbol.trim()}>
        {busy === "sync" ? "同步中…" : "同步日线"}
      </button>
      <button className="button" type="button" disabled={busy !== ""} onClick={onBoardLots} title="从港交所下载每只港股的每手股数">
        {busy === "lots" ? "更新中…" : "更新港股每手股数"}
      </button>
      <p className="muted small full">港股会顺带下载港币兑人民币汇率（港股通回测要用）；分红送股从复权数据推算。已有数据会被更新，不会重复。</p>
    </form>
  );
}

type IndexInfo = { code: string; name: string; start: string | null; end: string | null; bars: number };

/** Benchmark indices for report comparisons: status for everyone, sync for admins. */
function IndexBar({ token, isAdmin, notify }: { token: string; isAdmin: boolean; notify: Notify }) {
  const [indices, setIndices] = useState<IndexInfo[]>([]);
  const [start, setStart] = useState("2010-01-01");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    request<{ indices: IndexInfo[] }>("/market/indices", {}, token)
      .then((r) => setIndices(r.indices))
      .catch(() => undefined);
  }, [token]);

  async function sync() {
    setBusy(true);
    try {
      const r = await request<{ indices: IndexInfo[]; results: { name: string; ok: boolean; bars: number; error: string | null }[] }>(
        "/market/indices/sync",
        { method: "POST", body: JSON.stringify({ provider_id: "tencent", start_date: start, end_date: today() }) },
        token,
      );
      setIndices(r.indices);
      const failed = r.results.filter((x) => !x.ok);
      if (failed.length) notify("error", failed.map((x) => `${x.name} 同步失败：${x.error}`).join("；"));
      else notify("success", `已同步 ${r.results.map((x) => `${x.name} ${x.bars} 天`).join("、")}。打开任何回测报告都会和它们对比。`);
    } catch (error) {
      notify("error", `指数同步失败：${getErrorMessage(error)}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="index-bar">
      <strong>指数基准</strong>
      {indices.map((i) => (
        <span key={i.code} className={i.bars ? "" : "muted"}>
          <span className={`swatch bench-${i.code}`} />
          {i.name}：{i.bars ? `${i.start} 至 ${i.end}` : "未同步"}
        </span>
      ))}
      {isAdmin && (
        <span className="index-sync">
          从
          <input type="date" value={start} onChange={(e) => setStart(e.target.value)} />
          <button className="button" disabled={busy} onClick={sync}>
            {busy ? "同步中…" : "同步恒指和沪深300"}
          </button>
        </span>
      )}
      <span className="muted small full">回测报告会拿策略和这两个指数比收益。同步任何股票时也会顺带补齐这段时间的指数。</span>
    </div>
  );
}

export function MarketPage({
  token,
  isAdmin,
  instruments,
  reloadInstruments,
  syncSymbol,
  notify,
}: {
  token: string;
  isAdmin: boolean;
  instruments: MarketInstrument[];
  reloadInstruments: () => Promise<void>;
  syncSymbol: (symbol: string, startDate: string, endDate?: string, provider?: string) => Promise<boolean>;
  notify: Notify;
}) {
  const sorted = useMemo(() => [...instruments].sort((a, b) => b.bar_count - a.bar_count), [instruments]);
  const [symbol, setSymbol] = useState("");
  const [frequency, setFrequency] = useState("1d");
  const [range, setRange] = useState(250);
  const [bars, setBars] = useState<MarketBar[]>([]);
  const [quality, setQuality] = useState<MarketQuality | null>(null);
  const [imports, setImports] = useState<MarketImportBatch[]>([]);
  const [openImport, setOpenImport] = useState<MarketImportBatchDetail | null>(null);
  const [importTab, setImportTab] = useState<ImportTab>("csv");
  const [busy, setBusy] = useState("");
  const [menu, setMenu] = useState<MenuState>(null);
  const [indexVersion, setIndexVersion] = useState(0);
  const closeMenu = useCallback(() => setMenu(null), []);
  const selected = instruments.find((item) => item.symbol === symbol) || null;

  useEffect(() => {
    if (!symbol && sorted.length) setSymbol(sorted[0].symbol);
  }, [sorted, symbol]);

  useEffect(() => {
    if (selected && selected.frequencies.length && !selected.frequencies.includes(frequency)) setFrequency(selected.frequencies[0]);
  }, [selected?.symbol]);

  useEffect(() => {
    if (symbol) loadBars();
  }, [symbol, frequency, range]);

  useEffect(() => {
    loadImports();
  }, []);

  async function loadBars() {
    try {
      const payload = await request<{ bars: MarketBar[] }>(
        `/market/bars?symbol=${encodeURIComponent(symbol)}&frequency=${encodeURIComponent(frequency)}&limit=${range}`,
      );
      setBars(payload.bars);
      setQuality(await request<MarketQuality>(`/market/quality?symbol=${encodeURIComponent(symbol)}&limit=250`));
    } catch (error) {
      setBars([]);
      notify("error", `K 线加载失败：${getErrorMessage(error)}`);
    }
  }

  async function loadImports() {
    try {
      const payload = await request<{ imports: MarketImportBatch[] }>("/market/imports", {}, token);
      setImports(payload.imports);
    } catch {
      setImports([]);
    }
  }

  async function afterWrite(target: string, freq = "1d") {
    await reloadInstruments();
    setSymbol(target);
    setFrequency(freq);
    await loadImports();
  }

  async function handleSync(provider: string, target: string, start: string, end: string) {
    setBusy("sync");
    const ok = await syncSymbol(target, start, end, provider);
    if (ok) await afterWrite(target);
    setBusy("");
    window.setTimeout(() => setIndexVersion((v) => v + 1), 4000); // the index top-up runs in the background
  }

  async function syncBoardLots() {
    setBusy("lots");
    try {
      const result = await request<{ updated: number }>("/market/board-lots/sync", { method: "POST" }, token);
      await reloadInstruments();
      notify("success", `已更新 ${result.updated} 只港股的每手股数。`);
    } catch (error) {
      notify("error", `每手股数更新失败：${getErrorMessage(error)}`);
    } finally {
      setBusy("");
    }
  }

  async function removeData(item: MarketInstrument, freq?: string) {
    const what = freq ? `的 ${frequencyLabels[freq] || freq} 行情` : "的全部行情";
    const tail = freq && item.frequencies.length > 1 ? "" : "，这只股票会从列表里移除";
    if (!window.confirm(`确定删除 ${item.symbol} ${item.name}${what}吗？行情所有账户共用，删除后无法恢复${tail}。已保存的回测记录不受影响，需要时可以重新同步。`)) return;
    setBusy("delete");
    try {
      const query = freq ? `?frequency=${encodeURIComponent(freq)}` : "";
      const result = await request<{ deleted_bars: number; removed_instrument: boolean }>(
        `/market/instruments/${encodeURIComponent(item.symbol)}${query}`,
        { method: "DELETE" },
        token,
      );
      if (result.removed_instrument && item.symbol === symbol) setSymbol("");
      await reloadInstruments();
      notify("success", `已删除 ${item.symbol} 的 ${formatNumber(result.deleted_bars, 0)} 根 K 线${result.removed_instrument ? "，并从列表移除" : ""}。`);
    } catch (error) {
      notify("error", `删除失败：${getErrorMessage(error)}`);
    } finally {
      setBusy("");
    }
  }

  function openMenu(event: MouseEvent, item: MarketInstrument) {
    event.preventDefault();
    const items: MenuItem[] = [{ label: "查看走势", onClick: () => setSymbol(item.symbol) }];
    if (isAdmin) {
      if (item.frequencies.length > 1) {
        for (const f of item.frequencies) {
          items.push({ label: `只删除${frequencyLabels[f] || f}数据`, danger: true, onClick: () => removeData(item, f) });
        }
      }
      items.push({ label: "删除这只股票的全部行情", danger: true, disabled: busy !== "", onClick: () => removeData(item) });
    } else {
      items.push({ label: "删除行情需要管理员账户", disabled: true, onClick: () => undefined });
    }
    setMenu({ x: event.clientX, y: event.clientY, items });
  }

  async function showImport(id: number) {
    try {
      setOpenImport(await request<MarketImportBatchDetail>(`/market/imports/${id}`, {}, token));
    } catch (error) {
      notify("error", `导入详情加载失败：${getErrorMessage(error)}`);
    }
  }

  const first = bars[0]?.close;
  const last = bars[bars.length - 1]?.close;
  const change = first && last ? last / first - 1 : undefined;

  return (
    <div className="page-pad market">
      <SyncBar isAdmin={isAdmin} busy={busy} onSync={handleSync} onBoardLots={syncBoardLots} />
      <IndexBar key={indexVersion} token={token} isAdmin={isAdmin} notify={notify} />

      <div className="market-body">
        <aside className="instrument-list">
          <div className="list-head">
            <h2>股票</h2>
            <span className="muted small" title={isAdmin ? "右键一只股票可以删除它的行情" : undefined}>
              {instruments.length} 只{isAdmin && instruments.length > 0 ? " · 右键可删除" : ""}
            </span>
          </div>
          <ul>
            {sorted.map((item) => (
              <li key={item.symbol}>
                <button className={item.symbol === symbol ? "instrument active" : "instrument"}
                  onClick={() => setSymbol(item.symbol)}
                  onContextMenu={(event) => openMenu(event, item)}
                >
                  <span className="sym">{item.symbol}</span>
                  <span className="nm">{item.name}</span>
                  <span className="meta">
                    {formatNumber(item.bar_count, 0)} 根 · {item.last_trade_time?.slice(0, 10) || "-"}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </aside>
        <ContextMenu menu={menu} onClose={closeMenu} />

        <section className="instrument-detail">
          {!selected ? (
            <div className="empty big">
              <h3>还没有行情数据</h3>
              <p>在上面填股票代码，点「同步日线」。</p>
            </div>
          ) : (
            <>
              <div className="detail-head">
                <div>
                  <h2>
                    {selected.name} <span className="muted">{selected.symbol}</span>
                  </h2>
                  <p className="muted">
                    {selected.exchange === "HK" ? "港股" : "A股"} · {selected.currency || "CNY"}
                    {selected.exchange === "HK" && ` · 每手 ${selected.lot_size ?? "未知"} 股`} · {selected.first_trade_time?.slice(0, 10)} 至{" "}
                    {selected.last_trade_time?.slice(0, 10)}，共 {formatNumber(selected.bar_count, 0)} 根
                  </p>
                </div>
                {isAdmin && (
                  <button className="text-button danger push-right" disabled={busy !== ""} onClick={() => removeData(selected)}>
                    删除行情
                  </button>
                )}
                <div className="price-now">
                  <strong>{formatNumber(selected.latest_close)}</strong>
                  {change !== undefined && <span className={trendClass(change)}>区间 {change > 0 ? "+" : ""}{(change * 100).toFixed(2)}%</span>}
                </div>
              </div>

              <div className="chart-controls">
                <div className="segmented small">
                  {selected.frequencies.map((f) => (
                    <button key={f} className={f === frequency ? "active" : ""} onClick={() => setFrequency(f)}>
                      {frequencyLabels[f] || f}
                    </button>
                  ))}
                </div>
                <div className="segmented small">
                  {RANGES.map(([label, count]) => (
                    <button key={count} className={count === range ? "active" : ""} onClick={() => setRange(count)}>
                      {label}
                    </button>
                  ))}
                </div>
              </div>
              <PriceChart bars={bars} />

              {quality && (
                <div className="quality">
                  <h3>数据检查</h3>
                  <p>
                    最近 {quality.checked_bar_count} 根 K 线：
                    {quality.issue_count === 0 ? (
                      <span className="ok-text">没有发现价格或成交量异常</span>
                    ) : (
                      <span className="warn-text">
                        {quality.error_count} 个错误，{quality.warning_count} 个提醒
                      </span>
                    )}
                    {quality.missing_trading_days.length > 0 && `，缺 ${quality.missing_trading_days.length} 个交易日`}。
                    <span className="muted small"> 交易日历：{quality.calendar_name}</span>
                  </p>
                  {quality.issues.length > 0 && (
                    <ul className="issue-list">
                      {quality.issues.slice(0, 6).map((issue) => (
                        <li key={`${issue.trade_time}-${issue.issue_type}`} className={issue.severity}>
                          {issue.trade_time.slice(0, 10)} · {issue.message || issue.issue_type}
                        </li>
                      ))}
                    </ul>
                  )}
                  {quality.missing_trading_days.length > 0 && (
                    <p className="muted small">缺少：{quality.missing_trading_days.slice(0, 8).join("、")}{quality.missing_trading_days.length > 8 ? " 等" : ""}</p>
                  )}
                </div>
              )}
            </>
          )}
        </section>
      </div>

      {isAdmin && (
        <div className="market-extra">
          <details className="import-panel">
            <summary>其他导入方式（分钟线、自有数据）</summary>
            <div className="tabs" role="tablist">
              {([
                ["csv", "粘贴 CSV"],
                ["file", "上传 CSV 文件"],
                ["single", "改一天的收盘价"],
              ] as [ImportTab, string][]).map(([key, label]) => (
                <button key={key} role="tab" aria-selected={importTab === key} className={importTab === key ? "active" : ""} onClick={() => setImportTab(key)}>
                  {label}
                </button>
              ))}
            </div>
            <ImportForms
              tab={importTab}
              token={token}
              defaultSymbol={selected?.symbol || ""}
              defaultName={selected?.name || ""}
              notify={notify}
              onDone={afterWrite}
            />
          </details>

          <section className="import-log">
            <h3>导入记录</h3>
            {imports.length === 0 ? (
              <p className="muted">还没有导入过数据。</p>
            ) : (
              <table className="data-table compact clickable">
                <tbody>
                  {imports.slice(0, 8).map((item) => (
                    <tr key={item.id} onClick={() => showImport(item.id)} className={openImport?.id === item.id ? "selected" : ""}>
                      <td>{formatTimestamp(item.created_at)}</td>
                      <td>{item.symbol}</td>
                      <td>{IMPORT_TYPES[item.import_type] || item.import_type}</td>
                      <td className="num">新增 {item.inserted_bars}</td>
                      <td className="num">更新 {item.updated_bars}</td>
                      <td className={item.status === "completed" ? "ok-text" : "warn-text"}>{item.status === "completed" ? "成功" : item.status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            {openImport && (
              <div className="import-detail">
                <p>{openImport.message}</p>
                {openImport.errors.length > 0 && (
                  <ul className="issue-list">
                    {openImport.errors.slice(0, 6).map((error, i) => (
                      <li key={i} className="error">
                        {error}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </section>
        </div>
      )}
    </div>
  );
}

function ImportForms({
  tab,
  token,
  defaultSymbol,
  defaultName,
  notify,
  onDone,
}: {
  tab: ImportTab;
  token: string;
  defaultSymbol: string;
  defaultName: string;
  notify: Notify;
  onDone: (symbol: string, frequency?: string) => Promise<void>;
}) {
  const [symbol, setSymbol] = useState(defaultSymbol);
  const [name, setName] = useState(defaultName);
  const [frequency, setFrequency] = useState("1d");
  const [csvText, setCsvText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [day, setDay] = useState("");
  const [close, setClose] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setSymbol(defaultSymbol);
    setName(defaultName);
  }, [defaultSymbol, defaultName]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const target = symbol.trim().toUpperCase();
    if (!target || !name.trim()) {
      notify("error", "请填写股票代码和名称。");
      return;
    }
    setBusy(true);
    try {
      if (tab === "csv") {
        if (!csvText.trim()) throw new Error("请粘贴 CSV 内容");
        const r = await request<MarketCsvImportResponse>(
          "/market/import/csv",
          {
            method: "POST",
            body: JSON.stringify({ symbol: target, name: name.trim(), exchange: exchangeOf(target), frequency, csv_text: csvText, source: "csv" }),
          },
          token,
        );
        notify("success", `已导入 ${target}：解析 ${r.parsed_rows} 行，新增 ${r.inserted_bars}，更新 ${r.updated_bars}${r.skipped_rows ? `，跳过 ${r.skipped_rows}` : ""}。`);
        setCsvText("");
      } else if (tab === "file") {
        if (!file) throw new Error("请选择 CSV 文件");
        const data = new FormData();
        data.append("symbol", target);
        data.append("name", name.trim());
        data.append("exchange", exchangeOf(target));
        data.append("frequency", frequency);
        data.append("file", file);
        const r = await requestFormData<MarketCsvImportResponse>("/market/import/file", data, token);
        notify("success", `已导入 ${target}：解析 ${r.parsed_rows} 行，新增 ${r.inserted_bars}，更新 ${r.updated_bars}。`);
      } else {
        const price = Number(close);
        if (!day || !(price > 0)) throw new Error("请填写日期和大于 0 的收盘价");
        const r = await request<MarketImportResponse>(
          "/market/import",
          {
            method: "POST",
            body: JSON.stringify({
              instrument: { symbol: target, name: name.trim(), exchange: exchangeOf(target), asset_type: "stock", status: "active" },
              bars: [{ symbol: target, frequency: "1d", trade_time: day, open: price, high: price, low: price, close: price, volume: 0, amount: 0, adj_factor: 1, source: "manual" }],
            }),
          },
          token,
        );
        notify("success", `已写入 ${target} ${day}：新增 ${r.inserted_bars}，更新 ${r.updated_bars}。`);
      }
      await onDone(target, tab === "single" ? "1d" : frequency);
    } catch (error) {
      notify("error", `导入失败：${getErrorMessage(error)}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="import-form" onSubmit={submit}>
      <div className="field-grid">
        <label>
          股票代码
          <input value={symbol} placeholder="600519.SH" onChange={(e) => setSymbol(e.target.value.toUpperCase())} />
        </label>
        <label>
          名称
          <input value={name} placeholder="贵州茅台" onChange={(e) => setName(e.target.value)} />
        </label>
        {tab !== "single" ? (
          <label>
            周期
            <select value={frequency} onChange={(e) => setFrequency(e.target.value)}>
              {Object.entries(frequencyLabels).map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </select>
          </label>
        ) : (
          <>
            <label>
              日期
              <input type="date" value={day} onChange={(e) => setDay(e.target.value)} />
            </label>
            <label>
              收盘价
              <input inputMode="decimal" value={close} onChange={(e) => setClose(e.target.value)} />
            </label>
          </>
        )}
      </div>
      {tab === "csv" && (
        <textarea
          className="code-editor short"
          aria-label="CSV 内容"
          value={csvText}
          spellCheck={false}
          placeholder={"第一行是表头，例如：\ntrade_time,open,high,low,close,volume,amount\n2024-02-01,44.35,46.65,43.85,45.50,6074764,276000000"}
          onChange={(e) => setCsvText(e.target.value)}
        />
      )}
      {tab === "file" && <input type="file" accept=".csv,text/csv" onChange={(e) => setFile(e.target.files?.[0] || null)} />}
      {tab === "single" && <p className="muted small">只改这一天，开高低收都设成同一个价格。修正个别错误数据时用。</p>}
      <button className="button primary" type="submit" disabled={busy}>
        {busy ? "导入中…" : "导入"}
      </button>
    </form>
  );
}
