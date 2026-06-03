# 嵌入式Linux系统构建与配置平台

设备管理模块 - 支持设备CRUD、心跳模拟、在线/离线状态监控。

## 架构

```
├── backend/          # FastAPI后端
│   ├── app/
│   │   ├── main.py       # 应用入口 + lifespan
│   │   ├── config.py     # 配置（环境变量）
│   │   ├── database.py   # SQLAlchemy引擎 + Session
│   │   ├── models.py     # Device ORM模型
│   │   ├── schemas.py    # Pydantic请求/响应模型
│   │   ├── crud.py       # 数据库操作层
│   │   ├── routes.py     # API路由
│   │   └── scheduler.py  # APScheduler心跳定时任务
│   ├── tests/
│   │   └── test_devices.py  # 16个测试用例
│   └── sql/init.sql      # MySQL建表DDL
├── frontend/         # React前端 (Vite)
│   └── src/
│       ├── App.jsx              # 主页面（设备列表+筛选）
│       ├── DeviceTable.jsx      # 设备表格组件
│       ├── CreateDeviceModal.jsx # 创建设备弹窗
│       └── api.js               # axios API封装
└── docker-compose.yml  # 一键部署（MySQL+后端+前端）
```

## 核心功能

| 功能 | 说明 |
|------|------|
| 设备CRUD | 创建/查询/更新/删除，字段：设备ID、型号、内核版本、在线状态 |
| 心跳模拟 | APScheduler每30秒执行，70%概率更新心跳，30%概率不发送 |
| 离线判定 | 超过60秒未收到心跳自动标记为离线 |
| ID唯一性 | MySQL UNIQUE约束 + IntegrityError捕获，并发安全 |
| 状态筛选 | 前端支持筛选全部/在线/离线，5秒自动刷新 |

## 快速启动

### Docker方式（推荐）
```bash
docker-compose up -d
```
- 前端: http://localhost:3000
- 后端API: http://localhost:8000/docs

### 本地开发

**后端：**
```bash
cd backend
pip install -r requirements.txt
# 配置 .env（参考 .env.example）
uvicorn app.main:app --reload --port 8000
```

**前端：**
```bash
cd frontend
npm install
npm run dev
```

## 运行测试
```bash
cd backend
python -m pytest tests/ -v
```

## API接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/devices/ | 创建设备（409=ID重复） |
| GET | /api/devices/?is_online=true | 获取设备列表（可筛选） |
| GET | /api/devices/{device_id} | 获取单个设备 |
| PUT | /api/devices/{device_id} | 更新设备信息 |
| DELETE | /api/devices/{device_id} | 删除设备 |
| POST | /api/devices/{device_id}/heartbeat | 发送心跳 |

## 并发处理

设备ID唯一性通过两层保障：
1. **数据库层**：MySQL `UNIQUE` 约束（`device_id`列）
2. **应用层**：捕获 `IntegrityError` 转换为 `DuplicateDeviceError`，返回HTTP 409

即使多个请求同时创建相同device_id，数据库约束确保只有一个成功。
