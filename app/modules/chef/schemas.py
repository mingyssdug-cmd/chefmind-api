from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str


class SourceItem(BaseModel):
    recipe_id: str
    name: str
    score: float


class ChatResponse(BaseModel):
    reply: str
    intent: str
    sources: list[SourceItem] = []


class HistoryMessage(BaseModel):
    role: str
    content: str
    ts: str | None = None


class HistoryItem(BaseModel):
    checkpoint_id: str
    ts: str
    messages: list[HistoryMessage]


class HistoryResponse(BaseModel):
    items: list[HistoryItem]
    has_more: bool
    next_before: str | None


class DeleteHistoryResponse(BaseModel):
    thread_id: str
    deleted_checkpoints: int
    message: str