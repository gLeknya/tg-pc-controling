import asyncio
from dataclasses import dataclass, field

# ══════════════════════════════════════════════════════════════
#  МОДЕЛЬ ДЕРЕВА
# ══════════════════════════════════════════════════════════════

from typing import Optional

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
    current_photo: Optional[str] = None
    photo_file_id: Optional[str] = None

# Состояние по чатам
_trees: dict[int, Tree]         = {}
_msgs:  dict[int, int]          = {}   # chat_id → message_id дерева
_tasks: dict[int, asyncio.Task] = {}

def get_tree(chat_id: int) -> Tree | None:
    return _trees.get(chat_id)

def set_tree(chat_id: int, tree: Tree):
    _trees[chat_id] = tree

def pop_tree(chat_id: int) -> Tree | None:
    return _trees.pop(chat_id, None)

def get_msg_id(chat_id: int) -> int | None:
    return _msgs.get(chat_id)

def set_msg_id(chat_id: int, msg_id: int):
    _msgs[chat_id] = msg_id

def pop_msg_id(chat_id: int) -> int | None:
    return _msgs.pop(chat_id, None)

def get_task(chat_id: int) -> asyncio.Task | None:
    return _tasks.get(chat_id)

def set_task(chat_id: int, task: asyncio.Task):
    _tasks[chat_id] = task

def pop_task(chat_id: int) -> asyncio.Task | None:
    return _tasks.pop(chat_id, None)
