# 实盘应用阶段七交付物：影子交易

版本：v0.2-stage-7  
阶段：实盘应用路线阶段七  
状态：已完成本地实现，不会提交真实订单  

## 1. 阶段目标

阶段七让策略理论订单和只读账户快照进行对比，判断如果进入交易链路是否可行，但不提交任何订单。

## 2. 新增文件

| 文件 | 说明 |
|---|---|
| `shadow_trading_module/shadow_trader.py` | 影子交易评估器 |
| `shadow_trading_module/configs/shadow_demo.json` | 影子交易演示配置 |
| `shadow_trading_module/shadow-trading-stage-7-delivery.md` | 阶段七交付说明 |

## 3. 当前能力

- 读取只读账户快照。
- 读取策略理论订单。
- 复用 A 股与港股市场规则。
- 估算交易费用。
- 检查现金是否足够。
- 检查持仓和可卖数量。
- 输出可行性报告。
- 明确 `would_submit = false`。

## 4. 验收命令

```powershell
python shadow_trading_module\shadow_trader.py --config shadow_trading_module\configs\shadow_demo.json --output shadow_trading_module\output\stage7_shadow_report.json
```

## 5. 验收结果

| 场景 | 结果 |
|---|---|
| 港股 00700.HK 理论买入 | 可行 |
| A 股 600519.SH 理论卖出 | 因 T+1 / 可卖数量不足不可行 |
| 是否提交订单 | 否 |

## 6. 下一阶段

下一阶段进入：

```text
阶段八：人工确认下单
```

重点补充：

- 待确认订单包。
- 人工批准/拒绝记录。
- 未批准订单不得进入网关。
- 审批结果可审计。
