FROM python:3.12-slim

# 安装 uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# 先复制依赖定义，利用 Docker 缓存层
COPY pyproject.toml uv.lock ./

# 安装依赖（不安装项目本身，仅依赖）
RUN uv sync --frozen --no-install-project --no-dev

# 复制项目代码
COPY . .

# 安装项目
RUN uv sync --frozen --no-dev

# 非 root 用户（可选，但推荐）
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]