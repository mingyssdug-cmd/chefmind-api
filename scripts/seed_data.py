"""
Markdown 菜谱解析并落库（河南省）。
用法：
    python -m scripts.seed_data
    python -m scripts.seed_data data/raw/菜谱.md
"""

import asyncio
import re
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal, init_db
from app.modules.recipe.models import Recipe, RecipeCategory

# ============ 固定配置 ============
PROVINCE = "河南省"
RAW_DIR = Path("data/raw")

# 五个固定菜系（H2），其余 H2 忽略
VALID_CATEGORIES = {
    "山珍海味菜",
    "肉菜",
    "禽蛋菜",
    "水产菜",
    "植物菜",
}

H2_RE = re.compile(r"^##\s+(.+)$", re.M)          # 菜系
H3_RE = re.compile(r"^###\s+(.+)$", re.M)         # 菜名
INGREDIENT_HEAD_RE = re.compile(r"^\*\*原料\*\*\s*$", re.M)
METHOD_HEAD_RE = re.compile(r"^\*\*制法\*\*\s*$", re.M)
SUB_HEAD_RE = re.compile(r"^\*\*(.+?)\*\*\s*$", re.M)  # 主料/配料/调料 等小标题

# 原料条目：- 主料：竹荪 50g / * 配料: 火腿 20g / 主料：xxx
ITEM_WITH_GROUP_RE = re.compile(r"^[-*·]?\s*([^：:]{1,10})[：:]\s*(.+)$")
LIST_PREFIX_RE = re.compile(r"^[-*·]\s*")


def _strip_list_prefix(line: str) -> str:
    return LIST_PREFIX_RE.sub("", line).strip()


def _split_categories(text: str) -> list[tuple[str, str]]:
    """返回 [(菜系名, 该菜系段落文本)]，只保留 VALID_CATEGORIES"""
    matches = list(H2_RE.finditer(text))
    result = []
    for i, m in enumerate(matches):
        name = m.group(1).strip()
        if name not in VALID_CATEGORIES:
            continue
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        result.append((name, text[start:end]))
    return result


def _split_recipes(block: str) -> list[tuple[str, str]]:
    """返回 [(菜名, 菜谱 chunk 文本)]"""
    matches = list(H3_RE.finditer(block))
    result = []
    for i, m in enumerate(matches):
        name = m.group(1).strip()
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(block)
        result.append((name, block[start:end].strip()))
    return result


def _parse_ingredients(ing_text: str) -> list[dict]:
    """
    解析原料文本，输出 [{"主料": [...]}, {"配料": [...]}, {"调料": [...]}]
    兼容三种写法：
      A. 条目带分组前缀：- 主料：竹荪 50g
      B. 小标题分组 + 纯条目：**主料**\\n- 竹荪 50g
      C. 无分组纯条目：- 竹荪 50g  → 归入「原料」
    """
    groups: dict[str, list[str]] = {}
    order: list[str] = []

    def add(group: str, item: str):
        item = item.strip()
        if not item:
            return
        if group not in groups:
            groups[group] = []
            order.append(group)
        groups[group].append(item)

    # 先看有没有小标题（**主料** 等单独成行）
    sub_heads = list(SUB_HEAD_RE.finditer(ing_text))
    if sub_heads:
        # 写法 B
        for i, sh in enumerate(sub_heads):
            group = sh.group(1).strip()
            s = sh.end()
            e = sub_heads[i + 1].start() if i + 1 < len(sub_heads) else len(ing_text)
            for line in ing_text[s:e].splitlines():
                item = _strip_list_prefix(line)
                if item:
                    add(group, item)
    else:
        # 写法 A / C：逐行解析
        for line in ing_text.splitlines():
            raw = line.strip()
            if not raw:
                continue
            # 跳过加粗小标题行（如 **原料** 自身已在外部截掉，这里防万一）
            if re.match(r"^\*\*.+\*\*\s*$", raw):
                continue
            item = _strip_list_prefix(raw)
            if not item:
                continue
            m = ITEM_WITH_GROUP_RE.match(item)
            if m:
                group = m.group(1).strip()
                content = m.group(2).strip()
                add(group, content)
            else:
                add("原料", item)

    return [{g: groups[g]} for g in order]


def _parse_chunk(chunk: str) -> dict:
    ing_head = INGREDIENT_HEAD_RE.search(chunk)
    method_head = METHOD_HEAD_RE.search(chunk)

    # description：菜名行之后到 **原料** 之前
    first_nl = chunk.find("\n")
    desc_start = first_nl + 1 if first_nl != -1 else len(chunk)
    desc_end = ing_head.start() if ing_head else (method_head.start() if method_head else len(chunk))
    description = chunk[desc_start:desc_end].strip() or None

    # ingredients
    ingredients: list[dict] = []
    if ing_head:
        ing_end = method_head.start() if method_head else len(chunk)
        ing_text = chunk[ing_head.end():ing_end]
        ingredients = _parse_ingredients(ing_text)

    # instructions
    instructions = None
    if method_head:
        instructions = chunk[method_head.end():].strip() or None

    return {
        "description": description,
        "ingredients": ingredients,
        "instructions": instructions,
        "raw_markdown": chunk.strip(),
    }


async def _get_or_create_category(
    db: AsyncSession, name: str
) -> RecipeCategory:
    stmt = select(RecipeCategory).where(RecipeCategory.name == name)
    category = (await db.execute(stmt)).scalar_one_or_none()
    if category is None:
        category = RecipeCategory(name=name, province=PROVINCE)
        db.add(category)
        await db.flush()
    return category


async def _recipe_exists(db: AsyncSession, name: str, category_id: int) -> bool:
    stmt = select(Recipe.id).where(Recipe.name == name, Recipe.category_id == category_id)
    return (await db.execute(stmt)).first() is not None


async def seed_file(db: AsyncSession, md_path: Path) -> tuple[int, int]:
    text = md_path.read_text(encoding="utf-8")
    inserted = 0
    skipped = 0

    for cat_name, cat_block in _split_categories(text):
        category = await _get_or_create_category(db, cat_name)

        for recipe_name, chunk in _split_recipes(cat_block):
            if await _recipe_exists(db, recipe_name, category.id):
                skipped += 1
                continue

            parsed = _parse_chunk(chunk)
            recipe = Recipe(
                category_id=category.id,
                name=recipe_name,
                description=parsed["description"],
                ingredients=parsed["ingredients"],
                instructions=parsed["instructions"],
                image_url=None,
                raw_markdown=parsed["raw_markdown"],
            )
            db.add(recipe)
            inserted += 1

    await db.commit()
    return inserted, skipped


async def main(paths: list[Path]) -> None:
    await init_db()

    total_inserted = 0
    total_skipped = 0
    async with AsyncSessionLocal() as db:
        for p in paths:
            if not p.exists():
                print(f"[SKIP] 文件不存在: {p}")
                continue
            ins, skp = await seed_file(db, p)
            print(f"[OK] {p}: 新增 {ins} 条，跳过 {skp} 条")
            total_inserted += ins
            total_skipped += skp

    print(f"[DONE] 共新增 {total_inserted} 条，跳过 {total_skipped} 条")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        files = [Path(a) for a in sys.argv[1:]]
    else:
        files = sorted(RAW_DIR.glob("*.md"))
        if not files:
            print(f"未找到 {RAW_DIR}/*.md，请把 Markdown 文件放进去，或传入文件路径")
            sys.exit(1)
    asyncio.run(main(files))