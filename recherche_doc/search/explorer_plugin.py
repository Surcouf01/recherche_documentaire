r"""Plugin de l'explorateur Windows — enregistrement au premier lancement.

Mécanisme retenu : « command shell » (verbe) enregistré sous
``HKCU\Software\Classes\Drive\shell\RechercheDocumentaire``. L'explorateur
Windows affiche alors la commande « Recherche Documentaire... » dans le menu
contextuel de tout lecteur — y compris le drive sync root monté par le
provider CfApi. Sélectionner la commande lance l'exécutable de recherche
figé par PyInstaller (pas de dépendance à un Python système).

Pourquoi HKCU et une clé modifiable par l'utilisateur : pas d'élévation
requise, installation per-user propre, suppression fiable à la
désinstallation (clé entière recréée par le MSI, voir WXS).

L'argument ``%V`` passe le dossier courant de l'explorateur à l'exécutable,
ce qui permet à la GUI de pré-filtrer sur le drive visité.
"""

import argparse
import sys
from pathlib import Path

REG_KEY = r"Software\Classes\Drive\shell\RechercheDocumentaire"
MENU_LABEL = "Recherche Documentaire..."
ICON_HINT = "RechercheDocumentaireSearch.exe,0"


def get_gui_exe() -> Path:
    """Exécutable de recherche : exe figé sinon python -m (développement)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable)
    return Path(sys.executable)


def build_command(gui_exe: Path, frozen: bool) -> str:
    """Commande registre : exe figé "+ dossier visité (%V), ou python -m en développement."""
    if frozen:
        return f'"{gui_exe}" "%V"'
    return f'"{gui_exe}" -m recherche_doc.search.explorer_hook "%V"'


def register(exe_path: str = None) -> str:
    """Enregistre le verbe pour l'utilisateur courant. Retourne la commande."""
    import winreg

    gui_exe = Path(exe_path) if exe_path else get_gui_exe()
    frozen = bool(exe_path) or getattr(sys, "frozen", False)
    command = build_command(gui_exe, frozen)
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, REG_KEY, 0,
                            winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, None, 0, winreg.REG_SZ, MENU_LABEL)
        winreg.SetValueEx(key, "Icon", 0, winreg.REG_SZ,
                          str(gui_exe.parent / ICON_HINT.split(",")[0]) + ",0")
        with winreg.CreateKeyEx(key, "command", 0, winreg.KEY_SET_VALUE) as cmd:
            winreg.SetValueEx(cmd, None, 0, winreg.REG_SZ, command)
    return command


def unregister() -> bool:
    """Supprime le verbe. Retourne True si une clé a été supprimée."""
    import winreg

    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, REG_KEY + r"\command")
    except FileNotFoundError:
        pass
    except OSError:
        return False
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, REG_KEY)
    except FileNotFoundError:
        return False
    return True


def is_registered() -> bool:
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY) as key:
            winreg.QueryValueEx(key, None)
        return True
    except OSError:
        return False


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="explorer_plugin",
        description="Enregistre/supprime la commande « Recherche Documentaire » de l'explorateur")
    p.add_argument("--register", metavar="EXE",
                   help="Enregistre le verbe pour lancer EXE (défaut : exécutable courant)")
    p.add_argument("--unregister", action="store_true",
                   help="Supprime le verbe de l'explorateur")
    p.add_argument("--status", action="store_true",
                   help="Affiche l'état d'enregistrement")
    args = p.parse_args(argv)

    if args.register is not None:
        cmd = register(args.register if args.register != "" else None)
        print(f"Commande enregistrée : {cmd}")
        return 0
    if args.unregister:
        print("Supprimé." if unregister() else "Non enregistré.")
        return 0
    if args.status:
        print("Enregistré." if is_registered() else "Non enregistré.")
        return 0
    p.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
