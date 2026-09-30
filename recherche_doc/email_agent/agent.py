"""Agent IA de sauvegarde de factures reçues sur la messagerie personnelle.

- Scrute la messagerie (IMAP) depuis la date de dernier run,
- classe les courriels (CamemBERT / repli lexical) et retient ceux de
  catégorie « Facture » (cohérence avec le plugin Cloud Sync Engine :
  même classifieur, même taxonomie),
- convertit chaque courriel facture en PDF (aspect original conservé,
  pièces jointes aplaties en pages supplémentaires),
- sauvegarde le PDF dans le répertoire « Documents » (déclenche ainsi le
  pipeline d'import du sync engine),
- peut reproduire le pipeline d'import à partir d'un fichier .eml local,
- persiste la date de dernier run.
"""

import email.utils
import imaplib
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

from ..classifier import DocumentClassifier
from ..config import MailConfig
from ..database import DocumentDB
from ..pipeline import IndexingPipeline
from ..tagger import extract_tags, normalize_name
from .eml import parse_eml
from .pdf import email_to_pdf

INVOICE_HINTS = ("facture", "invoice", "montant", "paiement", "tva", "total ht", "total ttc", "réglée")


class EmailInvoiceAgent:
    def __init__(self, cfg: MailConfig, db: DocumentDB, pipeline: IndexingPipeline,
                 classifier: Optional[DocumentClassifier] = None):
        self.cfg = cfg
        self.db = db
        self.pipeline = pipeline
        self.classifier = classifier or DocumentClassifier()

    def _is_invoice(self, text: str) -> bool:
        category, _conf = self.classifier.classify(text)
        return category == "Facture"

    def process_eml(self, path: Path) -> Optional[str]:
        """Reproduit le pipeline d'import à partir d'un fichier .eml du filesystem."""
        parsed = parse_eml(path)
        text = parsed.full_text
        if not self._is_invoice(text):
            return None
        tags = extract_tags(text)
        emetteur = normalize_name(parsed.from_name or parsed.from_addr.split("@")[0])
        tags["emetteur"] = emetteur
        if not tags.get("recipient") and parsed.to_addrs:
            tags["recipient"] = normalize_name(parsed.to_addrs[0].split("@")[0].replace(".", " "))
        try:
            dt = email.utils.parsedate_to_datetime(parsed.date) if parsed.date else None
        except (TypeError, ValueError):
            dt = None
        if dt is not None and dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        tags["date"] = tags.get("date") or dt
        out_dir = Path(self.cfg.documents_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        name = f"Facture_{emetteur}_{tags['date'].strftime('%Y%m') if tags.get('date') else 's.d.'}.pdf"
        out = out_dir / name
        i = 1
        while out.exists():
            out = out_dir / name.replace(".pdf", f"_{i}.pdf")
            i += 1
        email_to_pdf(parsed, str(out))
        self.pipeline.process_file(out, source_text=text, tags_override=tags)
        return str(out)

    def run(self) -> List[str]:
        """Scrute la messagerie IMAP depuis la date de dernier run."""
        saved: List[str] = []
        since = self.cfg.last_run or self.db.get_setting("mail_last_run")
        if not since:
            since = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%d-%b-%Y")
        with imaplib.IMAP4_SSL(self.cfg.imap_url) as imap:
            imap.login(self.cfg.login, self.cfg.password)
            imap.select("INBOX")
            typ, data = imap.search(None, f'(SINCE "{since}")')
            if typ != "OK":
                return []
            for num in data[0].split():
                typ, msg_data = imap.fetch(num, "(RFC822)")
                if typ != "OK":
                    continue
                raw = msg_data[0][1]
                with open(os.path.join(self._tmpdir(), f"{num.decode()}.eml"), "wb") as f:
                    f.write(raw)
                parsed = parse_eml(raw)
                if self._is_invoice(parsed.full_text):
                    out = self._save_invoice(parsed)
                    if out:
                        saved.append(out)
        now = datetime.now(timezone.utc).strftime("%d-%b-%Y")
        self.db.set_setting("mail_last_run", now)
        self.cfg.last_run = now
        return saved


    def _extract_tags(self, parsed) -> dict:
        text = parsed.full_text
        tags = extract_tags(text)
        tags["emetteur"] = normalize_name(parsed.from_name or parsed.from_addr.split("@")[0])
        if not tags.get("recipient") and parsed.to_addrs:
            tags["recipient"] = normalize_name(parsed.to_addrs[0].split("@")[0].replace(".", " "))
        try:
            dt = email.utils.parsedate_to_datetime(parsed.date) if parsed.date else None
        except (TypeError, ValueError):
            dt = None
        if dt is not None and dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        tags["date"] = tags.get("date") or dt
        return tags

    def _tmpdir(self) -> str:
        d = os.path.join(tempfile.gettempdir(), "recherche_doc_mail")
        os.makedirs(d, exist_ok=True)
        return d

    def _save_invoice(self, parsed) -> Optional[str]:
        out_dir = Path(self.cfg.documents_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        safe = "".join(c for c in parsed.subject if c not in '\\/:*?"<>|')[:80] or "Facture"
        out = out_dir / f"Facture_{safe}.pdf"
        email_to_pdf(parsed, str(out))
        self.pipeline.process_file(out, source_text=parsed.full_text,
                                   tags_override=self._extract_tags(parsed))
        return str(out)
