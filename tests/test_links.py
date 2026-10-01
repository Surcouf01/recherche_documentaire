"""Tests de la création de liens — pas de repli par copie."""

import tempfile
import unittest
from pathlib import Path

from recherche_doc.links import LinkCreationError, is_link, link_file


class TestLinkFile(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.source = Path(self.tmp) / "source.txt"
        self.source.write_text("contenu", encoding="utf-8")

    def test_symlink_created(self):
        link = Path(self.tmp) / "lien.txt"
        link_file(self.source, link)
        self.assertTrue(link.is_symlink())
        self.assertEqual(link.read_text(encoding="utf-8"), "contenu")
        self.assertTrue(is_link(link))

    def test_source_is_not_link(self):
        self.assertFalse(is_link(self.source))

    def test_idempotent_existing_link(self):
        link = Path(self.tmp) / "lien.txt"
        link_file(self.source, link)
        link_file(self.source, link)  # ne doit ni lever ni dupliquer
        self.assertTrue(link.exists())

    def test_failure_raises_no_copy(self):
        # cible dans un répertoire inexistant -> échec de symlink
        link = Path(self.tmp) / "inexistant" / "lien.txt"
        with self.assertRaises(LinkCreationError):
            link_file(self.source, link)
        self.assertFalse(link.exists())


if __name__ == "__main__":
    unittest.main()
