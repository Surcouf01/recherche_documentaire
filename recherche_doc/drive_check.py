"""Vérification de l'accès au répertoire « Documents » (drive monté)."""

from pathlib import Path

from .config import SyncConfig


def check_documents_access(cfg: SyncConfig) -> str | None:
    """Retourne un message d'erreur si « Documents » est inaccessible, sinon None.

    L'outil n'établit pas lui-même la connexion au NAS : il s'appuie sur le
    drive (CfApi ou montage) déjà en place. Un échec se manifeste ici par un
    répertoire « Documents » inaccessible.
    """
    docs = Path(cfg.documents_dir)
    try:
        if docs.is_dir():
            return None
    except OSError:
        pass
    if cfg.local_root:
        return (f"Répertoire « {docs} » inaccessible — vérifiez le champ "
                f"local_root et le montage du NAS.")
    return (f"Drive « {cfg.drive_letter} » non monté ou inaccessible — "
            f"la connexion au NAS n'est probablement pas établie. Vérifiez le "
            f"montage du drive ou le champ drive_letter de config.yaml.")
