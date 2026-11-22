from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.core.config import settings


async def create_checkpointer() -> tuple[AsyncPostgresSaver, AsyncConnectionPool]:
    """
    创建 Checkpointer 及其连接池。
    返回 (checkpointer, pool)，pool 由 lifespan 结束时关闭。
    """
    pool = AsyncConnectionPool(
        conninfo=settings.CHECKPOINT_DB_URL,
        min_size=1,
        max_size=8,
        open=False,
        kwargs={
            "autocommit": True,
            "prepare_threshold": 0,
            "row_factory": dict_row,
        },
    )
    await pool.open()
    await pool.wait()

    checkpointer = AsyncPostgresSaver(pool)
    await checkpointer.setup()  # 幂等，首次建 checkpoint 表

    return checkpointer, pool