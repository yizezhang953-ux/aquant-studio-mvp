import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import {
  BacktestHistoryItem,
  MarketInstrument,
  MarketSyncResponse,
  NoticeKind,
  StrategyRecord,
  TemplateSummary,
  User,
  getErrorMessage,
  request,
  today,
} from "./api";
import { HistoryPage } from "./HistoryPage";
import { MarketPage } from "./MarketPage";
import { StrategyPage } from "./StrategyPage";

type Page = "strategy" | "history" | "market";
const PAGES: [Page, string][] = [
  ["strategy", "策略研究"],
  ["history", "回测记录"],
  ["market", "行情数据"],
];

function storedToken() {
  try {
    return window.localStorage.getItem("aquant_token") || "";
  } catch {
    return "";
  }
}

function storeToken(token: string) {
  try {
    if (token) window.localStorage.setItem("aquant_token", token);
    else window.localStorage.removeItem("aquant_token");
  } catch {
    /* private mode: stay logged in for this tab only */
  }
}

function initialPage(): Page {
  const hash = window.location.hash.replace("#", "");
  return hash === "history" || hash === "market" ? hash : "strategy";
}

export default function App() {
  const [token, setToken] = useState(storedToken);
  const [user, setUser] = useState<User | null>(null);
  const [checking, setChecking] = useState(Boolean(storedToken()));
  const [page, setPage] = useState<Page>(initialPage);
  const [templates, setTemplates] = useState<TemplateSummary[]>([]);
  const [strategies, setStrategies] = useState<StrategyRecord[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [instruments, setInstruments] = useState<MarketInstrument[]>([]);
  const [history, setHistory] = useState<BacktestHistoryItem[]>([]);
  const [notice, setNotice] = useState<{ kind: NoticeKind; text: string; id: number } | null>(null);
  const timer = useRef<number>();

  const notify = useCallback((kind: NoticeKind, text: string) => {
    window.clearTimeout(timer.current);
    setNotice({ kind, text, id: Date.now() });
    if (kind !== "error") timer.current = window.setTimeout(() => setNotice(null), 5000);
  }, []);

  useEffect(() => {
    request<{ templates: TemplateSummary[] }>("/templates")
      .then((p) => setTemplates(p.templates))
      .catch((e) => notify("error", `模板加载失败：${getErrorMessage(e)}`));
    reloadInstruments();
  }, []);

  useEffect(() => {
    window.location.hash = page === "strategy" ? "" : page;
  }, [page]);

  useEffect(() => {
    if (!token) {
      setChecking(false);
      return;
    }
    storeToken(token);
    (async () => {
      try {
        const me = await request<User>("/auth/me", {}, token);
        setUser(me);
        const list = await reloadStrategies(token);
        setSelectedId((current) => current || list[0]?.strategy_id || "");
        await reloadHistory(token);
      } catch {
        storeToken("");
        setToken("");
        setUser(null);
      } finally {
        setChecking(false);
      }
    })();
  }, [token]);

  async function reloadInstruments() {
    try {
      const payload = await request<{ instruments: MarketInstrument[] }>("/market/instruments");
      setInstruments(payload.instruments);
    } catch (error) {
      notify("error", `行情列表加载失败：${getErrorMessage(error)}`);
    }
  }

  async function reloadStrategies(accessToken = token) {
    const payload = await request<{ strategies: StrategyRecord[] }>("/strategies", {}, accessToken);
    setStrategies(payload.strategies);
    return payload.strategies;
  }

  async function reloadHistory(accessToken = token) {
    try {
      const payload = await request<{ backtests: BacktestHistoryItem[] }>("/backtests", {}, accessToken);
      setHistory(payload.backtests);
    } catch (error) {
      notify("error", `回测记录加载失败：${getErrorMessage(error)}`);
    }
  }

  async function syncSymbol(symbol: string, startDate: string, endDate = today(), provider = "tencent") {
    notify("info", `正在从${provider === "tencent" ? "腾讯行情" : "演示数据源"}同步 ${symbol}，通常要几秒…`);
    try {
      const result = await request<MarketSyncResponse>(
        "/market/sync",
        { method: "POST", body: JSON.stringify({ provider_id: provider, symbol, start_date: startDate, end_date: endDate, frequency: "1d" }) },
        token,
      );
      await reloadInstruments();
      const extras = [
        result.corporate_actions ? `分红送股 ${result.corporate_actions} 次` : "",
        result.fx_rates ? `汇率 ${result.fx_rates} 天` : "",
      ].filter(Boolean);
      notify("success", `已同步 ${result.symbol}：${result.fetched_bars} 根日线${extras.length ? `，${extras.join("，")}` : ""}。`);
      return true;
    } catch (error) {
      notify("error", `同步 ${symbol} 失败：${getErrorMessage(error)}`);
      return false;
    }
  }

  async function logout() {
    if (token) await request("/auth/logout", { method: "POST" }, token).catch(() => undefined);
    storeToken("");
    setToken("");
    setUser(null);
    setStrategies([]);
    setHistory([]);
    setSelectedId("");
    notify("info", "已退出登录。");
  }

  return (
    <div className="app">
      <header className="appbar">
        <div className="brand">
          <span className="mark" aria-hidden="true" />
          <span className="brand-name">AQuant Studio</span>
        </div>
        {user && (
          <nav className="pages" aria-label="页面">
            {PAGES.map(([key, label]) => (
              <button key={key} className={page === key ? "active" : ""} aria-current={page === key ? "page" : undefined} onClick={() => setPage(key)}>
                {label}
              </button>
            ))}
          </nav>
        )}
        <div className="appbar-right">
          <span className="env" title="只做历史回测和模拟，不会向券商下单">模拟环境 · 实盘已禁用</span>
          {user && (
            <span className="who">
              {user.display_name}
              {user.is_admin && <small>管理员</small>}
              <button className="text-button" onClick={logout}>
                退出
              </button>
            </span>
          )}
        </div>
      </header>

      {notice && (
        <div className={`notice ${notice.kind}`} role={notice.kind === "error" ? "alert" : "status"} key={notice.id}>
          <span>{notice.text}</span>
          <button className="icon-button" aria-label="关闭提示" onClick={() => setNotice(null)}>
            ×
          </button>
        </div>
      )}

      <main className="content">
        {checking ? (
          <div className="empty big">
            <p>正在登录…</p>
          </div>
        ) : !user ? (
          <AuthScreen
            onAuthed={(accessToken, me) => {
              setUser(me);
              setToken(accessToken);
            }}
            notify={notify}
          />
        ) : page === "strategy" ? (
          <StrategyPage
            token={token}
            user={user}
            templates={templates}
            strategies={strategies}
            selectedId={selectedId}
            onSelect={setSelectedId}
            instruments={instruments}
            reloadStrategies={() => reloadStrategies()}
            onBacktestSaved={() => reloadHistory()}
            syncSymbol={(symbol, start) => syncSymbol(symbol, start)}
            notify={notify}
          />
        ) : page === "history" ? (
          <HistoryPage token={token} history={history} notify={notify} />
        ) : (
          <MarketPage
            token={token}
            isAdmin={Boolean(user.is_admin)}
            instruments={instruments}
            reloadInstruments={reloadInstruments}
            syncSymbol={syncSymbol}
            notify={notify}
          />
        )}
      </main>
    </div>
  );
}

function AuthScreen({ onAuthed, notify }: { onAuthed: (token: string, user: User) => void; notify: (kind: NoticeKind, text: string) => void }) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      const body = mode === "login" ? { email, password } : { email, password, display_name: displayName };
      const payload = await request<{ access_token: string; user: User }>(mode === "login" ? "/auth/login" : "/auth/register", {
        method: "POST",
        body: JSON.stringify(body),
      });
      onAuthed(payload.access_token, payload.user);
      notify("success", mode === "login" ? `欢迎回来，${payload.user.display_name}。` : "账户已创建。");
    } catch (error) {
      notify("error", getErrorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth">
      <section className="auth-copy">
        <h1>用历史行情检验你的交易想法</h1>
        <p>A股、港股和港股通的规则都已内置：整手、T+1、涨跌停、印花税、汇率和股息税。只做回测和模拟，不会真的下单。</p>
      </section>
      <form className="auth-form" onSubmit={submit}>
        <div className="segmented">
          <button type="button" className={mode === "login" ? "active" : ""} onClick={() => setMode("login")}>
            登录
          </button>
          <button type="button" className={mode === "register" ? "active" : ""} onClick={() => setMode("register")}>
            注册
          </button>
        </div>
        <label>
          邮箱
          <input type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
        {mode === "register" && (
          <label>
            显示名称
            <input value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
          </label>
        )}
        <label>
          密码
          <input
            type="password"
            autoComplete={mode === "login" ? "current-password" : "new-password"}
            value={password}
            placeholder={mode === "register" ? "至少 8 个字符" : ""}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        <button className="button primary wide" type="submit" disabled={busy}>
          {busy ? "请稍候…" : mode === "login" ? "登录" : "注册并进入"}
        </button>
        {mode === "register" && <p className="muted small">在本机运行时，第一个注册的账户是管理员，可以同步行情数据。</p>}
      </form>
    </div>
  );
}
