from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.modules.chef.schemas import HistoryItem, HistoryMessage, HistoryResponse, DeleteHistoryResponse


async def get_history(
    checkpointer: AsyncPostgresSaver,
    thread_id: str,
    before: str | None = None,
    limit: int = 20,
) -> HistoryResponse:
    """
    只取最新一个 checkpoint，返回该快照中的全部 messages。
    """
    config = {"configurable": {"thread_id": thread_id}}

    tup = await checkpointer.aget_tuple(config)
    if tup is None:
        return HistoryResponse(items=[], has_more=False, next_before=None)

    checkpoint = tup.checkpoint or {}
    channel_values = checkpoint.get("channel_values") or {}
    raw_messages = channel_values.get("messages") or []

    msgs = []
    for msg in raw_messages:
        if isinstance(msg, HumanMessage):
            msgs.append(HistoryMessage(role="user", content=msg.content))
        elif isinstance(msg, AIMessage):
            msgs.append(HistoryMessage(role="assistant", content=msg.content))

    if not msgs:
        return HistoryResponse(items=[], has_more=False, next_before=None)

    return HistoryResponse(
        items=[
            HistoryItem(
                checkpoint_id=tup.config["configurable"].get("checkpoint_id", ""),
                ts=checkpoint.get("ts", ""),
                messages=msgs,
            )
        ],
        has_more=False,
        next_before=None,
    )


async def delete_history(
    checkpointer: AsyncPostgresSaver,
    thread_id: str,
) -> DeleteHistoryResponse:
    """
    删除指定 thread 的所有 checkpoint 记录。
    三张表按 thread_id 清理：checkpoints / checkpoint_blobs / checkpoint_writes。
    """
    deleted = 0
    async with checkpointer.pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT COUNT(*) FROM checkpoints WHERE thread_id = %s",
                (thread_id,),
            )
            row = await cur.fetchone()
            deleted = row[0] if row else 0

            await cur.execute(
                "DELETE FROM checkpoint_writes WHERE thread_id = %s",
                (thread_id,),
            )
            await cur.execute(
                "DELETE FROM checkpoint_blobs WHERE thread_id = %s",
                (thread_id,),
            )
            await cur.execute(
                "DELETE FROM checkpoints WHERE thread_id = %s",
                (thread_id,),
            )
        await conn.commit()

    return DeleteHistoryResponse(
        thread_id=thread_id,
        deleted_checkpoints=deleted,
        message=(
            f"已删除 {deleted} 条会话记录"
            if deleted > 0
            else "该会话不存在或已删除"
        ),
    )