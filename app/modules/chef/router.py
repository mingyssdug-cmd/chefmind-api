import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.chef.history import get_history
from app.modules.chef.schemas import ChatRequest, HistoryResponse
from app.modules.user.deps import get_current_user
from app.modules.user.models import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chef", tags=["chef"])


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/chat/stream", summary="AI 智能厨师对话（SSE 流式，按用户隔离记忆）")
async def chat_stream(
    req: ChatRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    chef_graph = request.app.state.chef_graph
    thread_id = current_user.thread_id

    async def event_generator():
        final_state: dict | None = None
        try:
            async for event in chef_graph.astream_events(
                {
                    "messages": [{"role": "user", "content": req.message}],
                    "sources": [],
                },
                config={
                    "configurable": {
                        "thread_id": thread_id,
                        "db": db,
                    }
                },
                version="v2",
            ):
                kind = event["event"]
                node = event.get("metadata", {}).get("langgraph_node")

                if kind == "on_chat_model_stream" and node in ("recipe", "chitchat"):
                    content = event["data"]["chunk"].content
                    if content:
                        yield _sse("token", {"content": content})

                elif kind == "on_chain_end" and event.get("name") == "LangGraph":
                    final_state = event["data"].get("output")

            # 发送 meta 事件
            if final_state:
                yield _sse("meta", {
                    "intent": final_state.get("intent", "unknown"),
                    "sources": final_state.get("sources", []),
                })

            # 【核心修复】动态提取最后一条消息的内容放入 done 事件
            done_data = {}
            if final_state:
                messages = final_state.get("messages") or []
                if messages:
                    last_msg = messages[-1]
                    # 兼容 LangChain Message 对象和 dict
                    content = getattr(last_msg, "content", None)
                    if content is None and isinstance(last_msg, dict):
                        content = last_msg.get("content")
                    if content:
                        done_data["content"] = content

            yield _sse("done", done_data)

        except Exception as e:
            logger.exception("chef chat stream failed, thread_id=%s", thread_id)
            yield _sse("error", {"detail": f"智能体调用失败: {str(e)}"})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get(
    "/chat/history",
    response_model=HistoryResponse,
    summary="查询当前用户的对话历史",
)
async def chat_history(
    request: Request,
    current_user: User = Depends(get_current_user),
    before: str | None = Query(None, description="游标：上一页最后一条的 checkpoint_id"),
    limit: int = Query(20, ge=1, le=50, description="每页条数"),
):
    checkpointer = request.app.state.checkpointer
    if checkpointer is None:
        raise HTTPException(status_code=500, detail="checkpointer 未初始化")

    return await get_history(
        checkpointer,
        current_user.thread_id,
        before=before,
        limit=limit,
    )


@router.delete(
    "/chat/history",
    response_model=dict,
    summary="清空当前用户的对话记忆",
)
async def delete_chat_history(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    checkpointer = request.app.state.checkpointer
    if checkpointer is None:
        raise HTTPException(status_code=500, detail="checkpointer 未初始化")

    try:
        await checkpointer.adelete_thread(current_user.thread_id)
    except Exception as e:
        logger.exception("delete thread failed, thread_id=%s", current_user.thread_id)
        raise HTTPException(status_code=500, detail=f"删除会话失败: {str(e)}")

    return {
        "thread_id": current_user.thread_id,
        "deleted": True,
    }