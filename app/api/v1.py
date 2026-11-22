from fastapi import APIRouter

from app.modules.recipe.router import router as recipe_router

from app.modules.chef.router import router as chef_router

from app.modules.user.router import router as auth_router
api_router = APIRouter(prefix="/api/v1")
api_router.include_router(recipe_router, tags=["recipe"])
api_router.include_router(chef_router)
api_router.include_router(auth_router)