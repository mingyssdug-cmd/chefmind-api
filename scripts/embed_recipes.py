"""
将菜谱表中的 raw_markdown 切分为父子块，子块向量化后写入 pgvector。
用法：
    python -m scripts.embed_recipes              # 处理所有尚未向量化的菜谱
    python -m scripts.embed_recipes --rebuild    # 清空重跑
"""

import asyncio
import re
import sys
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal, init_db
from app.core.embedding import embed_batch
from app.modules.recipe.models import Recipe
from app.modules.rag.models import RecipeEmbedding

# 子块切分器：菜谱段落通常不长，300 字足够覆盖一个语义单元
CHILD_SPLITTER = RecursiveCharacterTextSplitter(
    chunk_size=300,
    chunk_overlap=50,
    separators=["\n\n", "\n", "。", "，", " ", ""],
)

# 子块内的语义标记：优先按这些结构切
SECTION_MARKERS = ["**原料**", "**制法**"]


def split_recipe_to_children(raw_markdown: str, recipe_name: str) -> list[str]:
    """
    将一道菜的 raw_markdown 切分为子块列表。
    策略：
    1. 先按 **原料** / **制法** 切成大段
    2. 每段若超长，再用 RecursiveCharacterTextSplitter 细切
    """
    # 去掉 H3 标题行（菜名），它不属于正文
    text = raw_markdown.strip()
    text = re.sub(r"^###\s+.+\n?", "", text, count=1)

    # 按语义标记分段
    segments = []
    current = []
    for line in text.split("\n"):
        if any(marker in line for marker in SECTION_MARKERS) and current:
            segments.append("\n".join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        segments.append("\n".join(current))

    # 每段细切
    children = []
    for seg in segments:
        seg = seg.strip()
        if not seg:
            continue
        if len(seg) <= 300:
            children.append(seg)
        else:
            children.extend(CHILD_SPLITTER.split_text(seg))

    # 兜底：如果切分后为空，整篇作为一个子块
    if not children:
        children = [text[:500]]
    return children


async def embed_one_recipe(db: AsyncSession, recipe: Recipe) -> int:
    """处理单道菜：切分 → 向量化 → 写入。返回子块数量。"""
    children = split_recipe_to_children(recipe.raw_markdown, recipe.name)
    if not children:
        return 0

    vectors = embed_batch(children)

    for idx, (child_text, vec) in enumerate(zip(children, vectors)):
        db.add(RecipeEmbedding(
            recipe_id=recipe.id,
            child_index=idx,
            content=child_text,
            embedding=vec,
            metadata_={
                "recipe_name": recipe.name,
                "category_id": recipe.category_id,
            },
        ))
    return len(children)


async def main(rebuild: bool = False):
    await init_db()

    async with AsyncSessionLocal() as db:
        if rebuild:
            await db.execute(delete(RecipeEmbedding))
            await db.commit()
            print("[REBUILD] 已清空 recipe_embedding")

        # 找出尚未向量化的菜谱（没有子块的）
        subq = select(RecipeEmbedding.recipe_id).distinct()
        stmt = select(Recipe).where(Recipe.id.not_in(subq))
        recipes = list((await db.execute(stmt)).scalars().all())

        if not recipes:
            print("[DONE] 所有菜谱已向量化，无新增")
            return

        print(f"[START] 待处理菜谱: {len(recipes)} 道")
        total_children = 0
        for i, recipe in enumerate(recipes, 1):
            try:
                n = await embed_one_recipe(db, recipe)
                total_children += n
                if i % 20 == 0 or i == len(recipes):
                    await db.commit()
                    print(f"  进度 {i}/{len(recipes)}，累计子块 {total_children}")
            except Exception as e:
                print(f"  [ERROR] 菜谱「{recipe.name}」({recipe.id}): {e}")
                await db.rollback()
                continue

        await db.commit()
        print(f"[DONE] 共处理 {len(recipes)} 道菜，生成 {total_children} 个子块")


if __name__ == "__main__":
    rebuild = "--rebuild" in sys.argv
    asyncio.run(main(rebuild))