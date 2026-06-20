# 第四阶段交付物：策略 DSL 与编辑器数据结构

版本：v0.1  
阶段：第四阶段 - 策略 DSL / 编辑器数据结构  
日期：2026-06-20  
前置依赖：第三阶段 A 股行情数据模块  
目标：把第二阶段原型中的“买入规则、卖出规则、仓位风控”定义成可保存、可校验、可被回测引擎执行的 JSON 数据结构。

## 1. 阶段范围

本阶段完成策略规则的数据契约，不实现完整回测。

已完成：

- 策略 DSL v1.0。
- JSON Schema 草案。
- 双均线策略样例。
- RSI 波段策略样例。
- 策略校验器。
- 数据覆盖校验，可连接第三阶段 SQLite 行情库。

暂不包含：

- 可视化编辑器前端真实交互。
- 指标数值计算。
- 回测撮合逻辑。
- 策略参数自动优化。
- 用户自定义 Python 代码。

## 2. 交付文件

| 文件 | 说明 |
|---|---|
| `strategy_module/strategy_schema.json` | 策略 DSL JSON Schema |
| `strategy_module/strategy_validator.py` | 策略校验器 |
| `strategy_module/samples/double_ma_strategy.json` | 双均线趋势策略样例 |
| `strategy_module/samples/rsi_reversal_strategy.json` | RSI 波段反转策略样例 |
| `strategy_module/strategy-dsl-delivery.md` | 第四阶段交付说明 |

## 3. DSL 设计原则

### 3.1 安全

第一版不允许用户提交任意 Python、SQL 或脚本代码。用户只能通过白名单字段组合策略：

- 白名单指标。
- 白名单操作符。
- 白名单频率。
- 白名单市场。
- 白名单价格字段。

这样可以避免策略编辑器变成任意代码执行入口。

### 3.2 易于前端生成

策略编辑器里的每一个下拉框、输入框和条件组，都能直接映射到 JSON：

| 前端控件 | DSL 字段 |
|---|---|
| 股票代码输入框 | `universe.symbols` |
| 频率选择 | `data.frequency` |
| 指标选择 | `condition.left.name` / `condition.right.name` |
| 指标参数 | `expression.params` |
| 操作符选择 | `condition.operator` |
| 条件组全部/任意 | `rule_group.logic` |
| 仓位比例 | `position.order_size_value` |
| 止损止盈 | `risk.stop_loss_pct` / `risk.take_profit_pct` |

### 3.3 易于回测执行

回测引擎只需要读取：

1. `universe` 确定股票。
2. `data` 查询行情。
3. `entry` 判断买入。
4. `exit` 判断卖出。
5. `position` 计算下单金额。
6. `execution` 计算成交价、手续费、滑点。
7. `risk` 执行止损、止盈、最大回撤和持仓周期限制。

## 4. 顶层结构

```json
{
  "schema_version": "1.0",
  "strategy_id": "strategy_double_ma_600519",
  "name": "双均线趋势策略",
  "market": "a_share",
  "universe": {},
  "data": {},
  "entry": {},
  "exit": {},
  "position": {},
  "execution": {},
  "risk": {},
  "metadata": {}
}
```

## 5. 市场与标的

MVP 仅支持 A 股单标的。

```json
{
  "market": "a_share",
  "universe": {
    "type": "single",
    "symbols": ["600519.SH"]
  }
}
```

规则：

- `market` 必须是 `a_share`。
- `symbols` 只能有 1 个。
- 股票代码必须符合 `000001.SZ` 或 `600519.SH` 格式。

## 6. 数据设置

```json
{
  "data": {
    "frequency": "1d",
    "adjustment": "forward",
    "start_date": "2024-01-02",
    "end_date": "2024-01-08"
  }
}
```

支持频率：

- `1d`
- `60m`
- `30m`
- `15m`

复权方式：

- `forward`：前复权。
- `backward`：后复权。
- `none`：不复权。

## 7. 条件表达式

条件由三部分组成：

```json
{
  "left": {},
  "operator": "cross_above",
  "right": {}
}
```

### 7.1 表达式类型

支持三种表达式：

| 类型 | 用途 | 示例 |
|---|---|---|
| `price` | 价格/成交字段 | 收盘价、成交量 |
| `indicator` | 技术指标 | MA、RSI、MACD |
| `constant` | 固定数值 | 30、70、0.05 |

价格表达式：

```json
{
  "type": "price",
  "field": "close"
}
```

指标表达式：

```json
{
  "type": "indicator",
  "name": "MA",
  "params": {
    "period": 5,
    "field": "close"
  }
}
```

常量表达式：

```json
{
  "type": "constant",
  "value": 30
}
```

## 8. MVP 指标白名单

| 指标 | DSL 名称 | 必要参数 | 用途 |
|---|---|---|---|
| 简单移动平均线 | `MA` | `period`, `field` | 趋势 |
| 指数移动平均线 | `EMA` | `period`, `field` | 趋势 |
| MACD | `MACD` | `fast`, `slow`, `signal` 可选 | 趋势确认 |
| RSI | `RSI` | `period`, `field` | 超买超卖 |
| 布林带 | `BOLL` | `period`, `std` | 均值回归 |
| 成交量均线 | `VOLUME_MA` | `period` | 量能判断 |
| 收益率 | `RETURN` | `period`, `field` | 动量 |
| 波动率 | `VOLATILITY` | `period`, `field` | 风险 |

## 9. 操作符白名单

| 操作符 | 含义 |
|---|---|
| `gt` | 大于 |
| `lt` | 小于 |
| `eq` | 等于 |
| `gte` | 大于等于 |
| `lte` | 小于等于 |
| `cross_above` | 上穿 |
| `cross_below` | 下穿 |

## 10. 买入规则

示例：MA5 上穿 MA20 时买入。

```json
{
  "entry": {
    "logic": "all",
    "conditions": [
      {
        "left": {
          "type": "indicator",
          "name": "MA",
          "params": { "period": 5, "field": "close" }
        },
        "operator": "cross_above",
        "right": {
          "type": "indicator",
          "name": "MA",
          "params": { "period": 20, "field": "close" }
        }
      }
    ]
  }
}
```

## 11. 卖出规则

示例：MA5 下穿 MA20 时卖出。

```json
{
  "exit": {
    "logic": "any",
    "conditions": [
      {
        "left": {
          "type": "indicator",
          "name": "MA",
          "params": { "period": 5, "field": "close" }
        },
        "operator": "cross_below",
        "right": {
          "type": "indicator",
          "name": "MA",
          "params": { "period": 20, "field": "close" }
        }
      }
    ]
  }
}
```

## 12. 仓位规则

```json
{
  "position": {
    "initial_cash": 100000,
    "order_size_type": "cash_pct",
    "order_size_value": 0.3,
    "max_position_pct": 0.8
  }
}
```

MVP 只支持按资金比例下单：

- `order_size_type = cash_pct`
- `order_size_value = 0.3` 表示每次使用 30% 资金。
- `max_position_pct = 0.8` 表示最大持仓不超过 80%。

## 13. 成交设置

```json
{
  "execution": {
    "entry_price": "next_open",
    "exit_price": "next_open",
    "fee_rate": 0.0003,
    "slippage_rate": 0.0005
  }
}
```

支持：

- `next_open`：下一根 K 线开盘价。
- `current_close`：当前 K 线收盘价。

## 14. 风控规则

```json
{
  "risk": {
    "stop_loss_pct": 0.08,
    "take_profit_pct": 0.2,
    "max_drawdown_pct": 0.15,
    "max_holding_bars": null
  }
}
```

含义：

- `stop_loss_pct`: 单笔止损。
- `take_profit_pct`: 单笔止盈。
- `max_drawdown_pct`: 策略最大回撤停止交易。
- `max_holding_bars`: 最大持有 K 线数量。

## 15. 校验器用法

使用 Codex 内置 Python：

```powershell
& 'C:\Users\huawei\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' strategy_module\strategy_validator.py strategy_module\samples\double_ma_strategy.json --db data_module\market_data.sqlite
```

校验器会检查：

- 必填字段。
- A 股市场边界。
- 股票代码格式。
- 数据频率。
- 日期区间。
- 买入/卖出条件。
- 指标白名单。
- 操作符白名单。
- 仓位比例。
- 风控参数。
- 行情数据覆盖情况。

## 16. 与第三阶段数据模块的衔接

策略 DSL 中的数据字段：

```json
{
  "symbols": ["600519.SH"],
  "frequency": "1d",
  "start_date": "2024-01-02",
  "end_date": "2024-01-08"
}
```

会映射到第三阶段数据模块查询：

```text
query --symbol 600519.SH --frequency 1d --start 2024-01-02 --end 2024-01-08
```

后续回测引擎只需要使用相同参数获取 K 线数据。

## 17. 前端编辑器映射方式

### 策略编辑器页面

前端应维护一个策略 JSON 草稿对象。用户每修改一次控件，就更新对应字段。

示例：

| 用户动作 | JSON 更新 |
|---|---|
| 输入股票代码 | `universe.symbols[0]` |
| 选择 15 分钟线 | `data.frequency = "15m"` |
| 添加 MA 指标 | 新增 `indicator` expression |
| 选择“上穿” | `operator = "cross_above"` |
| 输入止损 8% | `risk.stop_loss_pct = 0.08` |

### 保存策略

保存前流程：

1. 前端做基础表单校验。
2. 后端使用 `strategy_validator.py` 的逻辑做强校验。
3. 校验通过后保存策略 JSON。
4. 校验失败则返回错误列表给前端。

## 18. 后续扩展点

后续可以扩展：

- 多标的股票池。
- 因子排序。
- 调仓周期。
- 行业/市值过滤器。
- 参数扫描。
- 样本内/样本外测试。
- 自定义指标库。
- 代码模式，但需要沙箱隔离。

## 19. 第四阶段结论

第四阶段已经把策略编辑器背后的核心数据结构确定下来。

现在产品已经具备：

1. 可导入和查询的 A 股行情数据。
2. 可保存的策略 JSON。
3. 可校验的买入、卖出、仓位和风控规则。
4. 数据覆盖检查能力。

下一阶段建议进入“回测引擎 MVP”，让双均线和 RSI 样例策略真正跑出交易记录、收益曲线和核心指标。
