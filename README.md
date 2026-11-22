# 厨思 ChefMind

> 智能菜谱与 AI 烹饪助手后端 —— 基于 FastAPI + PostgreSQL(pgvector) + LangGraph 的多智能体应用

厨思（ChefMind）是一个面向菜谱学习与智能烹饪场景的后端服务。用户可浏览、搜索各省菜谱，并通过 AI 智能厨师以对话方式获取菜谱、选食材、生成做法。AI 助手基于 LangGraph 构建，包含意图路由、RAG 食谱生成、闲聊与安全过滤节点，并支持按用户隔离的短期记忆。

---

## 功能特性

- **菜谱管理**：省份 / 菜系 / 菜谱三级结构，支持分页、按省份与菜系过滤、菜名模糊搜索、菜谱详情。
- **AI 智能厨师**：
  - SSE 流式对话，逐 token 输出。
  - 意图路由：食谱生成（RAG 增强） / 闲聊 / 安全拦截。
  - 基于 pgvector 的父子块向量检索，命中后回取完整菜谱原文，降低幻觉。
  - 短期记忆：按登录用户的 `thread_id` 隔离，状态持久化于 PostgreSQL。
  - 历史查询（游标分页）与一键清空会话。
- **认证体系**：账号密码注册 / 登录、JWT（access + refresh）、微信小程序静默登录与手机号绑定。
- **工程化**：SQLAlchemy 2.0 异步、Alembic 友好、Docker Compose 一键部署、Swagger 文档。

---

## 技术栈

| 层 | 技术 |
| --- | --- |
| Web 框架 | FastAPI、Uvicorn |
| 数据库 | PostgreSQL 16 + pgvector |
| ORM | SQLAlchemy 2.0（asyncpg） |
| 智能体 | LangGraph、LangChain、langgraph-checkpoint-postgres |
| 模型 | OpenAI 兼容聊天模型、text-embedding-v4（向量） |
| 认证 | PyJWT、argon2-cffi、OAuth2 Password Flow |
| 依赖管理 | uv |
| 部署 | Docker、Docker Compose |

---

## 目录结构

```text
chefmind-api/
├── app/
│   ├── main.py                 # FastAPI 入口，lifespan 管理 DB 与 checkpointer
│   ├── core/                   # 配置、数据库、checkpointer、embedding
│   ├── api/v1.py               # 路由聚合（/api/v1）
│   └── modules/
│       ├── recipe/             # 菜谱模块
│       ├── rag/                # 向量检索模块
│       ├── chef/               # AI 厨师模块（LangGraph 图、历史、路由）
│       └── user/               # 认证与用户模块
├── scripts/                    # 数据落库、向量化、记忆测试脚本
├── data/raw/                   # 菜谱 Markdown 源文件（按城市分目录）
├── docker/init.sql             # 启用 pgvector 扩展
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── .env.example
└── README.md
```

---

## 快速开始（本地开发）

### 1. 环境要求

- Python 3.12+
- PostgreSQL 16（需启用 pgvector 扩展）
- uv

### 2. 安装依赖

```bash
uv sync
```

### 3. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`，至少填写：

- `POSTGRES_*`：数据库连接
- `OPENAI_API_KEY` / `OPENAI_BASE_URL` / `MODEL_NAME`：聊天模型
- `DASHSCOPE_API_KEY`：向量模型
- `JWT_SECRET_KEY`：生产环境必须替换为强随机值

生成强随机 JWT 密钥：

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

### 4. 启用 pgvector 并启动

```bash
psql "$DATABASE_URL" -c "CREATE EXTENSION IF NOT EXISTS vector;"
uv run uvicorn app.main:app --reload --port 8000
```

访问 `http://localhost:8000/docs` 查看 Swagger。

---

## Docker 一键部署

```bash
# 1. 配置环境变量
cp .env.example .env
# 编辑 .env：JWT_SECRET_KEY、OPENAI_API_KEY、DASHSCOPE_API_KEY（如需微信登录填 WECHAT_*）

# 2. 构建并启动
docker compose up -d --build

# 3. 验证
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/provinces
```

**首次启动自动完成**：

1. `db` 容器初始化数据库并启用 pgvector 扩展。
2. `api` 容器启动时建业务表与 LangGraph checkpoint 表。

**常用命令**：

```bash
docker compose logs -f api        # 查看 API 日志
docker compose down               # 停止（保留数据）
docker compose down -v            # 停止并清空数据卷（慎用）
docker compose exec api python -c "from app.core.config import settings; print(settings.MODEL_NAME)"
```

> 数据持久化在 `pgdata` 卷。修改 `docker/init.sql` 后需 `docker compose down -v` 才会重新执行。

---

## 数据落库与向量化

菜谱源文件放在 `data/raw/<城市>/<文件>.md`，结构为：H1 主标题 → H2 菜系 → H3 菜名 → `**原料**` / `**制法**`。

```bash
# 解析 Markdown 并写入 PostgreSQL
uv run python -m scripts.seed_data

# 切分父子块并写入 pgvector
uv run python -m scripts.embed_recipes

# 记忆功能测试
uv run python -m scripts.test_memory
```

---

## API 概览

| 模块 | 方法 | 路径 | 登录 |
| --- | --- | --- | --- |
| 菜谱 | GET | `/api/v1/provinces` | 否 |
| 菜谱 | GET | `/api/v1/categories` | 否 |
| 菜谱 | GET | `/api/v1/recipes` | 否 |
| 菜谱 | GET | `/api/v1/recipes/{id}` | 否 |
| AI 厨师 | POST | `/api/v1/chef/chat/stream` | 是 |
| AI 厨师 | GET | `/api/v1/chef/chat/history` | 是 |
| AI 厨师 | DELETE | `/api/v1/chef/chat/history` | 是 |
| 认证 | POST | `/api/v1/auth/register` | 否 |
| 认证 | POST | `/api/v1/auth/login` | 否 |
| 认证 | POST | `/api/v1/auth/refresh` | 否 |
| 认证 | POST | `/api/v1/auth/wechat/login` | 否 |
| 认证 | POST | `/api/v1/auth/wechat/bind-phone` | 可选 |
| 认证 | GET | `/api/v1/auth/me` | 是 |
| 认证 | POST | `/api/v1/auth/logout` | 是 |
| 系统 | GET | `/health` | 否 |

完整字段与错误码见项目内 API 接口文档（v1.6）。

---

## 安全说明

- `.env` 不进入版本库；仓库仅提供 `.env.example`。
- `JWT_SECRET_KEY` 生产环境必须替换，禁止使用默认值。
- 微信登录依赖 `WECHAT_APPID` / `WECHAT_SECRET`，未配置时仅账号密码体系可用。
- AI 对话接口对输入做长度截断与安全过滤。

---

## License

内部项目，未授权请勿外传。
