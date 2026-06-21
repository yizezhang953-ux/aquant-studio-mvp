import { FormEvent, useEffect, useMemo, useState } from "react";

const API_BASE = "http://localhost:8000/api/v1";

type AuthMode = "login" | "register";
type MessageKind = "info" | "success" | "error";

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
  strategy: Record<string, unknown>;
};

type StrategyRecord = {
  strategy_id: string;
  name: string;
  market: string;
  symbol: string;
  frequency: string;
  source_template_id: string | null;
  status: "draft" | "active" | "archived";
  strategy: Record<string, unknown>;
};

type StrategyVersion = {
  version: number;
  change_note: string;
  strategy: Record<string, unknown>;
};

type FlashMessage = {
  kind: MessageKind;
  text: string;
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
  return "Request failed";
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
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

function prettyJson(value: unknown) {
  return JSON.stringify(value, null, 2);
}

export default function App() {
  const [authMode, setAuthMode] = useState<AuthMode>("login");
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
  const [strategyStatus, setStrategyStatus] = useState<StrategyRecord["status"]>("draft");
  const [editorText, setEditorText] = useState("{}");
  const [versions, setVersions] = useState<StrategyVersion[]>([]);
  const [message, setMessage] = useState<FlashMessage>({
    kind: "info",
    text: "连接后端后，可以注册、复制模板并保存自己的策略。",
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
    loadVersions(selectedStrategy.strategy_id);
  }, [selectedStrategy]);

  async function loadTemplates() {
    try {
      const payload = await request<{ templates: TemplateSummary[] }>("/templates");
      setTemplates(payload.templates);
      if (payload.templates.length > 0) {
        setSelectedTemplateId(payload.templates[0].template_id);
      }
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
      setEditorText("{}");
      setStrategyName("");
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
        authMode === "login"
          ? { email, password }
          : { email, password, display_name: displayName };
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
    if (token) {
      await request("/auth/logout", { method: "POST" }, token).catch(() => undefined);
    }
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
      const created = await request<StrategyRecord>(
        "/strategies",
        {
          method: "POST",
          body: JSON.stringify({
            name: `${detail.metadata.name} - 我的策略`,
            source_template_id: detail.metadata.template_id,
            strategy: detail.strategy,
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
      const parsed = JSON.parse(editorText) as Record<string, unknown>;
      const updated = await request<StrategyRecord>(
        `/strategies/${selectedStrategy.strategy_id}`,
        {
          method: "PUT",
          body: JSON.stringify({
            name: strategyName,
            status: strategyStatus,
            strategy: parsed,
            change_note: "Frontend editor save",
          }),
        },
        token,
      );
      await loadStrategies();
      setSelectedStrategyId(updated.strategy_id);
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

  function loadVersionIntoEditor(version: StrategyVersion) {
    setEditorText(prettyJson(version.strategy));
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
                <button
                  type="button"
                  className={authMode === "login" ? "active" : ""}
                  onClick={() => setAuthMode("login")}
                >
                  登录
                </button>
                <button
                  type="button"
                  className={authMode === "register" ? "active" : ""}
                  onClick={() => setAuthMode("register")}
                >
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
              <input
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </label>
            <button className="primary-action" type="submit" disabled={loading}>
              {loading ? "处理中" : authMode === "login" ? "登录" : "注册并进入"}
            </button>
          </form>
          <aside className="panel compact-panel">
            <h2>本阶段能力</h2>
            <ul>
              <li>使用后端账户接口建立登录会话</li>
              <li>复制系统模板为个人策略</li>
              <li>保存 JSON 策略并生成版本</li>
              <li>按用户隔离策略列表</li>
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
              <select
                value={selectedTemplateId}
                onChange={(event) => setSelectedTemplateId(event.target.value)}
              >
                {templates.map((template) => (
                  <option key={template.template_id} value={template.template_id}>
                    {template.name}
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
                    <select
                      value={strategyStatus}
                      onChange={(event) => setStrategyStatus(event.target.value as StrategyRecord["status"])}
                    >
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
                <textarea
                  className="json-editor"
                  value={editorText}
                  onChange={(event) => setEditorText(event.target.value)}
                  spellCheck={false}
                />
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
