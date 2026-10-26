import { LogicMode, Operand, RuleCondition, RuleGroup } from "./api";

// Visual editor for the strategy DSL's entry/exit rules: every condition reads as a sentence,
// e.g. [均线 MA 20] [上穿] [均线 MA 60]. Covers every indicator the validator supports.

type ParamSpec = { key: string; label: string; default: number | string; options?: { value: string; label: string }[] };

const INDICATORS: Record<string, { label: string; params: ParamSpec[] }> = {
  MA: { label: "均线 MA", params: [{ key: "period", label: "周期", default: 20 }] },
  EMA: { label: "指数均线 EMA", params: [{ key: "period", label: "周期", default: 20 }] },
  RSI: { label: "RSI", params: [{ key: "period", label: "周期", default: 14 }] },
  MACD: {
    label: "MACD",
    params: [
      { key: "fast", label: "快线", default: 12 },
      { key: "slow", label: "慢线", default: 26 },
      { key: "signal", label: "信号", default: 9 },
      {
        key: "output",
        label: "取值",
        default: "macd",
        options: [
          { value: "macd", label: "DIF" },
          { value: "signal", label: "DEA" },
          { value: "hist", label: "柱" },
        ],
      },
    ],
  },
  BOLL: {
    label: "布林带 BOLL",
    params: [
      { key: "period", label: "周期", default: 20 },
      { key: "std", label: "倍数", default: 2 },
      {
        key: "output",
        label: "轨道",
        default: "middle",
        options: [
          { value: "upper", label: "上轨" },
          { value: "middle", label: "中轨" },
          { value: "lower", label: "下轨" },
        ],
      },
    ],
  },
  VOLUME_MA: { label: "均量", params: [{ key: "period", label: "周期", default: 5 }] },
  RETURN: { label: "N 日涨幅", params: [{ key: "period", label: "天数", default: 3 }] },
  VOLATILITY: { label: "波动率", params: [{ key: "period", label: "周期", default: 20 }] },
};

const PRICE_FIELDS: Record<string, string> = {
  close: "收盘价",
  open: "开盘价",
  high: "最高价",
  low: "最低价",
  volume: "成交量",
  amount: "成交额",
};

export const OPERATORS: Record<string, string> = {
  cross_above: "上穿",
  cross_below: "下穿",
  gt: "大于",
  gte: "大于等于",
  lt: "小于",
  lte: "小于等于",
  eq: "等于",
};

/** Encodes an operand's kind for the <select>: "price:close", "indicator:MA", "constant". */
function kindOf(operand?: Operand) {
  if (!operand || operand.type === "constant") return "constant";
  if (operand.type === "price") return `price:${operand.field || "close"}`;
  return `indicator:${operand.name || "MA"}`;
}

function operandFromKind(kind: string, previous?: Operand): Operand {
  if (kind === "constant") return { type: "constant", value: previous?.type === "constant" ? previous.value ?? 0 : 0 };
  const [type, name] = kind.split(":");
  if (type === "price") return { type: "price", field: name };
  const spec = INDICATORS[name];
  const params: Record<string, number | string> = {};
  for (const param of spec.params) params[param.key] = param.default;
  if (name !== "VOLUME_MA") params.field = "close";
  return { type: "indicator", name, params };
}

export function describeOperand(operand?: Operand): string {
  if (!operand) return "?";
  if (operand.type === "constant") return String(operand.value ?? 0);
  if (operand.type === "price") return PRICE_FIELDS[operand.field || "close"] || operand.field || "价格";
  const name = operand.name || "";
  const params = operand.params || {};
  if (name === "MACD") return `MACD(${params.fast ?? 12},${params.slow ?? 26},${params.signal ?? 9})`;
  if (name === "BOLL") return `BOLL${params.period ?? 20}`;
  if (name === "RETURN") return `${params.period ?? 3}日涨幅`;
  if (name === "VOLUME_MA") return `${params.period ?? 5}日均量`;
  return `${name}${params.period ?? ""}`;
}

export function describeGroup(group?: RuleGroup): string {
  const conditions = group?.conditions || [];
  if (!conditions.length) return "未设置";
  const joiner = group?.logic === "any" ? " 或 " : " 且 ";
  return conditions
    .map((c) => `${describeOperand(c.left)} ${OPERATORS[c.operator || ""] || c.operator} ${describeOperand(c.right)}`)
    .join(joiner);
}

function OperandInput({ operand, allowConstant, onChange }: { operand?: Operand; allowConstant: boolean; onChange: (next: Operand) => void }) {
  const kind = kindOf(operand);
  const indicatorName = operand?.type === "indicator" ? operand.name || "MA" : "";
  const spec = indicatorName ? INDICATORS[indicatorName] : null;
  return (
    <span className="operand">
      <select
        aria-label="比较对象"
        value={kind}
        onChange={(event) => onChange(operandFromKind(event.target.value, operand))}
      >
        <optgroup label="指标">
          {Object.entries(INDICATORS).map(([key, item]) => (
            <option key={key} value={`indicator:${key}`}>
              {item.label}
            </option>
          ))}
        </optgroup>
        <optgroup label="行情">
          {Object.entries(PRICE_FIELDS).map(([key, label]) => (
            <option key={key} value={`price:${key}`}>
              {label}
            </option>
          ))}
        </optgroup>
        {allowConstant && <option value="constant">固定数值</option>}
      </select>
      {operand?.type === "constant" && (
        <input
          className="num-input"
          aria-label="数值"
          inputMode="decimal"
          value={String(operand.value ?? 0)}
          onChange={(event) => {
            const parsed = Number(event.target.value);
            onChange({ ...operand, value: Number.isFinite(parsed) ? parsed : 0 });
          }}
        />
      )}
      {spec?.params.map((param) =>
        param.options ? (
          <select
            key={param.key}
            aria-label={param.label}
            value={String(operand?.params?.[param.key] ?? param.default)}
            onChange={(event) => onChange({ ...operand, params: { ...operand?.params, [param.key]: event.target.value } })}
          >
            {param.options.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        ) : (
          <label className="param" key={param.key}>
            <span>{param.label}</span>
            <input
              className="num-input"
              inputMode="numeric"
              value={String(operand?.params?.[param.key] ?? param.default)}
              onChange={(event) => {
                const parsed = Number(event.target.value);
                onChange({ ...operand, params: { ...operand?.params, [param.key]: Number.isFinite(parsed) ? parsed : 0 } });
              }}
            />
          </label>
        ),
      )}
    </span>
  );
}

function ConditionRow({
  condition,
  onChange,
  onRemove,
  removable,
}: {
  condition: RuleCondition;
  onChange: (next: RuleCondition) => void;
  onRemove: () => void;
  removable: boolean;
}) {
  const leftIsReturn = condition.left?.type === "indicator" && condition.left.name === "RETURN";
  return (
    <div className="condition-row">
      <OperandInput operand={condition.left} allowConstant={false} onChange={(left) => onChange({ ...condition, left })} />
      <select
        className="operator"
        aria-label="条件"
        value={condition.operator || "gt"}
        onChange={(event) => onChange({ ...condition, operator: event.target.value })}
      >
        {Object.entries(OPERATORS).map(([key, label]) => (
          <option key={key} value={key}>
            {label}
          </option>
        ))}
      </select>
      <OperandInput operand={condition.right} allowConstant onChange={(right) => onChange({ ...condition, right })} />
      {removable && (
        <button type="button" className="icon-button" onClick={onRemove} aria-label="删除这个条件" title="删除这个条件">
          ×
        </button>
      )}
      {leftIsReturn && condition.right?.type === "constant" && <small className="row-hint">0.01 表示 1%</small>}
    </div>
  );
}

export function RuleGroupEditor({
  title,
  tone,
  group,
  onChange,
}: {
  title: string;
  tone: "entry" | "exit";
  group: RuleGroup;
  onChange: (next: RuleGroup) => void;
}) {
  const conditions = group.conditions?.length ? group.conditions : [];
  const update = (index: number, next: RuleCondition) =>
    onChange({ ...group, conditions: conditions.map((item, i) => (i === index ? next : item)) });
  return (
    <section className={`rule-group ${tone}`}>
      <header>
        <h4>{title}</h4>
        {conditions.length > 1 && (
          <select
            aria-label="条件组合方式"
            value={group.logic || "all"}
            onChange={(event) => onChange({ ...group, logic: event.target.value as LogicMode })}
          >
            <option value="all">同时满足以下条件</option>
            <option value="any">满足任一条件</option>
          </select>
        )}
      </header>
      {conditions.length === 0 && <p className="muted">还没有条件。</p>}
      {conditions.map((condition, index) => (
        <ConditionRow
          key={index}
          condition={condition}
          removable={conditions.length > 1}
          onChange={(next) => update(index, next)}
          onRemove={() => onChange({ ...group, conditions: conditions.filter((_, i) => i !== index) })}
        />
      ))}
      <button
        type="button"
        className="text-button"
        onClick={() =>
          onChange({
            logic: group.logic || "all",
            conditions: [
              ...conditions,
              { left: { type: "price", field: "close" }, operator: "gt", right: operandFromKind("indicator:MA") },
            ],
          })
        }
      >
        + 添加条件
      </button>
    </section>
  );
}
