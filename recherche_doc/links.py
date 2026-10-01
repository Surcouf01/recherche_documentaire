"""Création des liens (Windows: hard links/symlink ; POSIX: liens symboliques).

Dans le cadre du Cloud Sync Engine, ces répertoires sont des entrées virtuelles du
provider. En mode simulation locale, on matérialise l'arborescence par liens
symboliques (POSIX) ou durs/symboliques (Windows).

Il n'y a **pas de repli par copie** : si la création du lien échoue (privilège
insuffisant, système de fichiers non supporté), `LinkCreationError` est levée
afin que l'erreur soit signalée à l'utilisateur au lieu d'être masquée par une
copie silencieuse (consommation d'espace NAS et divergence de l'original).
"""

import ctypes
import os
import platform
from pathlib import Path


class LinkCreationError(OSError):
    """Échec de création d'un lien — aucune copie de substitution n'est faite."""


def is_windows() -> bool:
    return platform.system() == "Windows"


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


def is_link(path: Path) -> bool:
    """True si `path` est un lien (symbolique ou dur) plutôt qu'une copie."""
    try:
        if path.is_symlink():
            return True
        if is_windows():
            return _hard_link_count(path) > 1
    except OSError:
        return False
    return False


def _hard_link_count(path: Path) -> int:
    """Nombre de liens durs vers l'inode du fichier (Windows : NumberOfLinks)."""
    if not is_windows():
        try:
            return os.stat(path).st_nlink
        except OSError:
            return 0
    handle = ctypes.windll.kernel32.CreateFileW(
        str(path), 0, 0, None, 3, 128, None)  # OPEN_EXISTING, FILE_FLAG_BACKUP_SEMANTICS
    if handle == -1:
        return 0
    try:
        info = ctypes.create_string_buffer(36 + 104)
        import ctypes.wintypes as wt
        class _BY_HANDLE_FILE_INFORMATION(ctypes.Structure):
            _fields_ = [("dwFileAttributes", wt.DWORD),
                        ("ftCreationTime", wt.FILETIME),
                        ("ftLastAccessTime", wt.FILETIME),
                        ("ftLastWriteTime", wt.FILETIME),
                        ("dwVolumeSerialNumber", wt.DWORD),
                        ("nFileSizeHigh", wt.DWORD),
                        ("nFileSizeLow", wt.DWORD),
                        ("nNumberOfLinks", wt.DWORD),
                        ("nFileIndexHigh", wt.DWORD),
                        ("nFileIndexLow", wt.DWORD)]
        info = _BY_HANDLE_FILE_INFORMATION()
        if not ctypes.windll.kernel32.GetFileInformationByHandle(handle, ctypes.byref(info)):
            return 0
        return int(info.nNumberOfLinks)
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def link_file(source: Path, link_path: Path) -> None:
    """Crée un lien vers `source` nommé `link_path`.

    Windows : hard link, puis symlink si l'utilisateur a le privilège
    `SeCreateSymbolicLinkPrivilege`. POSIX : symlink. En cas d'échec,
    lève LinkCreationError — jamais de copie de substitution.
    """
    if link_path.exists() or link_path.is_symlink():
        return
    last_error: OSError = LinkCreationError("création de lien non tentée")
    if is_windows():
        try:
            os.link(str(source), str(link_path))
            return
        except OSError as e:
            last_error = e
        try:
            os.symlink(str(source), str(link_path), target_is_file=True)
            return
        except OSError as e:
            last_error = e
    else:
        try:
            os.symlink(str(source.resolve()), str(link_path))
            return
        except OSError as e:
            last_error = e
    raise LinkCreationError(
        f"Impossible de créer le lien « {link_path} » vers « {source} » : "
        f"{last_error}. Aucune copie de substitution n'est effectuée ; "
        f"vérifiez les privilèges (SeCreateSymbolicLinkPrivilege / même volume "
        f"pour les liens durs).")


def remove_link(path: Path) -> None:
    try:
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.is_dir():
            path.rmdir()
    except FileNotFoundError:
        pass
