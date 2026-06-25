"""
SSH-бот — файловый менеджер через Telegram
Навигация через кликабельные ссылки в тексте сообщения.
Клик на папку → разворачивает / сворачивает её прямо в том же сообщении.
"""

import os
import asyncio
import random
import hashlib
import platform
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from telegram import Update
from telegram.error import TelegramError, BadRequest
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# ══════════════════════════════════════════════════════════════
#  КОНФИГ
# ══════════════════════════════════════════════════════════════

# Загрузка переменных окружения из .env
if os.path.exists(".env"):
    with open(".env", "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                parts = line.split("=", 1)
                if len(parts) == 2:
                    os.environ[parts[0].strip()] = parts[1].strip()

BOT_TOKEN     = os.getenv("BOT_TOKEN", "")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не установлен в .env или переменных окружения!")

ALLOWED_USERS : list[int] = []   # [] = все; иначе — whitelist user_id
MAX_ITEMS     = 30               # макс. элементов в одной папке

SYMBOLS = ['•', '+', '×', '⁕', '⁜', '※']
WORDS   = ['fetching', 'scrolling', 'clicking', 'searching']

_bot_username = ""  # заполняется при первом /start

# ══════════════════════════════════════════════════════════════
#  РЕЕСТР ПУТЕЙ  (payload deep-link ограничен 64 байтами)
# ══════════════════════════════════════════════════════════════

_reg: dict[str, str] = {}

def reg(path: str) -> str:
    key = hashlib.md5(path.encode()).hexdigest()[:10]
    _reg[key] = path
    return key

def dereg(key: str) -> Optional[str]:
    return _reg.get(key)

# ══════════════════════════════════════════════════════════════
#  ФАЙЛОВАЯ СИСТЕМА
# ══════════════════════════════════════════════════════════════

def get_drives() -> list[str]:
    if platform.system() == "Windows":
        import string
        return [f"{l}:\\" for l in string.ascii_uppercase if os.path.exists(f"{l}:\\")]
    return ["/"]

def listdir(path: str) -> tuple[list[Path], list[Path]]:
    try:
        entries = list(Path(path).iterdir())
    except PermissionError:
        return [], []
    dirs  = sorted([e for e in entries if e.is_dir()],  key=lambda x: x.name.lower())
    files = sorted([e for e in entries if e.is_file()], key=lambda x: x.name.lower())
    if len(dirs) + len(files) > MAX_ITEMS:
        if len(dirs) >= MAX_ITEMS:
            return dirs[:MAX_ITEMS], []
        return dirs, files[:MAX_ITEMS - len(dirs)]
    return dirs, files

# ══════════════════════════════════════════════════════════════
#  МОДЕЛЬ ДЕРЕВА
# ══════════════════════════════════════════════════════════════

@dataclass
class Row:
    path:         str
    name:         str
    is_dir:       bool
    prefix:       str         # например "├ " или "│   └ "
    child_indent: str         # отступ для детей этой строки
    expanded:     bool = False

@dataclass
class Tree:
    header:      str
    rows:        list[Row] = field(default_factory=list)
    loading_idx: int = -1    # индекс строки с активным спиннером (-1 = нет)
    spin_idx:    int = 0
    spin_dir:    int = 1
    spin_word:   str = ""

# Состояние по чатам
_trees: dict[int, Tree]         = {}
_msgs:  dict[int, int]          = {}   # chat_id → message_id дерева
_tasks: dict[int, asyncio.Task] = {}

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

# ══════════════════════════════════════════════════════════════
#  РЕНДЕРИНГ
# ══════════════════════════════════════════════════════════════

def render(tree: Tree) -> str:
    lines = [tree.header]
    sym   = SYMBOLS[tree.spin_idx]

    for i, row in enumerate(tree.rows):
        if row.is_dir:
            icon = "▾ 📁" if row.expanded else "📁"
            key  = reg(row.path)
            url  = f"https://t.me/{_bot_username}?start=cd_{key}"
            lines.append(f'{row.prefix}<a href="{url}">{icon} {row.name}</a>')
        else:
            lines.append(f"{row.prefix}📄 {row.name}")

        # Спиннер вставляется сразу после загружаемой строки
        if i == tree.loading_idx:
            lines.append(f"{row.child_indent}{sym} {tree.spin_word}...")

    return "\n".join(lines)

# ══════════════════════════════════════════════════════════════
#  СПИННЕР
# ══════════════════════════════════════════════════════════════

async def _spin_loop(bot, chat_id: int):
    while True:
        await asyncio.sleep(0.8)
        tree   = _trees.get(chat_id)
        msg_id = _msgs.get(chat_id)
        if not tree or not msg_id or tree.loading_idx < 0:
            break

        tree.spin_idx += tree.spin_dir
        if tree.spin_idx >= len(SYMBOLS): tree.spin_idx, tree.spin_dir = len(SYMBOLS) - 2, -1
        elif tree.spin_idx < 0:           tree.spin_idx, tree.spin_dir = 1, 1

        try:
            await bot.edit_message_text(
                chat_id=chat_id, message_id=msg_id,
                text=render(tree), parse_mode="HTML",
                disable_web_page_preview=True,
            )
        except BadRequest as e:
            if "not modified" not in str(e).lower(): break
        except TelegramError:
            break

def _start_spin(bot, chat_id: int, row_idx: int):
    tree = _trees[chat_id]
    tree.loading_idx = row_idx
    tree.spin_idx    = 0
    tree.spin_dir    = 1
    tree.spin_word   = random.choice(WORDS)
    if chat_id in _tasks:
        _tasks[chat_id].cancel()
    _tasks[chat_id] = asyncio.create_task(_spin_loop(bot, chat_id))

async def _stop_spin(chat_id: int):
    tree = _trees.get(chat_id)
    if tree: tree.loading_idx = -1
    task = _tasks.pop(chat_id, None)
    if task:
        task.cancel()
        try: await task
        except asyncio.CancelledError: pass

# ══════════════════════════════════════════════════════════════
#  ВСПОМОГАТЕЛЬНЫЕ
# ══════════════════════════════════════════════════════════════

async def _edit(bot, chat_id: int):
    tree   = _trees.get(chat_id)
    msg_id = _msgs.get(chat_id)
    if not tree or not msg_id: return
    try:
        await bot.edit_message_text(
            chat_id=chat_id, message_id=msg_id,
            text=render(tree), parse_mode="HTML",
            disable_web_page_preview=True,
        )
    except BadRequest as e:
        # Сообщение удалено — сбрасываем состояние
        if "message to edit not found" in str(e).lower():
            _trees.pop(chat_id, None)
            _msgs.pop(chat_id, None)

def allowed(uid: int) -> bool:
    return not ALLOWED_USERS or uid in ALLOWED_USERS

# ══════════════════════════════════════════════════════════════
#  ХЭНДЛЕРЫ — НАВИГАЦИЯ
# ══════════════════════════════════════════════════════════════

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global _bot_username
    if not allowed(update.effective_user.id): return

    _bot_username = context.bot.username
    chat_id = update.effective_chat.id

    # Навигационный deep-link (пользователь кликнул на папку)
    if context.args and context.args[0].startswith("cd_"):
        await _navigate(update, context, context.args[0][3:])
        return

    # Начальный экран — диски / корень
    await _stop_spin(chat_id)
    drives = await asyncio.to_thread(get_drives)

    rows = []
    for i, d in enumerate(drives):
        last = (i == len(drives) - 1)
        rows.append(Row(
            path=d, name=d, is_dir=True,
            prefix="└ " if last else "├ ",
            child_indent="    " if last else "│   ",
        ))

    _trees[chat_id] = Tree(header="💻 Диски", rows=rows)
    msg = await update.message.reply_text(
        render(_trees[chat_id]),
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
    _msgs[chat_id] = msg.message_id


async def _navigate(update: Update, context: ContextTypes.DEFAULT_TYPE, key: str):
    """Вызывается когда пользователь кликнул на ссылку папки."""
    chat_id = update.effective_chat.id

    # Удаляем "/start cd_..." сообщение которое отправил Telegram при клике
    try: await update.message.delete()
    except TelegramError: pass

    path = dereg(key)
    if not path: return

    tree   = _trees.get(chat_id)
    msg_id = _msgs.get(chat_id)

    # Нет активного дерева — запускаем с нуля
    if not tree or not msg_id:
        await cmd_start(update, context)
        return

    # Ищем строку с этим путём
    row_idx = next((i for i, r in enumerate(tree.rows) if r.path == path), -1)
    if row_idx < 0: return

    row = tree.rows[row_idx]

    # Тогл: уже развёрнуто → сворачиваем
    if row.expanded:
        collapse_row(tree, row_idx)
        await _edit(context.bot, chat_id)
        return

    # Разворачиваем: сначала показываем спиннер
    _start_spin(context.bot, chat_id, row_idx)
    await _edit(context.bot, chat_id)

    # Загружаем содержимое в фоне
    dirs, files = await asyncio.to_thread(listdir, path)
    await _stop_spin(chat_id)

    # Строим дочерние строки и вставляем их после родителя
    children = build_rows(dirs, files, row.child_indent)
    if not children:
        children = [Row(
            path="", name="(пусто)", is_dir=False,
            prefix=row.child_indent + "└ ",
            child_indent="",
        )]

    # Найти row ещё раз на случай изменений пока грузились
    row_idx = next((i for i, r in enumerate(tree.rows) if r.path == path), row_idx)
    tree.rows = tree.rows[:row_idx + 1] + children + tree.rows[row_idx + 1:]
    tree.rows[row_idx].expanded = True

    await _edit(context.bot, chat_id)

# ══════════════════════════════════════════════════════════════
#  ХЭНДЛЕРЫ — КОМАНДЫ (заготовки для SSH-функций)
# ══════════════════════════════════════════════════════════════

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update.effective_user.id): return
    await update.message.reply_text(
        "🖥 SSH-бот\n\n"
        "Навигация:\n"
        "  /start — файловое дерево\n"
        "  Нажмите на 📁 — раскрыть / свернуть папку\n\n"
        "В разработке:\n"
        "  /exec <cmd>  — выполнить команду\n"
        "  /get  <path> — скачать файл\n"
        "  /put         — загрузить файл на ПК\n"
        "  /sys         — CPU / RAM / диски\n"
        "  /ps          — список процессов\n"
        "  /kill <pid>  — завершить процесс\n"
        "  /find <name> — найти файл\n"
        "  /cat  <path> — прочитать файл\n"
    )

# ── TODO: /exec ────────────────────────────────────────────────
# import subprocess
# async def cmd_exec(update, context):
#     cmd = " ".join(context.args)
#     r = await asyncio.to_thread(
#         subprocess.run, cmd, shell=True, capture_output=True, text=True, timeout=30
#     )
#     await update.message.reply_text(r.stdout or r.stderr or "(нет вывода)")

# ── TODO: /get ─────────────────────────────────────────────────
# async def cmd_get(update, context):
#     path = " ".join(context.args)
#     await context.bot.send_document(update.effective_chat.id, open(path, "rb"))

# ── TODO: /sys ─────────────────────────────────────────────────
# import psutil
# async def cmd_sys(update, context):
#     mem = psutil.virtual_memory()
#     await update.message.reply_text(
#         f"CPU: {psutil.cpu_percent()}%\n"
#         f"RAM: {mem.percent}% ({mem.used//1024**2}/{mem.total//1024**2} MB)"
#     )

# ── TODO: /ps ──────────────────────────────────────────────────
# async def cmd_ps(update, context):
#     procs = "\n".join(f"{p.pid:>6}  {p.name()}" for p in psutil.process_iter(['pid','name']))
#     await update.message.reply_text(f"<pre>{procs}</pre>", parse_mode="HTML")

# ── TODO: /kill ────────────────────────────────────────────────
# async def cmd_kill(update, context):
#     psutil.Process(int(context.args[0])).terminate()
#     await update.message.reply_text("Завершён.")

# ── TODO: /find ────────────────────────────────────────────────
# import fnmatch
# async def cmd_find(update, context): ...  # os.walk + fnmatch.filter

# ── TODO: /cat ─────────────────────────────────────────────────
# async def cmd_cat(update, context):
#     text = Path(" ".join(context.args)).read_text(errors="replace")[:4000]
#     await update.message.reply_text(f"<pre>{text}</pre>", parse_mode="HTML")

# ══════════════════════════════════════════════════════════════
#  ЗАПУСК
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help",  cmd_help))
    app.run_polling()