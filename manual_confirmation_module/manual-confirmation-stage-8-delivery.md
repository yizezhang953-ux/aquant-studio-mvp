# 实盘应用阶段八交付物：人工确认下单工作流

版本：v0.2-stage-8  
阶段：实盘应用路线阶段八  
状态：已完成本地实现，仍不直接连接真实券商  

## 1. 阶段目标

阶段八让影子交易产生的可行订单必须经过人工确认，才能导出为可提交订单。未确认订单不能进入交易网关。

## 2. 新增文件

| 文件 | 说明 |
|---|---|
| `manual_confirmation_module/confirmation_workflow.py` | 人工确认工作流 |
| `manual_confirmation_module/configs/manual_approvals.json` | 审批样例 |
| `manual_confirmation_module/manual-confirmation-stage-8-delivery.md` | 阶段八交付说明 |

## 3. 当前能力

- 从影子交易报告生成待确认订单。
- 过滤不可行理论订单。
- 应用人工审批结果。
- 审批通过后导出 approved order。
- 审批缺失或拒绝时不导出订单。
- approved order 包含审批人、审批时间和审批备注。

## 4. 验收命令

生成待确认订单：

```powershell
python manual_confirmation_module\confirmation_workflow.py prepare --shadow-report shadow_trading_module\output\stage7_shadow_report.json --pending manual_confirmation_module\output\stage8_pending_orders.json
```

应用审批：

```powershell
python manual_confirmation_module\confirmation_workflow.py apply --pending manual_confirmation_module\output\stage8_pending_orders.json --approvals manual_confirmation_module\configs\manual_approvals.json --output manual_confirmation_module\output\stage8_manual_confirmation_result.json
```

## 5. 验收结果

| 场景 | 结果 |
|---|---|
| 从影子报告生成待确认订单 | 1 条 |
| 应用审批 | 1 条 approved order |
| 不可行理论订单 | 不进入待确认列表 |

## 6. 下一阶段

下一阶段进入：

```text
阶段九：小资金限额自动化
```

重点补充：

- 自动交易白名单。
- 单笔金额上限。
- 单日金额上限。
- 仅允许 approved/manual 或白名单来源。
- 自动熔断。
