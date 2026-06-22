# 阶段 10 交付物：策略版本与回测绑定

版本：V2.1 Stage 10  
日期：2026-06-22  
状态：已完成回测与策略版本、参数摘要的绑定。

## 1. 阶段目标

让每一次回测都能追溯到当时使用的策略版本和核心参数，避免只看到收益曲线却不知道它来自哪一次策略修改。

## 2. 已交付内容

- `backtest_runs` 新增：
  - `strategy_version`
  - `parameter_snapshot`
- SQLite 自动补字段迁移。
- 回测报告写入当时的完整策略 JSON。
- 登录用户运行回测时，后端自动查找来源策略的最新版本号。
- 回测历史返回版本号和参数摘要。
- 前端“我的回测记录”显示：
  - 版本号
  - 入场阈值
  - 出场阈值
  - 仓位比例
- 前端“回测对比”显示版本号与参数摘要。

## 3. 参数摘要字段

`parameter_snapshot` 当前记录：

- `symbol`
- `frequency`
- `start_date`
- `end_date`
- `entry_operator`
- `entry_value`
- `exit_operator`
- `exit_value`
- `order_size_value`
- `max_position_pct`
- `stop_loss_pct`
- `take_profit_pct`
- `max_drawdown_pct`

## 4. 使用流程

1. 用户编辑并保存策略，生成策略版本。
2. 用户运行回测。
3. 后端将回测绑定到来源策略和最新版本号。
4. 后端保存参数摘要。
5. 用户在历史记录和对比表中查看版本与参数。

## 5. 验收标准

- 后端测试通过。
- 前端 TypeScript 检查通过。
- Vite 构建通过。
- 结构检查通过。
- 登录用户回测历史中包含 `strategy_version` 和 `parameter_snapshot`。

## 6. 下一阶段建议

阶段 11 建议做“回测参数差异视图”：在选择两条回测时，自动高亮它们入场、出场、仓位和风控参数的差异。
