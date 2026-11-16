import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    province: str


class RecipeListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    category_name: str
    province: str
    image_url: str | None
    description: str | None


class RecipeListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[RecipeListItem]


class RecipeDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    category_name: str
    province: str
    description: str | None
    ingredients: list[Any]
    instructions: str | None
    image_url: str | None
    created_at: datetime