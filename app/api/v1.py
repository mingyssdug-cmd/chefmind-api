from fastapi import APIRouter

from app.modules.recipe.router import router as recipe_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(recipe_router, tags=["recipe"])