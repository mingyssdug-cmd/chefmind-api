from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    thread_id: str | None = None   # 预留，后期接记忆时用


class SourceItem(BaseModel):
    recipe_id: str
    name: str
    score: float


class ChatResponse(BaseModel):
    reply: str
    intent: str
    sources: list[SourceItem] = []