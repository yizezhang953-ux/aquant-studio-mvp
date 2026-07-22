# 实盘应用阶段一交付物：交易主链路与 OMS 重构

版本：v0.2-stage-1  
阶段：实盘应用路线阶段一  
状态：已完成本地实现，仍禁止真实实盘  

## 1. 阶段目标

阶段一的目标不是连接真实券商，而是先把“策略信号”和“真实下单能力”解耦，形成可审计、可控制、可扩展的交易主链路。

本阶段完成：

- 新增订单管理系统 OMS。
- 建立订单生命周期状态机。
- 将订单接收、风控、提交适配器、成交结果串成统一流程。
- 保留实盘总闸门，默认禁止真实券商提交。
- 输出订单生命周期文件，便于审计和后续前端展示。

## 2. 当前安全边界

当前仓库仍然不能真实下单。

安全状态：

```text
live_trading_enabled = false
allow_real_broker_submit = false
mode = paper_trading
```

允许：

- 策略生成订单票据。
- 网关接收订单。
- 风控前置检查。
- 沙箱适配器模拟成交。
- 输出 OMS 与审计日志。

不允许：

- 连接真实券商。
- 发送真实订单。
- 自动使用真实账户资金。
- 绕过交易网关直接调用券商接口。

## 3. 新增文件

| 文件 | 说明 |
|---|---|
| `trading_gateway_module/order_management.py` | OMS 状态机与订单生命周期事件 |
| `trading_gateway_module/live-trading-stage-1-delivery.md` | 阶段一交付说明 |

## 4. 修改文件

| 文件 | 说明 |
|---|---|
| `trading_gateway_module/trading_gateway.py` | 接入 OMS；增加实盘策略闸门校验 |
| `trading_gateway_module/configs/sandbox_gateway.json` | 增加 `live_trading_policy` 配置 |

## 5. 订单生命周期

当前状态流：

```text
received
  -> risk_accepted
  -> submitted_to_broker
  -> filled
```

拒单状态流：

```text
received
  -> risk_rejected
```

异常状态流：

```text
received / risk_accepted / submitted_to_broker
  -> failed
```

## 6. OMS 输出

网关运行后新增输出：

| 输出文件 | 说明 |
|---|---|
| `trading_gateway_module/output/sandbox/oms_orders.json` | 当前订单与生命周期事件快照 |
| `trading_gateway_module/output/sandbox/order_lifecycle.csv` | 生命周期事件流水 |

原有输出仍保留：

- `orders.csv`
- `fills.csv`
- `audit_log.csv`
- `account_state.json`
- `last_order_result.json`

## 7. 验收命令

正常沙箱订单：

```powershell
python trading_gateway_module\trading_gateway.py trading_gateway_module\sample_orders\buy_600519.json --config trading_gateway_module\configs\sandbox_gateway.json --output-dir trading_gateway_module\output\sandbox
```

超额拒单订单：

```powershell
python trading_gateway_module\trading_gateway.py trading_gateway_module\sample_orders\oversized_order.json --config trading_gateway_module\configs\sandbox_gateway.json --output-dir trading_gateway_module\output\sandbox
```

## 8. 验收标准

| 场景 | 预期结果 |
|---|---|
| 正常订单 | 状态流包含 `received -> risk_accepted -> submitted_to_broker -> filled` |
| 超额订单 | 状态流包含 `received -> risk_rejected` |
| 实盘开关误开 | 订单会被拒绝，原因包含 `live_trading_enabled must remain false` |
| 真实券商提交误开 | 订单会被拒绝，原因包含 `real broker submission is blocked in stage 1` |

## 9. 对后续阶段的接口意义

阶段二和阶段三可以继续沿用这条主链路：

```text
策略信号 -> OMS -> 风控 -> BrokerAdapter -> 回报 -> 审计
```

后续接真实券商时，只应新增具体券商适配器，不能让策略模块直接调用券商 API。

## 10. 下一阶段

下一阶段建议进入：

```text
阶段二：A 股交易规则模块
```

重点补齐：

- T+1。
- 100 股一手。
- 涨跌停。
- 停牌。
- 交易日历。
- 印花税、过户费、最低佣金。
- 废单和可交易数量检查。
