import { useMemo, useState, MouseEvent } from "react";
import { BacktestTrade, EquityPoint, formatMoney, formatNumber, formatPercent } from "./api";

const W = 1000;

function scale(values: number[], height: number, pad = 0.06) {
  const finite = values.filter(Number.isFinite);
  const min = Math.min(...finite);
  const max = Math.max(...finite);
  const span = max - min || Math.abs(max) || 1;
  const lo = min - span * pad;
  const hi = max + span * pad;
  return { lo, hi, y: (v: number) => height - ((v - lo) / (hi - lo)) * height };
}

function path(values: number[], x: (i: number) => number, y: (v: number) => number) {
  let d = "";
  values.forEach((v, i) => {
    if (!Number.isFinite(v)) return;
    d += `${d ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`;
  });
  return d;
}

function useHover(count: number) {
  const [index, setIndex] = useState<number | null>(null);
  function onMove(event: MouseEvent<HTMLDivElement>) {
    const rect = event.currentTarget.getBoundingClientRect();
    const ratio = Math.min(Math.max((event.clientX - rect.left) / rect.width, 0), 1);
    setIndex(Math.round(ratio * (count - 1)));
  }
  return { index, onMove, onLeave: () => setIndex(null) };
}

/** Strategy equity vs buy-and-hold, with drawdown underneath and trade markers. */
export function EquityChart({
  points,
  trades,
  initialCash,
  currency,
  benchmarks = [],
}: {
  points: EquityPoint[];
  trades: BacktestTrade[];
  initialCash: number;
  currency: string;
  /** Index lines in equity units, aligned with points. */
  benchmarks?: { code: string; name: string; values: number[] }[];
}) {
  const H = 220;
  const DD = 56;
  const equity = points.map((p) => p.equity);
  const firstClose = points.find((p) => (p.close ?? 0) > 0)?.close;
  const hold = firstClose ? points.map((p) => (initialCash * (p.close ?? NaN)) / firstClose) : [];
  const drawdown = points.map((p) => p.drawdown_pct);
  const { y, lo, hi } = useMemo(() => scale([...equity, ...hold, ...benchmarks.flatMap((b) => b.values), initialCash], H), [points, benchmarks]);
  const ddMax = Math.max(...drawdown, 0.01);
  const x = (i: number) => (points.length <= 1 ? 0 : (i / (points.length - 1)) * W);
  const hover = useHover(points.length);
  const timeIndex = useMemo(() => new Map(points.map((p, i) => [p.trade_time.slice(0, 10), i])), [points]);
  const markers = trades.flatMap((t) => [
    { i: timeIndex.get(t.entry_time.slice(0, 10)), kind: "buy" as const },
    { i: timeIndex.get(t.exit_time.slice(0, 10)), kind: "sell" as const },
  ]);

  if (points.length < 2) return <p className="muted">数据点太少，画不出曲线。</p>;
  const h = hover.index;
  const point = h != null ? points[h] : null;
  const baseY = y(initialCash);

  return (
    <div className="chart" onMouseMove={hover.onMove} onMouseLeave={hover.onLeave}>
      <div className="chart-legend">
        <span className="key strategy">策略权益</span>
        {hold.length > 0 && <span className="key hold">买入持有（按价格）</span>}
        {benchmarks.map((b) => (
          <span key={b.code} className={`key bench-${b.code}`}>
            {b.name}
          </span>
        ))}
        <span className="key dd">回撤</span>
      </div>
      <div className="chart-body">
        <div className="y-labels" style={{ height: H }}>
          <span>{formatMoney(hi)}</span>
          <span>{formatMoney(lo)}</span>
        </div>
        <svg viewBox={`0 0 ${W} ${H + DD + 8}`} style={{ height: H + DD + 8 }} preserveAspectRatio="none" role="img" aria-label="权益曲线">
          <line x1="0" x2={W} y1={baseY} y2={baseY} className="baseline" vectorEffect="non-scaling-stroke" />
          {hold.length > 0 && <path d={path(hold, x, y)} className="line hold" vectorEffect="non-scaling-stroke" />}
          {benchmarks.map((b) => (
            <path key={b.code} d={path(b.values, x, y)} className={`line bench-${b.code}`} vectorEffect="non-scaling-stroke" />
          ))}
          <path d={path(equity, x, y)} className="line strategy" vectorEffect="non-scaling-stroke" />
          {markers.map((m, k) =>
            m.i == null ? null : (
              <line
                key={k}
                x1={x(m.i)}
                x2={x(m.i)}
                y1={y(equity[m.i]) - (m.kind === "buy" ? -6 : 6)}
                y2={y(equity[m.i])}
                className={`marker ${m.kind}`}
                vectorEffect="non-scaling-stroke"
              />
            ),
          )}
          <g transform={`translate(0 ${H + 8})`}>
            <path
              d={`${path(drawdown, x, (v) => (v / ddMax) * DD)}L${W},0L0,0Z`}
              className="area dd"
              vectorEffect="non-scaling-stroke"
            />
          </g>
          {h != null && <line x1={x(h)} x2={x(h)} y1="0" y2={H + DD + 8} className="crosshair" vectorEffect="non-scaling-stroke" />}
        </svg>
      </div>
      <div className="x-labels">
        <span>{points[0].trade_time.slice(0, 10)}</span>
        <span>最大回撤 {formatPercent(Math.max(...drawdown))}</span>
        <span>{points[points.length - 1].trade_time.slice(0, 10)}</span>
      </div>
      {point && h != null && (
        <div className="chart-tip" style={{ left: `${(h / (points.length - 1)) * 100}%` }}>
          <strong>{point.trade_time.slice(0, 10)}</strong>
          <span>
            策略 {formatMoney(point.equity)} {currency}
          </span>
          {hold.length > 0 && <span>持有 {formatMoney(hold[h])}</span>}
          {benchmarks.map((b) => (
            <span key={b.code}>
              {b.name} {formatPercent(b.values[h] / initialCash - 1, true)}
            </span>
          ))}
          <span>回撤 {formatPercent(point.drawdown_pct)}</span>
        </div>
      )}
    </div>
  );
}

/** Close-price line for the market data page. */
export function PriceChart({ bars }: { bars: { trade_time: string; close: number }[] }) {
  const H = 200;
  const closes = bars.map((b) => b.close);
  const { y, lo, hi } = useMemo(() => scale(closes, H), [bars]);
  const x = (i: number) => (bars.length <= 1 ? 0 : (i / (bars.length - 1)) * W);
  const hover = useHover(bars.length);
  if (bars.length < 2) return <p className="muted">K 线太少，画不出走势。</p>;
  const h = hover.index;
  const up = closes[closes.length - 1] >= closes[0];
  return (
    <div className="chart" onMouseMove={hover.onMove} onMouseLeave={hover.onLeave}>
      <div className="chart-body">
        <div className="y-labels" style={{ height: H }}>
          <span>{formatNumber(hi)}</span>
          <span>{formatNumber(lo)}</span>
        </div>
        <svg viewBox={`0 0 ${W} ${H}`} style={{ height: H }} preserveAspectRatio="none" role="img" aria-label="收盘价走势">
          <path d={path(closes, x, y)} className={`line price ${up ? "up" : "down"}`} vectorEffect="non-scaling-stroke" />
          {h != null && <line x1={x(h)} x2={x(h)} y1="0" y2={H} className="crosshair" vectorEffect="non-scaling-stroke" />}
        </svg>
      </div>
      <div className="x-labels">
        <span>{bars[0].trade_time.slice(0, 10)}</span>
        <span>{bars[bars.length - 1].trade_time.slice(0, 10)}</span>
      </div>
      {h != null && (
        <div className="chart-tip" style={{ left: `${(h / (bars.length - 1)) * 100}%` }}>
          <strong>{bars[h].trade_time.slice(0, 16)}</strong>
          <span>收盘 {formatNumber(bars[h].close)}</span>
        </div>
      )}
    </div>
  );
}
