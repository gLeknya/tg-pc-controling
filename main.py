"""
SSH-бот — файловый менеджер через Telegram
Навигация через кликабельные ссылки в тексте сообщения.
Клик на папку → разворачивает / сворачивает её прямо в том же сообщении.

Этот файл является точкой входа. Вся логика разделена на модули в пакете src/.
"""

from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters

# Импорт конфигурации и хэндлеров
from src.config import BOT_TOKEN
from src.handlers import (
    cmd_start, 
    cmd_help, 
    cmd_exec, 
    cmd_get, 
    cmd_put, 
    cmd_sys, 
    cmd_ps, 
    cmd_kill, 
    cmd_find, 
    cmd_cat, 
    handle_document
)

import logging

logger = logging.getLogger("bot")

# ══════════════════════════════════════════════════════════════
#  ЗАПУСК
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    logger.info("Запуск бота...")
    # Инициализация приложения Telegram-бота с токеном из config
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # Хэндлеры навигации и справки
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help",  cmd_help))
    
    # Хэндлеры управления ПК
    app.add_handler(CommandHandler("exec",  cmd_exec))
    app.add_handler(CommandHandler("get",   cmd_get))
    app.add_handler(CommandHandler("put",   cmd_put))
    app.add_handler(CommandHandler("sys",   cmd_sys))
    app.add_handler(CommandHandler("ps",    cmd_ps))
    app.add_handler(CommandHandler("kill",  cmd_kill))
    app.add_handler(CommandHandler("find",  cmd_find))
    app.add_handler(CommandHandler("cat",   cmd_cat))
    
    # Прием файлов/документов
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    # Запуск поллинга
    logger.info("Бот запущен. Ожидание сообщений...")
    app.run_polling()