from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END

from app.core.config import settings
from app.modules.chef.state import ChefState
from app.modules.rag.retriever import retrieve_parents

llm = ChatOpenAI(
    model=settings.MODEL_NAME,
    api_key=settings.OPENAI_API_KEY,
    base_url=settings.OPENAI_BASE_URL,
    temperature=0.7,
)


# ---------- 路由节点 ----------
ROUTER_PROMPT = """你是一个意图分类器。根据用户消息判断意图，只输出以下两个词之一，不要输出任何其他内容：
- recipe：用户在询问菜谱、烹饪方法、食材搭配、怎么做某道菜
- chitchat：其他所有情况（打招呼、闲聊、问与烹饪无关的问题）"""


async def route_node(state: ChefState) -> dict:
    last_user_msg = state["messages"][-1]
    response = await llm.ainvoke([
        SystemMessage(content=ROUTER_PROMPT),
        HumanMessage(content=last_user_msg.content),
    ])
    raw = response.content.strip().lower()
    intent = "recipe" if "recipe" in raw else "chitchat"
    return {"intent": intent}


def route_decision(state: ChefState) -> str:
    return state["intent"]


# ---------- 食谱生成节点（接入 RAG）----------
RECIPE_RAG_PROMPT = """你是「厨思」的专业河南菜烹饪助手。

下面是从菜谱知识库中检索到的参考资料（每道菜是完整原文）。请优先依据这些资料回答用户问题：
- 如果资料中有与用户问题相关的菜谱，严格按资料内容组织回答，不要编造资料中没有的原料或步骤。
- 如果资料不足以回答，如实说明「知识库中暂无这道菜的完整记录」，再给出通用的烹饪建议，并明确标注「以下为通用建议」。
- 回答格式：菜名 → 简介 → 原料（主料/配料/调料）→ 制法（分步骤）。

参考资料：
{context}
"""


async def recipe_node(state: ChefState) -> dict:
    query = state["messages"][-1].content
    db = state["db"]

    # 1. 检索父块（raw_markdown 完整菜谱）
    parents = await retrieve_parents(db, query, top_k=3)

    # 2. 拼 context
    if parents:
        context = "\n\n---\n\n".join(
            f"【{p['name']}】\n{p['raw_markdown']}" for p in parents
        )
    else:
        context = "（知识库中未检索到相关菜谱）"

    sources = [
        {"recipe_id": p["recipe_id"], "name": p["name"], "score": round(p["score"], 4)}
        for p in parents
    ]

    # 3. 生成
    prompt = RECIPE_RAG_PROMPT.format(context=context)
    response = await llm.ainvoke([
        SystemMessage(content=prompt),
        HumanMessage(content=query),
    ])
    return {"messages": [response], "sources": sources}


# ---------- 闲聊节点 ----------
CHITCHAT_PROMPT = """你是「厨思」的智能厨师助手，性格亲切、简短。可以回应问候、闲聊，
但不要编造菜谱。如果用户的话题可以引导到烹饪或河南菜，自然地带一句即可，不要强行推销。"""


async def chitchat_node(state: ChefState) -> dict:
    response = await llm.ainvoke([
        SystemMessage(content=CHITCHAT_PROMPT),
        *state["messages"],
    ])
    return {"messages": [response], "sources": []}


# ---------- 构图 ----------
def build_chef_graph():
    builder = StateGraph(ChefState)

    builder.add_node("router", route_node)
    builder.add_node("recipe", recipe_node)
    builder.add_node("chitchat", chitchat_node)

    builder.add_edge(START, "router")
    builder.add_conditional_edges(
        "router",
        route_decision,
        {"recipe": "recipe", "chitchat": "chitchat"},
    )
    builder.add_edge("recipe", END)
    builder.add_edge("chitchat", END)

    return builder.compile()


chef_graph = build_chef_graph()