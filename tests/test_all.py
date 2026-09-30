import json
import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from recherche_doc import CATEGORIES
from recherche_doc.classifier import DocumentClassifier
from recherche_doc.database import DocumentDB
from recherche_doc.pipeline import IndexingPipeline
from recherche_doc.tagger import build_filename, dedupe_filename, extract_tags
from recherche_doc.search.engine import SearchEngine
from recherche_doc.sync_engine import LocalSyncEngine


INVOICE_TEXT = (
    "FACTURE\nFacture n° 2024-0123\nDestinataire: Véronique Dupont\n"
    "Émetteur: Clinique Barcelona IVF\nDate: 15/03/2024\n"
    "Montant total TTC : 1 250,00 €\nTVA 21% incluse\n"
)
LAB_TEXT = (
    "Résultats d'analyse de laboratoire\nMadame Véronique Dupont\n"
    "Docteur Martin\nLe 2024-05-02\nGlucose 0.95 g/l\n"
)


class TestClassifier(unittest.TestCase):
    def setUp(self):
        self.clf = DocumentClassifier()

    def test_invoice(self):
        cat, _ = self.clf.classify(INVOICE_TEXT)
        self.assertEqual(cat, "Facture")

    def test_lab_result(self):
        cat, _ = self.clf.classify(LAB_TEXT)
        self.assertEqual(cat, "Resultat")

    def test_default_autre(self):
        cat, _ = self.clf.classify("Lorem ipsum dolor sit amet consectetur")
        self.assertEqual(cat, "Autre")

    def test_categories_list(self):
        for c in CATEGORIES:
            self.assertTrue(c and isinstance(c, str))


class TestTagger(unittest.TestCase):
    def test_extract(self):
        tags = extract_tags(INVOICE_TEXT)
        self.assertEqual(tags["recipient"], "Veronique")
        self.assertEqual(tags["emetteur"], "Clinique")
        self.assertEqual(tags["date"], datetime(2024, 3, 15))

    def test_build_filename(self):
        tags = {"recipient": "Veronique", "emetteur": None, "date": datetime(2024, 3, 15)}
        name = build_filename("Facture", tags, ".pdf")
        self.assertEqual(name, "FactureVeronique202403.pdf")

    def test_build_filename_counter(self):
        tags = {"recipient": None, "emetteur": None, "date": datetime(2024, 3, 15)}
        self.assertEqual(build_filename("Facture", tags, ".pdf", 2), "Facture202403_2.pdf")

    def test_dedupe(self):
        self.assertEqual(dedupe_filename("Facture202403.pdf", ["Facture202403.pdf"]), "Facture202403_2.pdf")


class TestPipelineAndSearch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = Path(self.tmp)
        self.db = DocumentDB(str(self.root / ".docsearch" / "index.db"))
        self.pipeline = IndexingPipeline(self.root, self.db, DocumentClassifier())
        (self.pipeline.documents_dir / "facture_veronique.txt").write_text(INVOICE_TEXT, encoding="utf-8")
        (self.pipeline.documents_dir / "resultat_lab.txt").write_text(LAB_TEXT, encoding="utf-8")

    def test_db_hidden(self):
        self.assertTrue(Path(self.db.path).parent.name.startswith("."))

    def test_index_existing(self):
        n = self.pipeline.index_existing()
        self.assertEqual(n, 2)

    def test_links_created(self):
        self.pipeline.index_existing()
        fact_dir = self.pipeline.categories_dir / "Facture"
        self.assertTrue(fact_dir.exists())
        links = [p for p in fact_dir.rglob("*") if p.is_file()]
        self.assertTrue(len(links) >= 1)
        tag_dirs = [d for d in fact_dir.iterdir() if d.is_dir()]
        self.assertTrue(all(p.is_symlink() for p in links))

    def test_search_by_category(self):
        self.pipeline.index_existing()
        engine = SearchEngine(self.db)
        rows = engine.search(category="Facture")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["category"], "Facture")

    def test_search_by_tag(self):
        self.pipeline.index_existing()
        engine = SearchEngine(self.db)
        rows = engine.search(tags=["Veronique"], category="Facture")
        self.assertEqual(len(rows), 1)

    def test_search_date(self):
        self.pipeline.index_existing()
        engine = SearchEngine(self.db)
        self.assertEqual(len(engine.search(date="202403")), 1)
        self.assertEqual(len(engine.search(date="202405")), 1)

    def test_sync_engine_detects_new_file(self):
        engine = LocalSyncEngine.__new__(LocalSyncEngine)
        engine.cfg = None
        engine.pipeline = self.pipeline
        engine.on_error = lambda p, e: None
        engine._known = {p.name for p in self.pipeline.documents_dir.rglob("*") if p.is_file()}
        engine._stop = False
        engine.POLL_SECONDS = 0.1
        self.assertEqual(engine.scan_once(), 0)
        (self.pipeline.documents_dir / "nouvelle_facture.txt").write_text(INVOICE_TEXT, encoding="utf-8")
        self.assertEqual(engine.scan_once(), 1)
        self.assertEqual(engine.scan_once(), 0)


if __name__ == "__main__":
    unittest.main()
