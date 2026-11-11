import { useEffect, useRef, useState } from "react";
import { request } from "./api";

// Live quotes (Tencent, ~3 s delayed) and the background batch sync, shared by the pages.

export type Quote = {
  symbol: string;
  name: string;
  price: number;
  prev_close: number;
  open: number | null;
  high: number | null;
  low: number | null;
  volume: number;
  amount: number;
  change: number;
  change_pct: number;
  time: string | null;
  traded: boolean;
};

export type BatchJob = {
  job_id: string;
  status: "running" | "done" | "cancelled" | "error";
  total: number;
  done: number;
  ok: number;
  failed: { symbol: string; error: string }[];
  symbols: string[];
  error?: string;
};

/** Split pasted codes on spaces, commas, 、 and new lines. */
export function splitCodes(text: string) {
  return Array.from(new Set(text.split(/[\s,，、;；]+/).map((s) => s.trim().toUpperCase()).filter(Boolean)));
}

/** Roughly when A-share / HK prices move (Beijing time, weekdays 9:15-16:15); polling stops outside it. */
export function marketHoursNow(now = new Date()) {
  const beijing = new Date(now.getTime() + (now.getTimezoneOffset() + 480) * 60000);
  const minutes = beijing.getHours() * 60 + beijing.getMinutes();
  return beijing.getDay() >= 1 && beijing.getDay() <= 5 && minutes >= 9 * 60 + 15 && minutes <= 16 * 60 + 15;
}

/** Quotes for ``symbols``, refreshed every ``seconds`` while enabled, the page is visible and markets are open. */
export function useLiveQuotes(symbols: string[], enabled: boolean, seconds = 5) {
  const [quotes, setQuotes] = useState<Record<string, Quote>>({});
  const [error, setError] = useState("");
  const [updated, setUpdated] = useState<Date | null>(null);
  const key = symbols.slice(0, 500).join(",");

  useEffect(() => {
    if (!enabled || !key) return;
    let stopped = false;
    async function load(force = false) {
      if (stopped || document.hidden || (!force && !marketHoursNow())) return;
      try {
        const payload = await request<{ quotes: Quote[] }>(`/market/quotes?symbols=${encodeURIComponent(key)}`);
        if (stopped) return;
        setQuotes(Object.fromEntries(payload.quotes.map((q) => [q.symbol, q])));
        setUpdated(new Date());
        setError("");
      } catch (err) {
        if (!stopped) setError(err instanceof Error ? err.message : String(err));
      }
    }
    load(true); // always one read, so closing prices show after hours too
    const timer = window.setInterval(() => load(), seconds * 1000);
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, [enabled, key, seconds]);

  return { quotes, error, updated };
}

/** Starts / follows the background batch sync; ``onFinished`` runs once when a job stops. */
export function useBatchSync(token: string, onFinished: (job: BatchJob) => void) {
  const [job, setJob] = useState<BatchJob | null>(null);
  const finished = useRef(onFinished);
  finished.current = onFinished;

  useEffect(() => {
    request<{ job: BatchJob | null }>("/market/sync-batch", {}, token)
      .then((p) => setJob(p.job))
      .catch(() => undefined);
  }, [token]);

  useEffect(() => {
    if (job?.status !== "running") return;
    const timer = window.setInterval(async () => {
      try {
        const next = (await request<{ job: BatchJob | null }>("/market/sync-batch", {}, token)).job;
        setJob(next);
        if (next && next.status !== "running") finished.current(next);
      } catch {
        /* keep polling */
      }
    }, 1000);
    return () => window.clearInterval(timer);
  }, [job?.job_id, job?.status, token]);

  async function start(symbols: string[], startDate: string, endDate: string, provider: string) {
    const started = await request<BatchJob>(
      "/market/sync-batch",
      { method: "POST", body: JSON.stringify({ symbols, start_date: startDate, end_date: endDate, provider_id: provider }) },
      token,
    );
    setJob(started);
    return started;
  }

  async function cancel() {
    if (!job) return;
    setJob((await request<{ job: BatchJob }>(`/market/sync-batch/${job.job_id}/cancel`, { method: "POST" }, token)).job);
  }

  return { job, start, cancel, dismiss: () => setJob(null) };
}
