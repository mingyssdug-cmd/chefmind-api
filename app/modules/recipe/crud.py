import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.recipe.models import Recipe, RecipeCategory


async def list_categories(
    db: AsyncSession, province: str | None = None
) -> list[RecipeCategory]:
    stmt = select(RecipeCategory).order_by(RecipeCategory.province, RecipeCategory.id)
    if province:
        stmt = stmt.where(RecipeCategory.province == province)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def list_provinces(db: AsyncSession) -> list[str]:
    """返回所有省份（去重、排序），用于前端下拉框"""
    stmt = select(RecipeCategory.province).distinct().order_by(RecipeCategory.province)
    result = await db.execute(stmt)
    return [row[0] for row in result.all()]


async def list_recipes(
    db: AsyncSession,
    province: str | None = None,
    category_id: int | None = None,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[int, list[dict]]:
    base = select(Recipe, RecipeCategory).join(
        RecipeCategory, Recipe.category_id == RecipeCategory.id
    )

    if province:
        base = base.where(RecipeCategory.province == province)
    if category_id is not None:
        base = base.where(Recipe.category_id == category_id)
    if keyword:
        base = base.where(Recipe.name.ilike(f"%{keyword}%"))

    count_stmt = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        base.order_by(Recipe.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(stmt)).all()

    items = [
        {
            "id": recipe.id,
            "name": recipe.name,
            "category_name": category.name,
            "province": category.province,
            "image_url": recipe.image_url,
            "description": recipe.description,
        }
        for recipe, category in rows
    ]
    return total, items


async def get_recipe(db: AsyncSession, recipe_id: uuid.UUID) -> dict | None:
    stmt = (
        select(Recipe, RecipeCategory)
        .join(RecipeCategory, Recipe.category_id == RecipeCategory.id)
        .where(Recipe.id == recipe_id)
    )
    row = (await db.execute(stmt)).first()
    if row is None:
        return None

    recipe, category = row
    return {
        "id": recipe.id,
        "name": recipe.name,
        "category_name": category.name,
        "province": category.province,
        "description": recipe.description,
        "ingredients": recipe.ingredients,
        "instructions": recipe.instructions,
        "image_url": recipe.image_url,
        "created_at": recipe.created_at,
    }