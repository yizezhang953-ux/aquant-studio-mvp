import { useEffect, useState } from "react";
import { Notify, getErrorMessage, request } from "./api";

// 收盘后自动运行: when the daily job runs, where it pushes, run-now / test buttons and the run history.

type Channel = "none" | "pushplus" | "serverchan" | "webhook";
type AutomationSettings = {
  enabled: boolean;
  run_time: string;
  provider_id: "tencent" | "demo";
  notify_channel: Channel;
  notify_target_hint: string;
  last_run_date: string | null;
  channels: Record<Channel, string>;
};
type RunOrder = { side: "buy" | "sell"; symbol: string; name: string; reason: string; account_name: string };
type AutomationRun = {
  id: number;
  run_date: string;
  trigger: "schedule" | "manual";
  status: "ok" | "partial" | "error" | "running";
  summary: { orders?: RunOrder[]; warnings?: string[]; accounts?: unknown[] };
  message: string;
  notify_status: "off" | "sent" | "failed";
  notify_error: string | null;
  started_at: string | null;
};

const TARGET_HELP: Record<Channel, string> = {
  none: "",
  pushplus: "在 pushplus.plus 用微信扫码登录，复制「一对一推送」的 token。消息会出现在「pushplus 推送加」公众号里。",
  serverchan: "在 sct.ftqq.com 用微信登录，复制 SendKey（SCT 开头）。",
  webhook: "在企业微信、钉钉或飞书群里添加「自定义机器人」，复制它的 Webhook 地址（https:// 开头）。钉钉机器人的安全设置选「自定义关键词」并填 AQuant。",
};
const STATUS = { ok: "完成", partial: "有提醒", error: "出错", running: "运行中" };
const STATUS_CLASS = { ok: "tag ok", partial: "tag warn", error: "tag bad", running: "tag" };
const NOTIFY = { off: "未推送", sent: "已推送", failed: "推送失败" };

export function AutomationPanel({ token, isAdmin, notify }: { token: string; isAdmin: boolean; notify: Notify }) {
  const [saved, setSaved] = useState<AutomationSettings | null>(null);
  const [runs, setRuns] = useState<AutomationRun[]>([]);
  const [form, setForm] = useState({ enabled: false, run_time: "16:30", provider_id: "tencent", notify_channel: "none" as Channel });
  const [target, setTarget] = useState("");
  const [busy, setBusy] = useState("");
  const [openRun, setOpenRun] = useState<number | null>(null);

  function apply(data: { settings: AutomationSettings; runs: AutomationRun[] }) {
    setSaved(data.settings);
    setRuns(data.runs);
    const { enabled, run_time, provider_id, notify_channel } = data.settings;
    setForm({ enabled, run_time, provider_id, notify_channel });
    setTarget("");
  }

  useEffect(() => {
    request<{ settings: AutomationSettings; runs: AutomationRun[] }>("/automation", {}, token)
      .then(apply)
      .catch((error) => notify("error", `读取自动运行设置失败：${getErrorMessage(error)}`));
  }, [token]);

  const dirty = saved != null && (form.enabled !== saved.enabled || form.run_time !== saved.run_time || form.provider_id !== saved.provider_id || form.notify_channel !== saved.notify_channel || target.trim() !== "");
  const needsTarget = form.notify_channel !== "none" && !target.trim() && (form.notify_channel !== saved?.notify_channel || !saved?.notify_target_hint);

  async function save() {
    setBusy("save");
    try {
      const body = { ...form, ...(target.trim() ? { notify_target: target.trim() } : {}) };
      apply(await request("/automation", { method: "PUT", body: JSON.stringify(body) }, token));
      notify("success", form.enabled ? `已开启：每个交易日 ${form.run_time} 自动运行。` : "已保存，自动运行目前是关闭的。");
    } catch (error) {
      notify("error", `保存失败：${getErrorMessage(error)}`);
    } finally {
      setBusy("");
    }
  }

  async function testPush() {
    setBusy("test");
    try {
      await request("/automation/test-notify", { method: "POST" }, token);
      notify("success", "测试消息已发出，看看手机有没有收到。");
    } catch (error) {
      notify("error", `推送失败：${getErrorMessage(error)}`);
    } finally {
      setBusy("");
    }
  }

  async function runNow() {
    setBusy("run");
    notify("info", "正在同步行情并更新模拟盘，股票多的话要一会儿…");
    try {
      const run = await request<AutomationRun>("/automation/run", { method: "POST" }, token);
      setRuns((current) => [run, ...current.filter((r) => r.id !== run.id)]);
      setOpenRun(run.id);
      const orders = run.summary.orders?.length || 0;
      notify(run.status === "error" ? "error" : "success", run.status === "error" ? run.message : `运行完成：明天开盘 ${orders} 笔待执行。`);
    } catch (error) {
      notify("error", `运行失败：${getErrorMessage(error)}`);
    } finally {
      setBusy("");
    }
  }

  if (!saved) return null;

  return (
    <section className="batch-setup automation">
      <div className="paper-head">
        <h3 className="section-title">收盘后自动运行</h3>
        <span className={saved.enabled ? "tag ok" : "tag"}>{saved.enabled ? `已开启 · 每个交易日 ${saved.run_time}` : "未开启"}</span>
      </div>
      <p className="muted small">
        到点后自动同步模拟盘里股票的最新行情、更新所有模拟盘，再把明天开盘要执行的买卖单推送到你的手机。只推送，不会下单。
        需要程序（start.bat 的窗口）开着；如果到点时电脑没开，当天打开程序后会马上补跑一次。
      </p>

      <div className="paper-form automation-form">
        <label className="check">
          <input type="checkbox" checked={form.enabled} onChange={(e) => setForm({ ...form, enabled: e.target.checked })} />
          开启每日自动运行
        </label>
        <label>
          运行时间（北京时间）
          <input type="time" value={form.run_time} onChange={(e) => setForm({ ...form, run_time: e.target.value })} />
        </label>
        <label>
          行情来源
          <select value={form.provider_id} onChange={(e) => setForm({ ...form, provider_id: e.target.value })}>
            <option value="tencent">腾讯行情（真实数据）</option>
            <option value="demo">演示数据</option>
          </select>
        </label>
        <label>
          推送到
          <select value={form.notify_channel} onChange={(e) => setForm({ ...form, notify_channel: e.target.value as Channel })}>
            {(Object.keys(saved.channels) as Channel[]).map((key) => (
              <option key={key} value={key}>
                {saved.channels[key]}
              </option>
            ))}
          </select>
        </label>
        {form.notify_channel !== "none" && (
          <label className="wide">
            {form.notify_channel === "webhook" ? "Webhook 地址" : form.notify_channel === "serverchan" ? "SendKey" : "token"}
            <input
              value={target}
              type="password"
              autoComplete="off"
              placeholder={saved.notify_channel === form.notify_channel && saved.notify_target_hint ? `已保存（${saved.notify_target_hint}），不改就留空` : "粘贴到这里"}
              onChange={(e) => setTarget(e.target.value)}
            />
            <span className="muted small">{TARGET_HELP[form.notify_channel]}</span>
          </label>
        )}
        <div className="wide paper-form-foot">
          <button className="button primary" disabled={busy !== "" || !dirty || needsTarget || !form.run_time} onClick={save}>
            {busy === "save" ? "保存中…" : "保存设置"}
          </button>
          <button className="button" disabled={busy !== "" || dirty || saved.notify_channel === "none"} onClick={testPush}>
            {busy === "test" ? "发送中…" : "发一条测试推送"}
          </button>
          <button className="button" disabled={busy !== ""} onClick={runNow}>
            {busy === "run" ? "运行中…" : "立即运行一次"}
          </button>
          {!isAdmin && <span className="muted small">你不是管理员，自动运行只会用库里已有的行情，不会去同步。</span>}
        </div>
      </div>

      {runs.length > 0 && (
        <div className="table-wrap">
          <table className="data-table clickable automation-runs">
            <thead>
              <tr>
                <th>日期</th>
                <th>方式</th>
                <th>结果</th>
                <th className="num">待执行</th>
                <th>推送</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <RunRow key={run.id} run={run} open={openRun === run.id} onToggle={() => setOpenRun(openRun === run.id ? null : run.id)} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function RunRow({ run, open, onToggle }: { run: AutomationRun; open: boolean; onToggle: () => void }) {
  return (
    <>
      <tr onClick={onToggle}>
        <td>
          {run.run_date} <span className="muted small">{run.started_at?.slice(11, 16)}</span>
        </td>
        <td>{run.trigger === "schedule" ? "定时" : "手动"}</td>
        <td>
          <span className={STATUS_CLASS[run.status]}>{STATUS[run.status]}</span>
        </td>
        <td className="num">{run.summary.orders?.length ?? "-"}</td>
        <td title={run.notify_error || ""}>
          <span className={run.notify_status === "failed" ? "danger-text" : run.notify_status === "sent" ? "" : "muted"}>{NOTIFY[run.notify_status]}</span>
        </td>
      </tr>
      {open && (
        <tr className="run-detail">
          <td colSpan={5}>
            <pre className="run-message">{run.message.replace(/\*\*/g, "") || "（没有内容）"}</pre>
            {run.notify_error && <p className="danger-text small">推送失败：{run.notify_error}</p>}
          </td>
        </tr>
      )}
    </>
  );
}
