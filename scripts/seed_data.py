"""
Markdown 菜谱解析并落库（支持多城市、多菜系）。
目录约定：
    data/raw/<城市>/<任意文件名>.md
省份由目录名推断，例如：
    data/raw/河南/河南菜谱.md   -> 河南省
    data/raw/北京/北京菜谱.md   -> 北京市
    data/raw/四川/川菜.md       -> 四川省

用法：
    python -m scripts.seed_data                    # 扫描 data/raw 下所有 .md
    python -m scripts.seed_data data/raw/北京/北京菜谱.md
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
RAW_DIR = Path("data/raw")
DEFAULT_PROVINCE = "未知"

# 城市/省份目录名 -> 正式省份名。后期加城市只在这里加一行，脚本不用动。
PROVINCE_MAP: dict[str, str] = {
    "河南": "河南省",
    "北京": "北京市",
    "四川": "四川省",
    "广东": "广东省",
    "山东": "山东省",
    "江苏": "江苏省",
    "浙江": "浙江省",
    "湖南": "湖南省",
    "湖北": "湖北省",
    "陕西": "陕西省",
    # TODO: 按需继续补
}

# 固定 6 大类菜系（H2），其余 H2 忽略
VALID_CATEGORIES = {
    "山珍海味菜",
    "肉菜",
    "禽蛋菜",
    "水产菜",
    "植物菜",
    "其他菜",
}

H2_RE = re.compile(r"^##\s+(.+)$", re.M)
H3_RE = re.compile(r"^###\s+(.+)$", re.M)
INGREDIENT_HEAD_RE = re.compile(r"^\*\*原料\*\*\s*$", re.M)
METHOD_HEAD_RE = re.compile(r"^\*\*制法\*\*\s*$", re.M)
SUB_HEAD_RE = re.compile(r"^\*\*(.+?)\*\*\s*$", re.M)

ITEM_WITH_GROUP_RE = re.compile(r"^[-*·]?\s*([^：:]{1,10})[：:]\s*(.+)$")
LIST_PREFIX_RE = re.compile(r"^[-*·]\s*")


def _strip_list_prefix(line: str) -> str:
    return LIST_PREFIX_RE.sub("", line).strip()


def _infer_province(md_path: Path) -> str:
    """从目录名/文件名推断省份。优先父目录名，其次文件名。"""
    for key, prov in PROVINCE_MAP.items():
        if key in md_path.parent.name or key in md_path.stem:
            return prov
    return DEFAULT_PROVINCE


def _split_categories(text: str) -> list[tuple[str, str]]:
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
    matches = list(H3_RE.finditer(block))
    result = []
    for i, m in enumerate(matches):
        name = m.group(1).strip()
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(block)
        result.append((name, block[start:end].strip()))
    return result


def _parse_ingredients(ing_text: str) -> list[dict]:
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

    sub_heads = list(SUB_HEAD_RE.finditer(ing_text))
    if sub_heads:
        for i, sh in enumerate(sub_heads):
            group = sh.group(1).strip()
            s = sh.end()
            e = sub_heads[i + 1].start() if i + 1 < len(sub_heads) else len(ing_text)
            for line in ing_text[s:e].splitlines():
                item = _strip_list_prefix(line)
                if item:
                    add(group, item)
    else:
        for line in ing_text.splitlines():
            raw = line.strip()
            if not raw:
                continue
            if re.match(r"^\*\*.+\*\*\s*$", raw):
                continue
            item = _strip_list_prefix(raw)
            if not item:
                continue
            m = ITEM_WITH_GROUP_RE.match(item)
            if m:
                add(m.group(1).strip(), m.group(2).strip())
            else:
                add("原料", item)

    return [{g: groups[g]} for g in order]


def _parse_chunk(chunk: str) -> dict:
    ing_head = INGREDIENT_HEAD_RE.search(chunk)
    method_head = METHOD_HEAD_RE.search(chunk)

    first_nl = chunk.find("\n")
    desc_start = first_nl + 1 if first_nl != -1 else len(chunk)
    desc_end = ing_head.start() if ing_head else (method_head.start() if method_head else len(chunk))
    description = chunk[desc_start:desc_end].strip() or None

    ingredients: list[dict] = []
    if ing_head:
        ing_end = method_head.start() if method_head else len(chunk)
        ingredients = _parse_ingredients(chunk[ing_head.end():ing_end])

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
    db: AsyncSession, name: str, province: str
) -> RecipeCategory:
    stmt = select(RecipeCategory).where(
        RecipeCategory.name == name,
        RecipeCategory.province == province,
    )
    category = (await db.execute(stmt)).scalar_one_or_none()
    if category is None:
        category = RecipeCategory(name=name, province=province)
        db.add(category)
        await db.flush()
    return category


async def _recipe_exists(db: AsyncSession, name: str, category_id: int) -> bool:
    stmt = select(Recipe.id).where(Recipe.name == name, Recipe.category_id == category_id)
    return (await db.execute(stmt)).first() is not None


async def seed_file(db: AsyncSession, md_path: Path) -> tuple[int, int]:
    text = md_path.read_text(encoding="utf-8")
    province = _infer_province(md_path)
    inserted = 0
    skipped = 0

    for cat_name, cat_block in _split_categories(text):
        category = await _get_or_create_category(db, cat_name, province)

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


def _discover_files() -> list[Path]:
    """递归扫描 data/raw 下所有 .md"""
    if not RAW_DIR.exists():
        return []
    return sorted(RAW_DIR.rglob("*.md"))


async def main(paths: list[Path]) -> None:
    await init_db()

    total_inserted = 0
    total_skipped = 0
    async with AsyncSessionLocal() as db:
        for p in paths:
            if not p.exists():
                print(f"[SKIP] 文件不存在: {p}")
                continue
            province = _infer_province(p)
            ins, skp = await seed_file(db, p)
            print(f"[OK] {p} (province={province}): 新增 {ins} 条，跳过 {skp} 条")
            total_inserted += ins
            total_skipped += skp

    print(f"[DONE] 共新增 {total_inserted} 条，跳过 {total_skipped} 条")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        files = [Path(a) for a in sys.argv[1:]]
    else:
        files = _discover_files()
        if not files:
            print(f"未找到 {RAW_DIR}/**/*.md，请把 Markdown 文件放进去")
            sys.exit(1)
    asyncio.run(main(files))