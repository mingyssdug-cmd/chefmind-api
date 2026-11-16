import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class RecipeCategory(Base):
    __tablename__ = "recipe_category"
    __table_args__ = (
        UniqueConstraint("name", "province", name="uq_category_name_province"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    province: Mapped[str] = mapped_column(String(50), index=True, nullable=False)

    recipes: Mapped[list["Recipe"]] = relationship(
        back_populates="category", cascade="all, delete-orphan"
    )


class Recipe(Base):
    __tablename__ = "recipe"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    category_id: Mapped[int] = mapped_column(
        ForeignKey("recipe_category.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    ingredients: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    raw_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    category: Mapped["RecipeCategory"] = relationship(back_populates="recipes")