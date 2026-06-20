# 第十阶段交付物：交易网关与沙箱券商适配器

版本：v0.1  
阶段：第十阶段 - 实盘接口前置层  
日期：2026-06-20  
前置依赖：

- 第九阶段：模拟盘订单、成交和账户状态概念。
- 第八阶段：参数优化后的候选策略。

目标：建立从策略信号到交易接口之间的安全边界，先实现沙箱券商适配器、订单风控、账户状态和审计日志，为未来接入真实券商 API 做准备。

## 1. 重要边界

本阶段不是正式实盘交易系统。

当前实现：

- 不连接真实券商。
- 不发送真实订单。
- 不读取真实资金账户。
- 不托管资金。
- 不构成投资建议。
- 默认 `live_trading_enabled = false`。

本阶段交付的是“实盘接口前置层”：订单协议、风控校验、沙箱适配器、账户状态和审计日志。

## 2. 已完成能力

- 统一订单输入格式。
- 交易网关配置。
- 沙箱券商适配器。
- A 股股票代码校验。
- 标的白名单。
- 买卖方向白名单。
- 最大订单金额限制。
- 最大数量限制。
- 现金不足拒单。
- 禁止裸卖空。
- 沙箱成交。
- 手续费与滑点。
- 订单记录。
- 成交记录。
- 账户状态。
- 审计日志。

## 3. 交付文件

| 文件 | 说明 |
|---|---|
| `trading_gateway_module/trading_gateway.py` | 交易网关与沙箱券商适配器 |
| `trading_gateway_module/configs/sandbox_gateway.json` | 沙箱网关配置 |
| `trading_gateway_module/sample_orders/buy_600519.json` | 正常买入订单样例 |
| `trading_gateway_module/sample_orders/oversized_order.json` | 超额订单拒单样例 |
| `trading_gateway_module/output/sandbox/orders.csv` | 网关订单记录 |
| `trading_gateway_module/output/sandbox/fills.csv` | 沙箱成交记录 |
| `trading_gateway_module/output/sandbox/account_state.json` | 沙箱账户状态 |
| `trading_gateway_module/output/sandbox/audit_log.csv` | 审计日志 |
| `trading_gateway_module/output/sandbox/last_order_result.json` | 最近一次订单处理结果 |
| `trading_gateway_module/trading-gateway-delivery.md` | 第十阶段交付说明 |

## 4. 网关配置

配置文件：

```text
trading_gateway_module/configs/sandbox_gateway.json
```

关键配置：

```json
{
  "mode": "sandbox",
  "broker_adapter": "sandbox_a_share",
  "live_trading_enabled": false,
  "account": {
    "initial_cash": 100000,
    "fee_rate": 0.0003,
    "slippage_rate": 0.0005
  },
  "risk_limits": {
    "allowed_symbols": ["600519.SH", "000001.SZ", "300750.SZ"],
    "max_order_value": 30000,
    "max_quantity": 1000,
    "reject_short_sell": true
  }
}
```

## 5. 订单协议

订单样例：

```json
{
  "client_order_id": "CLIENT-ORDER-0001",
  "strategy_id": "template_price_breakout_entry_threshold_1680_exit_threshold_1670_order_size_0_2",
  "symbol": "600519.SH",
  "side": "buy",
  "order_type": "market",
  "quantity": 11,
  "estimated_price": 1683.34125,
  "reason": "entry_rule",
  "source": "paper_trading_promotion"
}
```

## 6. 运行命令

### 6.1 正常订单

```powershell
& 'C:\Users\huawei\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' trading_gateway_module\trading_gateway.py trading_gateway_module\sample_orders\buy_600519.json --config trading_gateway_module\configs\sandbox_gateway.json --output-dir trading_gateway_module\output\sandbox
```

验证结果：

- 风控通过。
- 订单状态：`filled`。
- 成交数量：`11`。
- 成交价格：`1684.182921`。
- 手续费：`5.557804`。
- 持仓更新为 `600519.SH: 11`。

### 6.2 超额订单

```powershell
& 'C:\Users\huawei\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' trading_gateway_module\trading_gateway.py trading_gateway_module\sample_orders\oversized_order.json --config trading_gateway_module\configs\sandbox_gateway.json --output-dir trading_gateway_module\output\sandbox
```

验证结果：

- 风控拒绝。
- 拒绝原因：
  - `order value exceeds max_order_value`
  - `cash is insufficient`
- 没有生成成交。

## 7. 当前输出

订单记录：

| 订单 | 状态 | 说明 |
|---|---|---|
| `CLIENT-ORDER-0001` | `filled` | 正常买入，沙箱成交 |
| `CLIENT-ORDER-REJECT-0001` | `rejected` | 超过订单金额限制，拒单 |

账户状态：

```json
{
  "account_id": "sandbox_account_001",
  "cash": 81468.430069,
  "positions": {
    "600519.SH": 11
  }
}
```

## 8. 风控规则

当前已实现：

| 风控项 | 说明 |
|---|---|
| 市场边界 | 股票代码必须为 A 股格式 |
| 标的白名单 | 只允许配置中的股票 |
| 方向白名单 | 只允许 buy / sell |
| 数量校验 | 数量必须为正整数 |
| 最大数量 | 超过 `max_quantity` 拒单 |
| 最大订单金额 | 超过 `max_order_value` 拒单 |
| 现金校验 | 买入金额超过现金拒单 |
| 卖空校验 | 持仓不足时卖出拒单 |
| 实盘锁 | `live_trading_enabled` 必须为 false |

## 9. 审计日志

审计日志文件：

```text
trading_gateway_module/output/sandbox/audit_log.csv
```

记录事件：

- `order_received`
- `risk_check`
- `order_filled`

每条日志包含：

- 时间戳。
- 事件类型。
- 状态。
- 消息。
- 原始 payload。

## 10. 未来接真实券商的接口边界

后续真实券商适配器应实现同样的接口：

```text
submit_order(order) -> fill / broker_order_ack
query_account() -> account_state
query_positions() -> positions
cancel_order(order_id) -> cancel_result
query_order(order_id) -> order_status
```

真实券商适配器必须放在交易网关之后，不能让策略模块直接调用券商 API。

## 11. 上线实盘前必须补充

实盘前必须另行完成：

- 券商 API 认证和密钥管理。
- 真实账户权限隔离。
- 人工确认开关。
- 每日最大亏损限制。
- 单笔/单日最大下单金额。
- 熔断机制。
- 订单撤单。
- 订单状态回报。
- 网络异常重试。
- 完整审计日志。
- 合规风险提示。
- A 股 T+1、100 股一手、涨跌停、停牌、印花税和最低佣金规则。

## 12. 第十阶段结论

第十阶段已经完成从“模拟盘订单”到“交易网关”的安全过渡。

现在项目具备：

1. 策略订单协议。
2. 风控前置校验。
3. 沙箱券商适配器。
4. 账户状态落盘。
5. 订单与成交审计。

下一阶段建议做“安全与合规层”，进一步完善权限、日志、风控、免责声明和实盘前检查清单。
