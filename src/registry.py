import hashlib
from typing import Optional

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
