import os
import logging
from typing import Optional

# Настройка логирования в консоль (простой и лаконичный формат)
logging.basicConfig(
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    level=logging.INFO
)
logger = logging.getLogger("bot")

# Отключаем спам HTTP-запросов от библиотек telegram и httpx
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)

# Загрузка переменных окружения из .env
if os.path.exists(".env"):
    logger.info("Загрузка .env")
    with open(".env", "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                parts = line.split("=", 1)
                if len(parts) == 2:
                    os.environ[parts[0].strip()] = parts[1].strip()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
if not BOT_TOKEN:
    logger.error("BOT_TOKEN не найден в .env!")
    raise ValueError("BOT_TOKEN не установлен в .env или переменных окружения!")


# Whitelist пользователей
ALLOWED_USERS: list[int] = []
ALLOWED_USERS_RAW = os.getenv("ALLOWED_USERS", "")
if ALLOWED_USERS_RAW:
    try:
        ALLOWED_USERS = [int(uid.strip()) for uid in ALLOWED_USERS_RAW.split(",") if uid.strip()]
        logger.info(f"Разрешенные ID: {ALLOWED_USERS}")
    except ValueError as e:
        logger.error(f"Ошибка ALLOWED_USERS: {e}")
else:
    logger.info("Доступ открыт для всех (нет ограничений)")

# Хранение ID привязанного пользователя
CONNECTED_USER_ID: Optional[int] = None

# Загрузка привязанного пользователя при старте
if os.path.exists(".connected_user"):
    try:
        with open(".connected_user", "r", encoding="utf-8") as f:
            content = f.read().strip()
            if content:
                CONNECTED_USER_ID = int(content)
                logger.info(f"Привязанный пользователь: {CONNECTED_USER_ID}")
    except Exception as e:
        logger.error(f"Ошибка чтения .connected_user: {e}")

MAX_ITEMS = int(os.getenv("MAX_ITEMS", "30"))

SYMBOLS = ['•', '+', '×', '⁕', '⁜', '※']
# Слова спиннера переведены или сохранены оригинальные
WORDS = ['fetching', 'scrolling', 'clicking', 'searching']

_bot_username = ""

def set_bot_username(username: str):
    global _bot_username
    _bot_username = username

def get_bot_username() -> str:
    return _bot_username

def get_connected_user() -> Optional[int]:
    return CONNECTED_USER_ID

def connect_user(uid: int) -> bool:
    global CONNECTED_USER_ID
    if CONNECTED_USER_ID is not None and CONNECTED_USER_ID != uid:
        return False
    
    CONNECTED_USER_ID = uid
    try:
        with open(".connected_user", "w", encoding="utf-8") as f:
            f.write(str(uid))
        logger.info(f"Бот привязан к UID {uid}")
        return True
    except Exception as e:
        logger.error(f"Ошибка сохранения .connected_user: {e}")
        return False

def allowed(uid: int) -> bool:
    # Если бот уже к кому-то привязан, доступ разрешен только ему
    if CONNECTED_USER_ID is not None:
        is_allowed = (uid == CONNECTED_USER_ID)
        if not is_allowed:
            logger.warning(f"Доступ отклонен для UID {uid} (привязан к {CONNECTED_USER_ID})")
        return is_allowed
        
    # Иначе проверяем ALLOWED_USERS из .env
    is_allowed = not ALLOWED_USERS or uid in ALLOWED_USERS
    if not is_allowed:
        logger.warning(f"Доступ отклонен для UID {uid}")
    return is_allowed
