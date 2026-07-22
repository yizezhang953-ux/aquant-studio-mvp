# 实盘应用阶段五交付物：Broker Adapter 抽象

版本：v0.2-stage-5  
阶段：实盘应用路线阶段五  
状态：已完成本地实现，仍禁止真实实盘  

## 1. 阶段目标

阶段五把券商相关能力抽象为统一接口。交易网关只依赖 `BrokerAdapter`，未来任何真实券商适配器都必须实现该接口，不能让策略、回测或模拟盘直接调用券商 API。

## 2. 新增文件

| 文件 | 说明 |
|---|---|
| `broker_adapter_module/broker_adapter.py` | Broker Adapter 抽象接口与沙箱实现 |
| `broker_adapter_module/broker-adapter-stage-5-delivery.md` | 阶段五交付说明 |

## 3. 当前接口

统一接口包含：

- `query_account()`
- `query_positions()`
- `submit_order(order)`
- `cancel_order(broker_order_id)`
- `query_order(broker_order_id)`
- `query_fills(broker_order_id)`

## 4. 当前实现

当前实现：

```text
SandboxBrokerAdapter
```

它会：

- 接收网关订单。
- 返回 broker ack。
- 生成沙箱成交。
- 更新账户资金。
- 更新持仓。
- 复用 A 股和港股费用规则。

## 5. 网关变化

交易网关现在输出：

- `broker_ack`
- `broker_order_id`
- `fill`
- `oms`
- `audit_log`

这意味着后续真实券商接入时，可以区分：

```text
网关订单号 gateway_order_id
券商订单号 broker_order_id
成交编号 fill_id
```

## 6. 验收命令

```powershell
python trading_gateway_module\trading_gateway.py trading_gateway_module\sample_orders\buy_00700_hk.json --config trading_gateway_module\configs\sandbox_gateway.json --output-dir trading_gateway_module\output\stage5_verify_broker_adapter_final
```

## 7. 验收结果

| 场景 | 结果 |
|---|---|
| 港股沙箱订单 | 成功成交 |
| broker ack | 正常输出 |
| broker_order_id | 正常写入 fill 和 OMS |
| 原有风控链路 | 保持有效 |

## 8. 下一阶段

下一阶段进入：

```text
阶段六：账户只读接入
```

重点补充：

- 只读账户接口。
- 只读持仓接口。
- 只读委托和成交接口。
- 禁止下单的真实账户预备适配器。
