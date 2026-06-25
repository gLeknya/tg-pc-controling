import os
import asyncio
import platform
import fnmatch
import subprocess
import logging
from pathlib import Path
from typing import Optional
from telegram import Update, Bot
from telegram.error import TelegramError
from telegram.ext import ContextTypes

logger = logging.getLogger("bot.handlers")

# Конфиг и вспомогательные функции
from src.config import allowed, set_bot_username, get_bot_username
from src.registry import dereg
from src.models import (
    Row, Tree, get_tree, get_msg_id, set_tree, set_msg_id
)
from src.fs import get_drives, listdir
from src.rendering import render, build_rows, collapse_row
from src.spinner import start_spin, stop_spin, edit_message

# ══════════════════════════════════════════════════════════════
#  ХЭНДЛЕРЫ — НАВИГАЦИЯ
# ══════════════════════════════════════════════════════════════

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not allowed(user.id): 
        return

    logger.info(f"User {user.id}: /start")
    set_bot_username(context.bot.username)
    chat_id = update.effective_chat.id

    # Навигационный deep-link (пользователь кликнул на папку)
    if context.args and context.args[0].startswith("cd_"):
        await _navigate(update, context, context.args[0][3:])
        return

    # Начальный экран — диски / корень
    await stop_spin(chat_id)
    drives = await asyncio.to_thread(get_drives)

    rows = []
    for i, d in enumerate(drives):
        last = (i == len(drives) - 1)
        rows.append(Row(
            path=d, name=d, is_dir=True,
            prefix="└ " if last else "├ ",
            child_indent="    " if last else "│   ",
        ))

    tree = Tree(header="💻 Диски", rows=rows)
    set_tree(chat_id, tree)
    
    msg = await update.message.reply_text(
        render(tree),
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
    set_msg_id(chat_id, msg.message_id)


async def _navigate(update: Update, context: ContextTypes.DEFAULT_TYPE, key: str):
    """Вызывается когда пользователь кликнул на ссылку папки."""
    chat_id = update.effective_chat.id
    user = update.effective_user

    # Удаляем "/start cd_..." сообщение которое отправил Telegram при клике
    try: 
        await update.message.delete()
    except TelegramError: 
        pass

    path = dereg(key)
    if not path: 
        logger.warning(f"User {user.id}: invalid nav key {key}")
        return

    logger.info(f"User {user.id}: cd {path}")

    tree = get_tree(chat_id)
    msg_id = get_msg_id(chat_id)

    # Нет активного дерева — запускаем с нуля
    if not tree or not msg_id:
        logger.info(f"Chat {chat_id}: active tree not found, restarting")
        await cmd_start(update, context)
        return

    # Ищем строку с этим путём
    row_idx = next((i for i, r in enumerate(tree.rows) if r.path == path), -1)
    if row_idx < 0: 
        logger.warning(f"Chat {chat_id}: path {path} not in tree")
        return

    row = tree.rows[row_idx]

    # Тогл: уже развёрнуто → сворачиваем
    if row.expanded:
        collapse_row(tree, row_idx)
        await edit_message(context.bot, chat_id)
        return

    # Разворачиваем: сначала показываем спиннер
    start_spin(context.bot, chat_id, row_idx)
    await edit_message(context.bot, chat_id)

    # Загружаем содержимое в фоне
    dirs, files = await asyncio.to_thread(listdir, path)
    await stop_spin(chat_id)

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

    await edit_message(context.bot, chat_id)


# ══════════════════════════════════════════════════════════════
#  ХЭНДЛЕРЫ — КОМАНДЫ ДЛЯ УПРАВЛЕНИЯ ПК
# ══════════════════════════════════════════════════════════════

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not allowed(user.id): 
        return
    logger.info(f"User {user.id}: /help")
    await update.message.reply_text(
        "🖥 <b>SSH-бот (Управление ПК)</b>\n\n"
        "<b>Навигация:</b>\n"
        "  /start — файловое дерево\n"
        "  Нажмите на 📁 — раскрыть / свернуть папку\n\n"
        "<b>Управление:</b>\n"
        "  /exec &lt;cmd&gt;  — выполнить команду\n"
        "  /get  &lt;path&gt; — скачать файл\n"
        "  /put         — инструкция для загрузки файлов на ПК\n"
        "  /sys         — CPU / RAM / диски\n"
        "  /ps          — список процессов\n"
        "  /kill &lt;pid&gt;  — завершить процесс\n"
        "  /find &lt;name&gt; — найти файл\n"
        "  /cat  &lt;path&gt; — прочитать файл\n",
        parse_mode="HTML"
    )


async def cmd_exec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not allowed(user.id): 
        return
    if not context.args:
        await update.message.reply_text("Использование: /exec &lt;команда&gt;", parse_mode="HTML")
        return
    cmd = " ".join(context.args)
    logger.info(f"User {user.id}: /exec {cmd}")
    
    try:
        # Выполнение команды в отдельном потоке
        r = await asyncio.to_thread(
            subprocess.run, 
            cmd, 
            shell=True, 
            capture_output=True, 
            text=True, 
            timeout=30
        )
        output = r.stdout or r.stderr or "(нет вывода)"
        if len(output) > 4000:
            output = output[:4000] + "\n... [вывод усечён]"
        await update.message.reply_text(f"<pre>{output}</pre>", parse_mode="HTML")
    except Exception as e:
        logger.error(f"User {user.id}: /exec '{cmd}' failed: {e}")
        await update.message.reply_text(f"Ошибка выполнения: {e}")


async def cmd_get(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not allowed(user.id): 
        return
    if not context.args:
        await update.message.reply_text("Использование: /get &lt;путь_к_файлу&gt;", parse_mode="HTML")
        return
    path_str = " ".join(context.args)
    path = Path(path_str)
    
    logger.info(f"User {user.id}: /get {path_str}")
    
    if not path.exists():
        logger.warning(f"User {user.id}: /get file not found: {path_str}")
        await update.message.reply_text("Файл не найден.")
        return
    if not path.is_file():
        logger.warning(f"User {user.id}: /get path is not a file: {path_str}")
        await update.message.reply_text("Указанный путь не является файлом.")
        return
        
    try:
        # Отправляем файл пользователю
        with open(path, "rb") as f:
            await context.bot.send_document(
                chat_id=update.effective_chat.id, 
                document=f,
                filename=path.name
            )
    except Exception as e:
        logger.error(f"User {user.id}: /get '{path_str}' failed: {e}")
        await update.message.reply_text(f"Ошибка отправки файла: {e}")


async def cmd_put(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not allowed(user.id): 
        return
    logger.info(f"User {user.id}: /put")
    await update.message.reply_text(
        "Чтобы загрузить файл на ПК, просто пришлите его мне как документ (файл).\n"
        "Он будет сохранен в последнюю открытую вами папку или в рабочую директорию бота."
    )


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not allowed(user.id): 
        return
    
    chat_id = update.effective_chat.id
    dest_dir = Path.cwd()
    
    # Попробуем сохранить файл в последнюю раскрытую папку
    tree = get_tree(chat_id)
    if tree:
        expanded_dirs = [r.path for r in tree.rows if r.is_dir and r.expanded]
        if expanded_dirs:
            dest_dir = Path(expanded_dirs[-1])
            
    doc = update.message.document
    dest_path = dest_dir / doc.file_name
    
    logger.info(f"User {user.id}: upload {doc.file_name} -> {dest_dir}")
    
    try:
        # Скачиваем файл в отдельном потоке
        new_file = await context.bot.get_file(doc.file_id)
        await new_file.download_to_drive(custom_path=dest_path)
        await update.message.reply_text(f"Файл успешно сохранен в: <code>{dest_path}</code>", parse_mode="HTML")
    except Exception as e:
        logger.error(f"User {user.id}: upload '{doc.file_name}' failed: {e}")
        await update.message.reply_text(f"Ошибка сохранения файла: {e}")


async def cmd_sys(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not allowed(user.id): 
        return
    logger.info(f"User {user.id}: /sys")
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=0.5)
        mem = psutil.virtual_memory()
        
        drives_info = []
        if platform.system() == "Windows":
            import string
            drives = [f"{l}:\\" for l in string.ascii_uppercase if os.path.exists(f"{l}:\\")]
        else:
            drives = ["/"]
            
        for drive in drives:
            try:
                usage = psutil.disk_usage(drive)
                drives_info.append(
                    f"  Диск {drive}: {usage.percent}% (свободно {usage.free // 1024**3} GB из {usage.total // 1024**3} GB)"
                )
            except Exception:
                pass
                
        drives_str = "\n".join(drives_info)
        
        await update.message.reply_text(
            f"💻 <b>Информация о системе:</b>\n\n"
            f"🖥 OS: {platform.system()} {platform.release()} ({platform.architecture()[0]})\n"
            f"🔥 CPU: {cpu}%\n"
            f"💾 RAM: {mem.percent}% (использовано {mem.used // 1024**2} MB из {mem.total // 1024**2} MB)\n"
            f"📁 Диски:\n{drives_str}",
            parse_mode="HTML"
        )
    except ImportError:
        await update.message.reply_text(
            "Для работы этой команды необходима библиотека <code>psutil</code>.\n"
            "Вы можете установить её с помощью:\n"
            "<code>pip install psutil</code>",
            parse_mode="HTML"
        )


async def cmd_ps(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not allowed(user.id): 
        return
    logger.info(f"User {user.id}: /ps")
    try:
        import psutil
        
        processes = []
        for p in psutil.process_iter(['pid', 'name']):
            try:
                processes.append((p.info['pid'], p.info['name'] or 'Unknown'))
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
                
        processes = sorted(processes, key=lambda x: x[0])
        
        lines = [f"{'PID':>6}  {'Имя процесса'}"]
        lines.append("-" * 30)
        for pid, name in processes[:100]:
            lines.append(f"{pid:>6}  {name}")
            
        procs = "\n".join(lines)
        if len(procs) > 4000:
            procs = procs[:4000] + "\n... [вывод усечён]"
            
        await update.message.reply_text(f"<pre>{procs}</pre>", parse_mode="HTML")
    except ImportError:
        logger.warning("psutil missing for /ps")
        await update.message.reply_text(
            "Для работы этой команды необходима библиотека <code>psutil</code>.\n"
            "Вы можете установить её с помощью:\n"
            "<code>pip install psutil</code>",
            parse_mode="HTML"
        )


async def cmd_kill(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not allowed(user.id): 
        return
    if not context.args:
        await update.message.reply_text("Использование: /kill &lt;PID&gt;", parse_mode="HTML")
        return
        
    try:
        pid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("PID должен быть числом.")
        return
        
    logger.info(f"User {user.id}: /kill {pid}")
    
    try:
        import psutil
        process = psutil.Process(pid)
        process.terminate()
        await update.message.reply_text(f"Сигнал завершения отправлен процессу {pid} ({process.name()}).")
    except ImportError:
        # Системное завершение через subprocess
        try:
            if platform.system() == "Windows":
                cmd = f"taskkill /F /PID {pid}"
            else:
                cmd = f"kill -9 {pid}"
            r = await asyncio.to_thread(subprocess.run, cmd, shell=True, capture_output=True, text=True)
            if r.returncode == 0:
                await update.message.reply_text(f"Процесс {pid} завершен системной командой.")
            else:
                await update.message.reply_text(f"Ошибка: {r.stderr or r.stdout}")
        except Exception as e:
            logger.error(f"User {user.id}: /kill {pid} failed: {e}")
            await update.message.reply_text(f"Ошибка завершения процесса: {e}")
    except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
        logger.error(f"User {user.id}: /kill {pid} failed: {e}")
        await update.message.reply_text(f"Не удалось завершить процесс {pid}: {e}")


async def cmd_find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not allowed(user.id): 
        return
    if not context.args:
        await update.message.reply_text("Использование: /find &lt;маска_файла&gt; [стартовая_папка]", parse_mode="HTML")
        return
        
    pattern = context.args[0]
    start_dir = context.args[1] if len(context.args) > 1 else "."
    
    logger.info(f"User {user.id}: /find {pattern} in {start_dir}")
    
    def search():
        matches = []
        for root, dirnames, filenames in os.walk(start_dir):
            for filename in fnmatch.filter(filenames, pattern):
                matches.append(os.path.join(root, filename))
                if len(matches) >= 30:
                    return matches, True
            for dirname in fnmatch.filter(dirnames, pattern):
                matches.append(os.path.join(root, dirname))
                if len(matches) >= 30:
                    return matches, True
        return matches, False

    try:
        await update.message.reply_text(f"Поиск <code>{pattern}</code> в <code>{start_dir}</code>...", parse_mode="HTML")
        matches, truncated = await asyncio.to_thread(search)
        
        if not matches:
            await update.message.reply_text("Ничего не найдено.")
            return
            
        res_text = "\n".join(matches)
        if truncated:
            res_text += "\n\n⚠️ Показаны первые 30 результатов."
            
        if len(res_text) > 4000:
            res_text = res_text[:4000] + "\n... [вывод усечён]"
            
        await update.message.reply_text(f"<pre>{res_text}</pre>", parse_mode="HTML")
    except Exception as e:
        logger.error(f"User {user.id}: /find {pattern} failed: {e}")
        await update.message.reply_text(f"Ошибка при поиске: {e}")


async def cmd_cat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not allowed(user.id): 
        return
    if not context.args:
        await update.message.reply_text("Использование: /cat &lt;путь_к_файлу&gt;", parse_mode="HTML")
        return
        
    path_str = " ".join(context.args)
    path = Path(path_str)
    
    logger.info(f"User {user.id}: /cat {path_str}")
    
    if not path.exists():
        logger.warning(f"User {user.id}: /cat file not found: {path_str}")
        await update.message.reply_text("Файл не найден.")
        return
    if not path.is_file():
        logger.warning(f"User {user.id}: /cat path is not a file: {path_str}")
        await update.message.reply_text("Указанный путь не является файлом.")
        return
        
    try:
        def read_file():
            return path.read_text(encoding="utf-8", errors="replace")
            
        text = await asyncio.to_thread(read_file)
        
        import html
        escaped_text = html.escape(text)
        
        if len(escaped_text) > 4000:
            escaped_text = escaped_text[:4000] + "\n... [вывод усечён]"
            
        await update.message.reply_text(f"<pre>{escaped_text}</pre>", parse_mode="HTML")
    except Exception as e:
        logger.error(f"User {user.id}: /cat '{path_str}' failed: {e}")
        await update.message.reply_text(f"Ошибка чтения файла: {e}")
