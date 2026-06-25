import asyncio
import random
from telegram import Bot
from telegram.error import TelegramError, BadRequest
from src.config import SYMBOLS, WORDS
from src.models import (
    get_tree, get_msg_id, get_task, set_task, pop_task, pop_tree, pop_msg_id
)
from src.rendering import render

# ══════════════════════════════════════════════════════════════
#  СПИННЕР
# ══════════════════════════════════════════════════════════════

async def _spin_loop(bot: Bot, chat_id: int):
    while True:
        await asyncio.sleep(0.8)
        tree   = get_tree(chat_id)
        msg_id = get_msg_id(chat_id)
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

def start_spin(bot: Bot, chat_id: int, row_idx: int):
    tree = get_tree(chat_id)
    if not tree:
        return
    tree.loading_idx = row_idx
    tree.spin_idx    = 0
    tree.spin_dir    = 1
    tree.spin_word   = random.choice(WORDS)
    
    current_task = get_task(chat_id)
    if current_task:
        current_task.cancel()
    
    task = asyncio.create_task(_spin_loop(bot, chat_id))
    set_task(chat_id, task)

async def stop_spin(chat_id: int):
    tree = get_tree(chat_id)
    if tree: tree.loading_idx = -1
    task = pop_task(chat_id)
    if task:
        task.cancel()
        try: await task
        except asyncio.CancelledError: pass

async def edit_message(bot: Bot, chat_id: int):
    tree   = get_tree(chat_id)
    msg_id = get_msg_id(chat_id)
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
            pop_tree(chat_id)
            pop_msg_id(chat_id)
