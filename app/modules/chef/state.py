from typing import Annotated, Literal

from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class ChefState(TypedDict):
    """
    只允许放可 msgpack 序列化的纯数据。
    db / llm / pool 等运行时对象一律走 config["configurable"]，不进 state。
    """
    messages: Annotated[list, add_messages]
    intent: Literal["recipe", "chitchat"]
    sources: list[dict]