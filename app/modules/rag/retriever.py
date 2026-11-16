from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.embedding import embed_text
from app.modules.rag.models import RecipeEmbedding
from app.modules.recipe.models import Recipe


async def retrieve_parents(
    db: AsyncSession,
    query: str,
    top_k: int = 5,
) -> list[dict]:
    """
    检索流程：
    1. query 向量化
    2. pgvector 相似度搜索子块，取 top_k 个
    3. 按 recipe_id 去重
    4. 回 recipe 表拿 raw_markdown（父块）
    返回：[{"recipe_id", "name", "raw_markdown", "score"}]
    """
    query_vec = embed_text(query)

    stmt = (
        select(
            RecipeEmbedding.recipe_id,
            RecipeEmbedding.embedding.cosine_distance(query_vec).label("distance"),
        )
        .order_by(RecipeEmbedding.embedding.cosine_distance(query_vec))
        .limit(top_k * 3)  # 多取一些用于去重
    )
    rows = (await db.execute(stmt)).all()

    # 去重，保留每个 recipe 的最佳分数
    seen: dict = {}
    for recipe_id, distance in rows:
        if recipe_id not in seen or distance < seen[recipe_id]:
            seen[recipe_id] = distance

    # 取前 top_k 个 recipe_id
    ranked = sorted(seen.items(), key=lambda x: x[1])[:top_k]
    recipe_ids = [rid for rid, _ in ranked]

    if not recipe_ids:
        return []

    # 回表拿父块
    recipe_stmt = select(Recipe).where(Recipe.id.in_(recipe_ids))
    recipes = {r.id: r for r in (await db.execute(recipe_stmt)).scalars().all()}

    results = []
    for rid, score in ranked:
        recipe = recipes.get(rid)
        if recipe:
            results.append({
                "recipe_id": str(rid),
                "name": recipe.name,
                "raw_markdown": recipe.raw_markdown,
                "score": 1 - score,  # cosine distance 转相似度
            })
    return results