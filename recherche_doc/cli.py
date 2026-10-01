"""CLI : indexation, moteur de synchro, recherche console, agent courriel, .eml."""

import argparse
import sys
from pathlib import Path

from .classifier import DocumentClassifier
from .config import load_mail_config, load_sync_config
from .drive_check import check_documents_access
from .database import DocumentDB
from .pipeline import IndexingPipeline
from .search.engine import SearchEngine


def _build_context(sync_config_path: str = "config.yaml"):
    cfg = load_sync_config(sync_config_path)
    root = Path(cfg.local_root or ".")
    db = DocumentDB(cfg.db_path)
    pipeline = IndexingPipeline(root, db, DocumentClassifier())
    return cfg, db, pipeline


def main(argv=None):
    p = argparse.ArgumentParser(prog="recherche_doc", description="Outil de référencement documentaire")
    sub = p.add_subparsers(dest="cmd", required=True)

    pc = sub.add_parser("check-connection", help="Vérifier l'accès au répertoire Documents (drive monté / NAS joignable)")
    pc.add_argument("config")

    ps = sub.add_parser("index", help="Indexer les fichiers existants du répertoire Documents")
    ps.add_argument("config")

    pw = sub.add_parser("watch", help="Démarrer le moteur de synchro (nouvelles importations)")
    pw.add_argument("config")

    pq = sub.add_parser("search", help="Recherche par catégorie/tags/mot-clé")
    pq.add_argument("config")
    pq.add_argument("--category", "-c")
    pq.add_argument("--tags", "-t", help="tags séparés par des virgules")
    pq.add_argument("--date", "-d", help="YYYYMM")
    pq.add_argument("--keyword", "-k")

    pg = sub.add_parser("gui", help="Interface graphique de recherche")
    pg.add_argument("config")

    pm = sub.add_parser("mail-run", help="Scruter la messagerie et sauvegarder les factures")
    pm.add_argument("config")

    pe = sub.add_parser("import-eml", help="Pipeline d'import depuis un fichier .eml")
    pe.add_argument("config")
    pe.add_argument("eml")

    args = p.parse_args(argv)
    cfg, db, pipeline = _build_context(args.config)

    if args.cmd == "check-connection":
        error = check_documents_access(cfg)
        if error:
            print(f"ERREUR: {error}", file=sys.stderr)
            return 1
        print(f"Accès à « {cfg.documents_dir} » vérifié.")
        return 0

    if args.cmd in ("index", "watch"):
        error = check_documents_access(cfg)
        if error:
            print(f"ERREUR: {error}", file=sys.stderr)
            return 1

    if args.cmd == "index":
        n = pipeline.index_existing()
        print(f"{n} fichier(s) indexé(s).")

    elif args.cmd == "watch":
        from .sync_engine import LocalSyncEngine
        engine = LocalSyncEngine(cfg, pipeline)
        print("Moteur de synchro local démarré (Ctrl+C pour arrêter)...")
        try:
            engine.run()
        except KeyboardInterrupt:
            pass

    elif args.cmd == "search":
        engine = SearchEngine(db)
        tags = [t.strip() for t in args.tags.split(",")] if args.tags else None
        rows = engine.search(category=args.category, tags=tags, date=args.date)
        if args.keyword:
            rows = [r for r in rows if args.keyword.lower() in r["filename"].lower()] or \
                   engine.search_fulltext(args.keyword)
        for r in rows:
            print(f"{r['filename']}\t{r['category']}\t{', '.join(r['tags'])}")
        print(f"({len(rows)} résultat(s))")

    elif args.cmd == "gui":
        from .search.ui import SearchUI
        SearchUI(SearchEngine(db)).launch()

    elif args.cmd == "mail-run":
        from .email_agent import EmailInvoiceAgent
        from .config import load_mail_config
        mail_cfg = load_mail_config(args.config)
        agent = EmailInvoiceAgent(mail_cfg, db, pipeline)
        for path in agent.run():
            print(f"Facture sauvegardée: {path}")

    elif args.cmd == "import-eml":
        from .email_agent import EmailInvoiceAgent
        from .config import load_mail_config
        try:
            mail_cfg = load_mail_config(args.config)
        except Exception:
            mail_cfg = type("MC", (), {"documents_dir": str(cfg.documents_dir),
                                       "imap_url": "", "login": "", "password": "", "last_run": None})()
        agent = EmailInvoiceAgent(mail_cfg, db, pipeline)
        out = agent.process_eml(Path(args.eml))
        print(f"PDF produit: {out}" if out else "Courriel non classé Facture — rien à importer.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
