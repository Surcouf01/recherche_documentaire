"""Création des liens (Windows: hard links/dossiers virtuels; POSIX: liens symboliques).

Dans le cadre du Cloud Sync Engine, ces répertoires sont des entrées virtuelles du
provider. En mode simulation locale, on matérialise l'arborescence par liens
symboliques (POSIX) ou durs/copies (Windows sans privilège de lien symbolique).
"""

import ctypes
import os
import platform
import sys
from pathlib import Path
from typing import List, Optional


def is_windows() -> bool:
    return platform.system() == "Windows"


def _ensure_no_symlink_privilege_windows() -> bool:
    try:
        return ctypes.windll.kernel32.IsUserAnAdmin() != 0 or "SeCreateSymbolicLinkPrivilege" in os.environ
    except Exception:
        return False


def make_category_dir(root: Path, category: str) -> Path:
    d = root / category
    d.mkdir(parents=True, exist_ok=True)
    return d


def _writable_links_allowed() -> bool:
    return os.environ.get("DOC_LINKS_WRITABLE", "0") == "1"


def make_tag_dir(category_dir: Path, tag: str) -> Path:
    safe = _sanitize(tag)
    d = category_dir / safe
    d.mkdir(parents=True, exist_ok=True)
    return d


def _sanitize(s: str) -> str:
    return "".join(c for c in s if c not in '\\/:*?"<>|').strip() or "_"


def link_file(source: Path, link_path: Path) -> None:
    """Crée un lien vers `source` nommé `link_path` (symlink POSIX, hard link Windows)."""
    if link_path.exists() or link_path.is_symlink():
        return
    if is_windows():
        try:
            os.link(str(source), str(link_path))
        except OSError:
            try:
                os.symlink(str(source), str(link_path), target_is_file=True)
            except OSError:
                import shutil
                shutil.copy2(str(source), str(link_path))
    else:
        try:
            os.symlink(str(source.resolve()), str(link_path))
        except (PermissionError, OSError):
            import shutil
            shutil.copy2(str(source), str(link_path))


def remove_link(path: Path) -> None:
    try:
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.is_dir():
            path.rmdir()
    except FileNotFoundError:
        pass
