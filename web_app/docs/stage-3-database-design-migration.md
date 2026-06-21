# 阶段 3 交付物：数据库设计与种子迁移

版本：V2.1 Stage 3  
日期：2026-06-21  
状态：已完成数据库结构、初始化接口和示例数据迁移。

## 1. 阶段目标

把阶段 2 的“文件驱动 API”升级为具备真实数据库基础的后端应用。当前阶段仍使用 SQLite 方便本地开发和演示，但代码层已经采用 SQLAlchemy ORM，后续可以迁移到 PostgreSQL。

## 2. 已交付内容

- 数据库会话层：`app/db/session.py`
- 初始化脚本：`app/db/init_db.py`
- 数据模型：策略模板、用户策略、行情标的、行情 K 线、回测运行、成交记录、权益曲线、审计日志
- 数据迁移服务：`app/services/database_service.py`
- 数据库 API：
  - `GET /api/v1/database/status`
  - `POST /api/v1/database/init`
- 测试用例：数据库初始化和状态查询
- 本地数据库文件忽略规则：`web_app/backend/*.db`

## 3. 数据表设计

| 表名 | 作用 |
|---|---|
| `strategy_templates` | 保存系统内置策略模板库 |
| `user_strategies` | 保存用户从模板复制或自主编辑的策略 |
| `market_instruments` | 保存 A 股股票标的基础信息 |
| `market_bars` | 保存日线、分钟线等行情 K 线 |
| `backtest_runs` | 保存一次回测任务的整体结果 |
| `backtest_trades` | 保存回测产生的交易明细 |
| `backtest_equity_points` | 保存回测权益曲线 |
| `audit_logs` | 保存系统初始化、关键操作和后续审计事件 |

## 4. 种子数据来源

| 来源 | 迁移到 |
|---|---|
| `template_module/templates/index.json` | `strategy_templates` |
| `template_module/templates/*.json` | `strategy_templates.strategy_json` 与 `user_strategies` |
| `data_module/market_data.sqlite` | `market_instruments` 与 `market_bars` |
| `backtest_module/output/price_breakout_demo/report.json` | `backtest_runs`、`backtest_trades`、`backtest_equity_points` |

## 5. 本地运行方式

安装依赖：

```powershell
cd web_app/backend
python -m pip install -e .[dev]
```

初始化数据库：

```powershell
python -m app.db.init_db
```

或通过 API 初始化：

```text
POST http://localhost:8000/api/v1/database/init
```

查看数据库状态：

```text
GET http://localhost:8000/api/v1/database/status
```

## 6. 验收标准

- 后端可以自动创建数据库表。
- 初始化接口可以重复运行，不产生重复行情 K 线。
- 模板、行情样例和回测样例可以迁移到数据库。
- 测试通过，结构检查通过。
- 数据库文件不提交到 GitHub，只提交模型、服务、脚本和文档。

## 7. 下一阶段建议

阶段 4 可以开始做用户账户与策略持久化：注册/登录、用户策略保存、策略版本管理，以及前端调用数据库 API 展示真实数据。
