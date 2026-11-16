from typing import Annotated, Literal

from langgraph.graph.message import add_messages
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import TypedDict


class ChefState(TypedDict):
    messages: Annotated[list, add_messages]
    intent: Literal["recipe", "chitchat"]
    db: AsyncSession          # 新增：由 router 注入，供 recipe_node 检索用
    sources: list[dict]       # 新增：检索到的父块来源，方便前端展示引用