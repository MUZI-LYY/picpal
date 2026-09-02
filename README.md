<p align="center">
  <img src="frontend/public/brand/picpal-logo.png" alt="PicPal Logo" width="220" />
</p>

<h1 align="center">北京 AI 旅行规划与出片点推荐</h1>

<p align="center">
  把旅行偏好、逐日路线、交通衔接和拍摄位置，整理进同一份可执行行程。
</p>

<p align="center"><strong>当前版本：北京 1–5 日 · 邀请码内测</strong></p>

## 产品介绍

PicPal 是面向北京自由行场景的对话式 AI 旅行规划助手。用户只需说出旅行天数、日期、同行人、出行节奏和拍摄偏好，系统会通过多轮对话补齐缺少的条件，生成按天、按时间排列的旅行路线。

它不只回答“去哪些景点”，还会把每一站的停留时间、交通衔接、预约提醒、住宿区域，以及经过准入校验的出片位置放进同一份行程。日期还没确定时，也可以先从旅行想法开始规划。

公开仓库保留 24 条北京机位的位置结构与文字说明，不包含采集图片、原始来源链接或作者信息。获得明确授权后，可以通过同源静态资源为机位补充参考图片。

## 核心能力

| 能力 | 当前实现 |
| --- | --- |
| 对话式需求理解 | 从自然语言中识别天数、日期、同行人、节奏、兴趣、必去或避开景点、交通和拍摄偏好，并只追问缺少的关键条件 |
| 可执行的逐日路线 | 按天和时间组织景点，给出停留时长、下一站交通衔接、开放时间及预约提醒 |
| 住宿区域建议 | 根据行程分布推荐适合落脚的区域，不虚构具体酒店或实时价格 |
| 出片点推荐 | 展示具体位置与文字机位说明；仅在存在已授权素材时展示参考图片 |
| 确定性校验 | 对数据 Schema、闭馆日、开放时间、时间冲突、路线和机位数据进行规则校验 |
| 可选外部能力 | 可接入 DeepSeek 和高德地图；缺少 Key 时使用规则或 Mock 回退，便于本地开发 |

## 用户流程

```text
输入邀请码
    ↓
描述旅行想法
    ↓
补齐天数、日期与节奏等关键条件
    ↓
生成并校验逐日路线
    ↓
查看交通、预约、住宿区域与出片点
    ↓
继续补充需求，生成新的行程版本
```

生成期间会展示六个运行阶段：理解旅行需求、确认景点位置、规划每日路线、评估住宿区域、检索出片机位、校验完整行程。

## 能力边界

- MVP 版本仅支持北京 1 至 5 日行程。
- 当前不应对外描述为全国旅行规划产品。
- 出片点检索采用 JSON 内存库、结构化过滤、关键词打分和规则重排；当前尚未接入 Embedding 或向量数据库。
- 未配置高德地图 Key 时，交通信息使用规则和距离估算，不等同于实时导航、实时路况或实时票价。
- 未配置模型 Key 时会进入规则或 Mock 回退，输出适合开发验收，不代表真实模型效果。
- 当前使用匿名 Cookie 会话和邀请码，不包含正式账号、多人协同编辑、分享或导出能力。
- 当前存储仅支持 SQLite，规划任务由进程内线程执行；仓库暂未提供 Docker、CI 和完整生产部署方案。
- OpenAPI 契约与部分新接口仍在同步中；修改 API 前应先核对实际路由，并同步更新契约和前端生成类型。

## 技术架构

```text
Next.js Web
    │
    ▼
FastAPI API
    │
    ├── Conversation / Message / Run / PlanVersion
    ├── 需求理解与多轮补齐
    ├── 行程规划、出片点检索与规则校验
    │
    ├── SQLite                  会话、消息、运行和行程版本
    ├── JSON                    景点与出片点公开示例资料
    ├── DeepSeek（可选）        需求理解与内容生成
    └── 高德地图（可选）        地点解析与路线信息
```

| 层级 | 技术 |
| --- | --- |
| 前端 | Next.js 16、React 19、TypeScript、Tailwind CSS 4、Lucide |
| 后端 | Python 3.11、FastAPI、Pydantic、SQLAlchemy、Alembic |
| 存储 | SQLite、JSON；可选同源授权图片 |
| 测试 | Pytest、Vitest、Testing Library、Playwright |
| 契约 | OpenAPI 3.1、`openapi-typescript` |

## 项目结构

```text
backend/
├── app/
│   ├── api/                    # FastAPI 路由
│   ├── data/                   # 出片点公开示例数据
│   ├── db/                     # SQLAlchemy 模型与仓储
│   ├── services/               # 对话、规划、检索、地图与校验能力
│   └── static/                 # 静态验收界面与可选授权素材
├── contracts/                  # OpenAPI、Schema 与 Fixture
├── alembic/                    # 数据库迁移
├── scripts/                    # Schema 生成脚本
└── tests/                      # 后端测试

frontend/
├── public/brand/               # PicPal 品牌素材
├── src/app/                    # Next.js App Router 页面
├── src/components/             # 官网、工作台、对话与行程组件
├── src/lib/                    # API Client 与前端工具
├── src/types/                  # OpenAPI 生成类型
└── e2e/                        # Playwright 场景

data/                           # 本地运行时数据目录
```

## 本地启动

### 运行要求

- Python 3.11
- Node.js 24 或更高版本
- npm

### 1. 准备环境变量

在项目根目录执行：

```bash
cp .env.example .env
openssl rand -hex 32
```

把生成结果填入 `.env`，本地开发至少需要确认以下配置：

```env
ENV=dev
SESSION_SIGNING_SECRET=<至少 32 字节的随机值>
SESSION_COOKIE_SECURE=false
INVITE_CODES=replace-with-your-local-code
```

`LLM_API_KEY` 和 `MAP_API_KEY` 可以暂时留空，系统会使用开发回退逻辑。不要把真实 Key 或邀请码提交到 Git。

### 2. 启动后端

打开一个终端：

```bash
cd backend
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/alembic upgrade head
.venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

后端健康检查：<http://127.0.0.1:8000/api/v1/health>

### 3. 启动前端

再打开一个终端：

```bash
cd frontend
npm ci
npm run dev
```

打开 <http://localhost:3000/>，点击“定制专属行程”进入 `/plan`，再输入 `.env` 中配置的邀请码。

本地前端默认将 `/api/*` 代理到 `http://127.0.0.1:8000`。如果后端地址不同，请在启动前端的进程环境中设置 `API_BACKEND_URL`，或写入 `frontend/.env.local`。

OpenAPI 契约发生变化后，再重新生成前端类型：

```bash
cd frontend
npm run generate:api
```

## 环境变量

| 变量 | 是否必需 | 说明 |
| --- | --- | --- |
| `ENV` | 否 | `dev` 或 `prod`；默认 `dev` |
| `DATABASE_URL` | 否 | SQLite 连接串；当前阶段不支持其他数据库 |
| `SESSION_SIGNING_SECRET` | 是 | 匿名会话签名密钥，生产环境必须使用至少 32 字节的随机值 |
| `SESSION_COOKIE_SECURE` | 是 | 本地纯 HTTP 设为 `false`，HTTPS 生产环境设为 `true` |
| `INVITE_CODES` | 是 | 内测邀请码，多个邀请码以逗号分隔 |
| `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` | 否 | DeepSeek 模型配置；未配置 Key 时使用回退逻辑 |
| `MAP_API_KEY` / `MAP_PROVIDER` | 否 | 高德地图配置；未配置 Key 时使用估算数据 |
| `API_BACKEND_URL` | 否 | Next.js 反代目标；应配置在前端进程或 `frontend/.env.local` |
| `VISION_API_KEY` / `VISION_BASE_URL` / `VISION_MODEL` | 否 | 仅用于离线图片准入流程，不是产品运行的必需配置 |

## 测试与质量检查

后端：

```bash
cd backend
.venv/bin/python -m pytest -q
```

前端：

```bash
cd frontend
npm run lint
npm run typecheck
npm test -- --run
npm run build
npm run test:e2e
```

Playwright 会在 `http://localhost:3100` 启动或复用测试前端。涉及真实后端数据的人工验收前，请先确认后端已运行。

## 当前 API

```text
Conversation → Message → Run → PlanVersion
```

- `POST /api/v1/invites/verify`：校验内测邀请码
- `POST /api/v1/conversations`：创建对话
- `GET /api/v1/conversations`：读取当前匿名会话的历史对话
- `GET /api/v1/conversations/{conversation_id}`：读取对话快照
- `POST /api/v1/conversations/{conversation_id}/messages`：发送需求或补充条件
- `GET /api/v1/runs/{run_id}`：轮询六阶段运行状态
- `GET /api/v1/plans/{plan_id}`：读取不可变行程版本
- `GET /api/v1/photo-spots/featured`：读取首页出片灵感
- `GET /api/v1/photo-assets/{filename}`：存在已授权的本地图片目录时读取同源图片资源
- `GET /api/v1/health`：健康检查

## 团队协作约定

- 从最新主分支创建功能分支，避免直接覆盖其他成员的工作。
- 修改 OpenAPI 契约后，运行 `npm run generate:api`，并同时提交契约与生成类型。
- 更新出片点数据或图片后重启后端，并重新生成行程；已有 `PlanVersion` 是不可变快照，不会自动补入新图片。
- 提交代码前运行与改动相关的测试；修改关键用户路径时同时检查桌面端和移动端。
- `.env`、API Key、邀请码、云资源 ID、内部地址和未经批准的采集原始数据不得提交到仓库。
- 采集图片和来源信息只有在确认公开授权与使用范围后才能加入公开仓库。
