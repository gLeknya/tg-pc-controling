import html
from pathlib import Path
from src.config import SYMBOLS, get_bot_username
from src.registry import reg
from src.models import Row, Tree

# ══════════════════════════════════════════════════════════════
#  ПОСТРОЕНИЕ СТРОК
# ══════════════════════════════════════════════════════════════

def build_rows(dirs: list[Path], files: list[Path], indent: str) -> list[Row]:
    all_items = list(dirs) + list(files)
    rows = []
    for i, item in enumerate(all_items):
        last = (i == len(all_items) - 1)
        rows.append(Row(
            path=str(item), name=item.name,
            is_dir=item in dirs,
            prefix=indent + ("└ " if last else "├ "),
            child_indent=indent + ("    " if last else "│   "),
        ))
    return rows

def collapse_row(tree: Tree, idx: int):
    """Убрать всех потомков строки idx из плоского списка."""
    plen = len(tree.rows[idx].prefix)
    end  = idx + 1
    while end < len(tree.rows) and len(tree.rows[end].prefix) > plen:
        end += 1
    tree.rows = tree.rows[:idx + 1] + tree.rows[end:]
    tree.rows[idx].expanded = False

IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp'}

def is_image(path_str: str) -> bool:
    return Path(path_str).suffix.lower() in IMAGE_EXTENSIONS

# ══════════════════════════════════════════════════════════════
#  РЕНДЕРИНГ
# ══════════════════════════════════════════════════════════════

def render(tree: Tree) -> str:
    lines = [tree.header]
    sym   = SYMBOLS[tree.spin_idx]
    bot_username = get_bot_username()

    # Вычисляем позицию спиннера: под последним загруженным элементом папки
    spinner_idx = tree.loading_idx
    spinner_indent = ""
    if tree.loading_idx >= 0 and tree.loading_idx < len(tree.rows):
        parent_row = tree.rows[tree.loading_idx]
        spinner_indent = parent_row.child_indent
        plen = len(parent_row.prefix)
        end = tree.loading_idx + 1
        while end < len(tree.rows) and len(tree.rows[end].prefix) > plen:
            end += 1
        spinner_idx = end - 1

    for i, row in enumerate(tree.rows):
        escaped_name = html.escape(row.name)
        if row.is_dir:
            icon = "▾ 📁" if row.expanded else "📁"
            key  = reg(row.path)
            url  = f"https://t.me/{bot_username}?start=cd_{key}"
            lines.append(f'{row.prefix}<a href="{url}">{icon} {escaped_name}</a>')
        else:
            if is_image(row.path):
                key = reg(row.path)
                url = f"https://t.me/{bot_username}?start=view_{key}"
                lines.append(f'{row.prefix}<a href="{url}">🖼 {escaped_name}</a>')
            else:
                lines.append(f"{row.prefix}📄 {escaped_name}")

        # Спиннер вставляется сразу после вычисленной строки
        if i == spinner_idx and tree.loading_idx >= 0:
            lines.append(f"{spinner_indent}{sym} {tree.spin_word}...")

    return "\n".join(lines)
