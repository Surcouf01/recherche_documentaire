"""Application GUI de recherche documentaire (point d'entrée PyInstaller).

Lancée par le raccourci du menu Démarrer créé par le MSI, elle recherche
config.yaml à côté de l'exécutable (répertoire d'installation).
"""

import sys
from pathlib import Path


def get_app_dir() -> Path:
    return Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[2]


def find_config() -> Path:
    for candidate in (get_app_dir() / "config.yaml", Path("config.yaml")):
        if candidate.exists():
            return candidate
    return get_app_dir() / "config.example.yaml"


def main(argv=None):
    from recherche_doc.classifier import DocumentClassifier
    from recherche_doc.config import load_sync_config
    from recherche_doc.database import DocumentDB
    from recherche_doc.search.engine import SearchEngine
    from recherche_doc.search.ui import SearchUI

    cfg_path = find_config()
    if not cfg_path.exists():
        print("Aucune configuration trouvée.")
        return 1
    cfg = load_sync_config(str(cfg_path))
    db = DocumentDB(cfg.db_path)
    engine = SearchEngine(db)

    def on_select(filename: str):
        import os
        import subprocess
        rec = db.get_file(filename)
        if rec and cfg.local_root:
            target = Path(cfg.local_root) / "Documents" / filename
            if target.exists():
                if sys.platform == "win32":
                    os.startfile(str(target))  # noqa: S606
                else:
                    subprocess.Popen(["xdg-open", str(target)])

    visited_dir = argv[0] if argv else None
    ui = SearchUI(engine, on_select=on_select)
    if visited_dir:
        ui.set_visited_dir(visited_dir)
    ui.launch()
    return 0


if __name__ == "__main__":
    _args = sys.argv[1:]
    if not getattr(sys, "frozen", False) and _args and _args[0] in ("--register", "--unregister", "--status"):
        from recherche_doc.search.explorer_plugin import main as plugin_main
        sys.exit(plugin_main(_args))
    try:
        if not getattr(sys, "frozen", False):
            from recherche_doc.search.explorer_plugin import is_registered
            if not is_registered():
                from recherche_doc.search.explorer_plugin import register
                register()
    except Exception:
        pass
    sys.exit(main(_args))
