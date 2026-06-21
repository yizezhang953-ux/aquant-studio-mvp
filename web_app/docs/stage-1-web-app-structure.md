# 阶段 1 交付物：Web App 工程结构

版本：V2.1 Stage 1  
日期：2026-06-21  
状态：已建立工程骨架，尚未迁移完整业务 API。

## 1. 阶段目标

本阶段目标是把原来的静态 MVP 项目升级为真正在线应用的工程结构。

已完成：

- 新增 `web_app/` 工程目录。
- 建立 `backend/` FastAPI 后端骨架。
- 建立 `frontend/` React + Vite 前端骨架。
- 建立配置、API、schemas、services、tasks、tests 目录。
- 保留对旧 MVP 模块的迁移引用。
- 增加结构检查脚本。

## 2. 当前目录

```text
web_app/
  backend/
    app/
      api/v1/routes/
      core/
      models/
      schemas/
      services/
      tasks/
      main.py
    tests/
    pyproject.toml
    .env.example
  frontend/
    src/
    public/
    package.json
    tsconfig.json
  docs/
  scripts/
```

## 3. 后端入口

后端入口：

```text
web_app/backend/app/main.py
```

已定义接口：

```text
GET /
GET /health
GET /api/v1/system
GET /api/v1/security/status
```

## 4. 前端入口

前端入口：

```text
web_app/frontend/src/App.tsx
```

当前是在线应用 shell，展示未来模块：

- Templates
- Strategy Editor
- Backtests
- Optimization
- Paper Trading
- Security

## 5. 启动方式

后端安装依赖后运行：

```powershell
cd web_app/backend
python -m uvicorn app.main:app --reload --port 8000
```

前端安装依赖后运行：

```powershell
cd web_app/frontend
npm install
npm run dev
```

## 6. 下一阶段

阶段 2 建议实现后端 API MVP：

- `GET /api/v1/templates`
- `POST /api/v1/strategies/validate`
- `POST /api/v1/backtests`
- `GET /api/v1/backtests/{id}`
- `GET /api/v1/security/status`

业务逻辑先复用当前已有模块，之后再逐步迁移到数据库和后台任务。
