import os
import logging

# Настройка логирования в консоль
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("bot.config")

# Загрузка переменных окружения из .env
if os.path.exists(".env"):
    logger.info("Загрузка переменных окружения из .env")
    with open(".env", "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                parts = line.split("=", 1)
                if len(parts) == 2:
                    os.environ[parts[0].strip()] = parts[1].strip()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
if not BOT_TOKEN:
    logger.error("BOT_TOKEN отсутствует в файле .env!")
    raise ValueError("BOT_TOKEN не установлен в .env или переменных окружения!")


# Whitelist пользователей
ALLOWED_USERS: list[int] = []
ALLOWED_USERS_RAW = os.getenv("ALLOWED_USERS", "")
if ALLOWED_USERS_RAW:
    try:
        ALLOWED_USERS = [int(uid.strip()) for uid in ALLOWED_USERS_RAW.split(",") if uid.strip()]
        logger.info(f"Загружен белый список пользователей ({len(ALLOWED_USERS)} ID): {ALLOWED_USERS}")
    except ValueError as e:
        logger.error(f"Ошибка при парсинге ALLOWED_USERS: {e}")
else:
    logger.info("Белый список пользователей пуст (доступ разрешен всем)")

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

def allowed(uid: int) -> bool:
    is_allowed = not ALLOWED_USERS or uid in ALLOWED_USERS
    if not is_allowed:
        logger.warning(f"Доступ заблокирован для пользователя: {uid} (не входит в список разрешённых)")
    return is_allowed
