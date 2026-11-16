import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.recipe import crud
from app.modules.recipe.schemas import (
    CategoryOut,
    RecipeDetail,
    RecipeListResponse,
)

router = APIRouter()


@router.get("/provinces", response_model=list[str], summary="获取省份列表")
async def get_provinces(db: AsyncSession = Depends(get_db)):
    """前端省份下拉框数据源"""
    return await crud.list_provinces(db)


@router.get("/categories", response_model=list[CategoryOut], summary="获取菜系列表")
async def get_categories(
    province: str | None = Query(default=None, description="按省份过滤，如「河南省」"),
    db: AsyncSession = Depends(get_db),
):
    return await crud.list_categories(db, province)


@router.get("/recipes", response_model=RecipeListResponse, summary="获取菜谱列表（分页+搜索）")
async def get_recipes(
    province: str | None = Query(default=None, description="按省份过滤，如「河南省」"),
    category_id: int | None = Query(default=None, description="按菜系过滤"),
    keyword: str | None = Query(default=None, description="按菜名模糊搜索"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    total, items = await crud.list_recipes(
        db, province, category_id, keyword, page, page_size
    )
    return {"total": total, "page": page, "page_size": page_size, "items": items}


@router.get("/recipes/{recipe_id}", response_model=RecipeDetail, summary="获取菜谱详情")
async def get_recipe_detail(recipe_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    data = await crud.get_recipe(db, recipe_id)
    if data is None:
        raise HTTPException(status_code=404, detail="菜谱不存在")
    return data