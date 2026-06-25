import os
import platform
from pathlib import Path
from src.config import MAX_ITEMS

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
