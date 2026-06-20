# 第七阶段交付物：回测报告可视化

版本：v0.1  
阶段：第七阶段 - 可视化分析  
日期：2026-06-20  
前置依赖：

- 第五阶段：回测引擎输出 `report.json`、`trades.csv`、`equity_curve.csv`。
- 第六阶段：策略模板库批量回测输出。

目标：把回测引擎产生的数据转化为用户可阅读的回测报告页面，展示核心指标、权益曲线、回撤曲线、价格走势、交易明细和权益数据。

## 1. 阶段范围

本阶段完成静态 HTML 可视化 MVP。

已完成：

- HTML 报告生成器。
- 指标卡片。
- 权益曲线。
- 回撤曲线。
- 收盘价曲线。
- 交易明细表。
- 权益曲线数据表。
- 可离线打开的 HTML 报告。
- 支持读取第五阶段和第六阶段的 `report.json`。

暂不包含：

- 前端框架接入。
- 实时 API 查询。
- 交互式缩放图表。
- 多策略对比。
- PDF 导出。
- 登录态和用户权限。

## 2. 交付文件

| 文件 | 说明 |
|---|---|
| `visualization_module/report_visualizer.py` | 回测报告 HTML 生成器 |
| `visualization_module/output/price_breakout_report.html` | 价格突破策略可视化报告 |
| `visualization_module/output/volume_breakout_report.html` | 成交量突破策略可视化报告 |
| `visualization_module/visualization-delivery.md` | 第七阶段交付说明 |

## 3. 输入数据

输入为第五阶段回测引擎生成的 `report.json`：

```json
{
  "strategy_id": "template_price_breakout",
  "strategy_name": "价格突破策略",
  "symbol": "600519.SH",
  "frequency": "1d",
  "start_date": "2024-01-02",
  "end_date": "2024-01-08",
  "metrics": {},
  "trades": [],
  "equity_curve": []
}
```

可视化模块主要读取：

- `metrics`
- `trades`
- `equity_curve`

## 4. 页面结构

可视化报告包含：

| 区域 | 内容 |
|---|---|
| 顶部摘要 | 策略名称、股票代码、频率、回测区间 |
| 策略摘要 | 策略 ID、初始资金、平均持仓 K 线 |
| 指标卡片 | 最终权益、总收益率、年化收益、最大回撤、胜率、交易次数、夏普比率、手续费 |
| 曲线分析 | 权益曲线、收盘价曲线、回撤曲线 |
| 交易明细 | 买入时间、卖出时间、价格、数量、净收益、手续费、卖出原因 |
| 权益数据 | 每根 K 线的现金、持仓、收盘价、权益和回撤 |

## 5. 生成命令

使用 Codex 内置 Python：

```powershell
& 'C:\Users\huawei\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' visualization_module\report_visualizer.py backtest_module\output\price_breakout_demo\report.json --output visualization_module\output\price_breakout_report.html --title 价格突破演示策略
```

另一个模板报告示例：

```powershell
& 'C:\Users\huawei\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' visualization_module\report_visualizer.py template_module\output\tpl_volume_breakout\report.json --output visualization_module\output\volume_breakout_report.html --title 成交量突破策略
```

## 6. 已生成报告

| 报告 | 来源 |
|---|---|
| `visualization_module/output/price_breakout_report.html` | 第五阶段价格突破演示策略 |
| `visualization_module/output/volume_breakout_report.html` | 第六阶段成交量突破模板 |

这两个文件可以直接用浏览器打开查看。

## 7. 验证结果

已验证：

- 可以读取第五阶段 `backtest_module/output/price_breakout_demo/report.json`。
- 可以读取第六阶段 `template_module/output/tpl_volume_breakout/report.json`。
- 可以生成 HTML 文件。
- HTML 中包含指标卡、曲线图、交易明细和权益数据。
- 不依赖网络和第三方 JavaScript 库。

## 8. 与原型页面的衔接

第二阶段原型中的“回测报告”页面后续可以升级为：

1. 后端回测完成后生成 `report.json`。
2. 前端通过 API 获取报告数据。
3. 前端按本阶段页面结构渲染：
   - 指标卡片。
   - 曲线图。
   - 交易表格。
   - 权益数据。
4. 用户可从策略编辑器点击“运行回测”后进入报告页。

当前 HTML 生成器相当于一个静态版报告页面，可作为真实前端开发的 UI 和数据结构参考。

## 9. 当前限制

当前曲线图使用内联 SVG 绘制，适合 MVP 展示。后续正式前端建议接入：

- ECharts。
- TradingView Lightweight Charts。
- 或基于 Canvas/SVG 的自研图表组件。

当前未实现：

- 鼠标悬浮 tooltip。
- 图表缩放。
- 多策略叠加对比。
- 买卖点标记。
- 导出 PDF。

## 10. 下一步建议

下一阶段建议做“参数优化”：

- 对策略参数进行网格搜索。
- 批量运行回测。
- 输出参数组合排行榜。
- 生成参数热力图或对比表。

也可以先做“前端集成”，把策略模板库、策略编辑器、回测引擎和报告页整合成一个最小 Web 应用。
