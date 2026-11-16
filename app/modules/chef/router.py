import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.chef.graph import chef_graph
from app.modules.chef.schemas import ChatRequest

router = APIRouter(prefix="/chef", tags=["chef"])


def _sse(event: str, data: dict) -> str:
    """构造一条 SSE 消息"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/chat/stream", summary="AI 智能厨师对话（SSE 流式）")
async def chat_stream(req: ChatRequest, db: AsyncSession = Depends(get_db)):
    async def event_generator():
        try:
            # stream_mode="messages"：只流 LLM 输出的 token
            # 同时用 metadata 判断是哪个节点产生的 token（route_node 也会调 LLM，要过滤）
            async for chunk, metadata in chef_graph.astream(
                {
                    "messages": [{"role": "user", "content": req.message}],
                    "db": db,
                    "sources": [],
                },
                stream_mode="messages",
            ):
                node = metadata.get("langgraph_node")
                # 只推 recipe / chitchat 节点的 token，路由节点的分类结果不推
                if node not in ("recipe", "chitchat"):
                    continue

                content = getattr(chunk, "content", "")
                if content:
                    yield _sse("token", {"content": content})

            # 流结束后，从最终 state 拿 intent 和 sources
            # 注意：astream 不返回最终 state，这里再查一次 graph 状态不可行，
            # 所以改为在流开始前先跑路由？—— 见下方说明，用 astream_events 更合适。
            yield _sse("done", {})

        except Exception as e:
            yield _sse("error", {"detail": f"智能体调用失败: {str(e)}"})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # 关闭 nginx 缓冲
            "Connection": "keep-alive",
        },
    )