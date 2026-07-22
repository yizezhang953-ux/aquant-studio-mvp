# 实盘应用阶段二交付物：A 股与港股交易规则模块

版本：v0.2-stage-2  
阶段：实盘应用路线阶段二  
状态：已完成本地实现，仍禁止真实实盘  

## 1. 阶段目标

阶段二把交易规则从交易网关里抽离为独立模块，让回测、模拟盘、风控网关和未来券商适配器可以共用同一套规则。

本阶段新增对以下市场的规则支持：

- 中国 A 股。
- 港股。

## 2. 新增文件

| 文件 | 说明 |
|---|---|
| `market_rules_module/market_rules.py` | 市场识别、交易规则校验、费用估算 |
| `market_rules_module/configs/market_rules.json` | A 股与港股规则配置 |
| `market_rules_module/market-rules-stage-2-delivery.md` | 阶段二交付说明 |
| `trading_gateway_module/sample_orders/buy_00700_hk.json` | 港股订单样例 |

## 3. 修改文件

| 文件 | 说明 |
|---|---|
| `trading_gateway_module/trading_gateway.py` | 接入市场规则模块；沙箱成交使用规则费用模型 |
| `trading_gateway_module/configs/sandbox_gateway.json` | 增加港股白名单和规则文件路径 |
| `trading_gateway_module/sample_orders/buy_600519.json` | 按 A 股买入一手规则改为 100 股 |
| `trading_gateway_module/sample_orders/oversized_order.json` | 调整为仍会触发超额拒单 |

## 4. 当前规则能力

### A 股

- 股票代码格式：`600519.SH`、`000001.SZ`。
- 买入数量必须为 100 股整数倍。
- 卖出支持按配置检查可卖数量，为 T+1 做准备。
- 费用模型支持佣金、过户费、卖出印花税。
- 涨跌停字段已预留，当前沙箱不强制要求行情上下限字段。

### 港股

- 股票代码格式：`00700.HK`。
- 支持每只股票配置不同 board lot。
- 当前样例支持：
  - `00700.HK`: 100 股一手。
  - `00005.HK`: 400 股一手。
  - `09988.HK`: 100 股一手。
- 支持港股常见限价订单类型。
- 费用模型支持经纪佣金、证监会交易征费、会财局交易征费、交易费、股票印花税和转手纸印花税配置。

## 5. 验收命令

规则文件校验：

```powershell
python market_rules_module\market_rules.py --rules market_rules_module\configs\market_rules.json
```

A 股订单：

```powershell
python trading_gateway_module\trading_gateway.py trading_gateway_module\sample_orders\buy_600519.json --config trading_gateway_module\configs\sandbox_gateway.json --output-dir trading_gateway_module\output\stage2_verify_a_share
```

港股订单：

```powershell
python trading_gateway_module\trading_gateway.py trading_gateway_module\sample_orders\buy_00700_hk.json --config trading_gateway_module\configs\sandbox_gateway.json --output-dir trading_gateway_module\output\stage2_verify_hk
```

超额拒单：

```powershell
python trading_gateway_module\trading_gateway.py trading_gateway_module\sample_orders\oversized_order.json --config trading_gateway_module\configs\sandbox_gateway.json --output-dir trading_gateway_module\output\stage2_verify_reject
```

## 6. 验收结果

| 场景 | 结果 |
|---|---|
| 规则文件校验 | 通过 |
| A 股 600519.SH 买入 100 股 | 通过，状态 `filled` |
| 港股 00700.HK 买入 100 股 | 通过，状态 `filled` |
| A 股超额订单 | 通过，状态 `risk_rejected` |

## 7. 重要说明

交易费用、港股 board lot、交易规则和监管要求都可能变化。当前实现采用配置文件而不是硬编码，正式实盘前必须由券商和交易所最新规则复核。

## 8. 下一阶段

下一阶段进入：

```text
阶段三：风控网关增强
```

重点补充：

- 单日订单数量限制。
- 单日成交额限制。
- 受限标的。
- 允许来源。
- 全局熔断开关。
- 重复订单识别。
