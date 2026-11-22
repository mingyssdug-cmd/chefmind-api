from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from app.api.v1 import api_router
from app.core.checkpointer import create_checkpointer
from app.core.database import init_db
from app.modules.chef.graph import build_chef_graph


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()

    checkpointer, pool = await create_checkpointer()
    app.state.chef_graph = build_chef_graph(checkpointer=checkpointer)
    app.state.checkpointer = checkpointer
    app.state.checkpoint_pool = pool

    yield

    await pool.close()


app = FastAPI(title="ChefMind API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],        # 开发阶段先用 *，上线改成具体域名
    allow_credentials=False,    # allow_origins=["*"] 时 credentials 必须 False
    allow_methods=["*"],        # 包含 OPTIONS
    allow_headers=["*"],
)
app.include_router(api_router)


@app.get("/health", tags=["meta"])
async def health():
    return {"status": "ok"}