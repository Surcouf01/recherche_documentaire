"""Point d'entrée applicatif Windows pour l'installeur MSI.

Installe/surveille : enregistre le sync root Cloud Sync Engine, démarre le
moteur de synchro et l'agent courriel selon la configuration.
"""

import argparse
import sys
from pathlib import Path


def get_app_dir() -> Path:
    return Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="RechercheDocumentaire",
        description="Outil de référencement documentaire — service de synchro et agent courriel",
    )
    p.add_argument(
        "--config",
        default=str(get_app_dir() / "config.yaml"),
        help="Chemin du fichier de configuration YAML",
    )
    p.add_argument(
        "--mode",
        choices=["sync", "mail", "all"],
        default="all",
        help="sync: moteur de synchro ; mail: agent courriel ; all: les deux",
    )
    p.add_argument("--scan-once", action="store_true",
                   help="Une seule scrutation puis arrêt (diagnostic)")
    args = p.parse_args(argv)

    from .classifier import DocumentClassifier
    from .config import load_sync_config
    from .database import DocumentDB
    from .pipeline import IndexingPipeline

    cfg = load_sync_config(args.config)
    root = Path(cfg.local_root or f"{cfg.drive_letter}\\")
    db = DocumentDB(cfg.db_path)
    pipeline = IndexingPipeline(root, db, DocumentClassifier())

    if args.mode in ("sync", "all"):
        from .sync_engine import build_engine
        engine = build_engine(cfg, db, pipeline)
        if args.scan_once:
            print(f"{engine.scan_once()} nouveau(x) fichier(s) indexé(s).")
            return 0
        print("Moteur de synchro démarré. Ctrl+C pour arrêter.")
        try:
            engine.run()
        except KeyboardInterrupt:
            return 0

    if args.mode in ("mail", "all"):
        from .config import load_mail_config
        from .email_agent import EmailInvoiceAgent
        try:
            mail_cfg = load_mail_config(args.config)
        except Exception:
            print("Section mail absente de la configuration — agent courriel désactivé.")
            return 0
        agent = EmailInvoiceAgent(mail_cfg, db, pipeline)
        for saved in agent.run():
            print(f"Facture sauvegardée: {saved}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
