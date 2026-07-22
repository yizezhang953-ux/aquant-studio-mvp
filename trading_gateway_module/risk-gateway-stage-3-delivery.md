# 实盘应用阶段三交付物：风控网关增强

版本：v0.2-stage-3  
阶段：实盘应用路线阶段三  
状态：已完成本地实现，仍禁止真实实盘  

## 1. 阶段目标

阶段三在基础订单风控之外，增加面向实盘运行的保护层。它位于市场规则校验之后、券商适配器提交之前。

主链路：

```text
策略订单 -> OMS -> 市场规则 -> 基础资金风控 -> 运行时风控网关 -> BrokerAdapter
```

## 2. 新增文件

| 文件 | 说明 |
|---|---|
| `trading_gateway_module/risk_gateway.py` | 运行时风控网关 |
| `trading_gateway_module/risk-gateway-stage-3-delivery.md` | 阶段三交付说明 |
| `trading_gateway_module/sample_orders/blocked_source_order.json` | 来源白名单拒单样例 |
| `trading_gateway_module/sample_orders/invalid_hk_lot_order.json` | 港股 board lot 拒单样例 |

## 3. 修改文件

| 文件 | 说明 |
|---|---|
| `trading_gateway_module/trading_gateway.py` | 接入运行时风控网关 |
| `trading_gateway_module/configs/sandbox_gateway.json` | 增加 `runtime_risk_controls` |

## 4. 当前风控能力

- 全局熔断开关。
- 订单来源白名单。
- 受限标的拒单。
- 重复 `client_order_id` 拒单。
- 单日订单数量限制。
- 单日提交订单数量限制。
- 单日提交成交额限制。
- 单标的仓位价值占比限制。
- 单日亏损限制预留。

## 5. 验收命令

来源拒单：

```powershell
python trading_gateway_module\trading_gateway.py trading_gateway_module\sample_orders\blocked_source_order.json --config trading_gateway_module\configs\sandbox_gateway.json --output-dir trading_gateway_module\output\stage3_verify_blocked_source
```

港股 board lot 拒单：

```powershell
python trading_gateway_module\trading_gateway.py trading_gateway_module\sample_orders\invalid_hk_lot_order.json --config trading_gateway_module\configs\sandbox_gateway.json --output-dir trading_gateway_module\output\stage3_verify_hk_lot
```

重复订单测试：

```powershell
python trading_gateway_module\trading_gateway.py trading_gateway_module\sample_orders\buy_00700_hk.json --config trading_gateway_module\configs\sandbox_gateway.json --output-dir trading_gateway_module\output\stage3_verify_duplicate
python trading_gateway_module\trading_gateway.py trading_gateway_module\sample_orders\buy_00700_hk.json --config trading_gateway_module\configs\sandbox_gateway.json --output-dir trading_gateway_module\output\stage3_verify_duplicate
```

## 6. 验收结果

| 场景 | 结果 |
|---|---|
| 未授权来源 `unapproved_robot` | 拒单 |
| 港股 `00005.HK` 非 400 股整数倍 | 拒单 |
| 同一 `client_order_id` 重复提交 | 第二次拒单 |

## 7. 下一阶段

下一阶段进入：

```text
阶段四：模拟盘升级
```

重点补充：

- 事件驱动模拟撮合。
- 订单提交、成交、撤单事件。
- 部分成交能力。
- 更接近真实账户的资金和持仓快照。
