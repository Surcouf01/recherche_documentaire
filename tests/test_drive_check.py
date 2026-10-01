"""Tests du contrôle d'accès au répertoire Documents (drive monté)."""

import os
import tempfile
import unittest

from recherche_doc.config import SyncConfig
from recherche_doc.drive_check import check_documents_access


class TestCheckDocumentsAccess(unittest.TestCase):
    def test_local_root_missing(self):
        cfg = SyncConfig(local_root="/nonexistent/path")
        error = check_documents_access(cfg)
        self.assertIsNotNone(error)
        self.assertIn("local_root", error)

    def test_local_root_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "Documents"))
            cfg = SyncConfig(local_root=tmp)
            self.assertIsNone(check_documents_access(cfg))

    def test_drive_message(self):
        cfg = SyncConfig(drive_letter="R:")
        error = check_documents_access(cfg)
        self.assertIsNotNone(error)
        self.assertIn("R:", error)
        self.assertIn("non monté", error)


if __name__ == "__main__":
    unittest.main()
