"""Tests du plugin explorateur (logique d'enregistrement, mock winreg)."""

import sys
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _make_fake_winreg(store):
    fake = types.ModuleType("winreg")

    class Key:
        def __init__(self, path):
            self.path = path
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    fake.HKEY_CURRENT_USER = "HKCU"
    fake.KEY_SET_VALUE = 1
    fake.REG_SZ = 1
    fake.Key = Key

    def CreateKeyEx(root, path, _r, _access):
        store.setdefault(path, {})
        return Key(path)

    def SetValueEx(key, name, _t, _d, value):
        store[key.path][name] = value

    def OpenKey(root, path):
        if path not in store:
            raise OSError("not found")
        return Key(path)

    def QueryValueEx(key, name):
        if name not in store[key.path]:
            raise OSError("missing")
        return (store[key.path][name], 1)

    def DeleteKey(root, path):
        if path not in store:
            raise FileNotFoundError(path)
        del store[path]

    fake.CreateKeyEx = CreateKeyEx
    fake.SetValueEx = SetValueEx
    fake.OpenKey = OpenKey
    fake.QueryValueEx = QueryValueEx
    fake.DeleteKey = DeleteKey
    return fake


class TestExplorerPlugin(unittest.TestCase):
    def setUp(self):
        self.store = {}
        self._orig = sys.modules.get("winreg")
        sys.modules["winreg"] = _make_fake_winreg(self.store)
        from recherche_doc.search import explorer_plugin as ep
        self.ep = ep

    def tearDown(self):
        if self._orig is not None:
            sys.modules["winreg"] = self._orig
        else:
            sys.modules.pop("winreg", None)

    def test_register_frozen_exe(self):
        cmd = self.ep.register("C:\\Program Files\\RD\\RechercheDocumentaireSearch.exe")
        self.assertEqual(
            cmd, '"C:\\Program Files\\RD\\RechercheDocumentaireSearch.exe" "%V"')
        key = "Software\\Classes\\Drive\\shell\\RechercheDocumentaire"
        self.assertEqual(self.store[key][None], "Recherche Documentaire...")
        self.assertIn("command", self.store)

    def test_register_dev_mode_uses_python_m(self):
        cmd = self.ep.register(None) if not getattr(sys, "frozen", False) else None
        if cmd is not None:
            self.assertIn("-m recherche_doc.search.explorer_hook", cmd)

    def test_unregister(self):
        self.ep.register("C:\\x\\app.exe")
        self.assertTrue(self.ep.unregister())
        self.assertFalse(self.ep.is_registered())

    def test_is_registered_false_initially(self):
        self.assertFalse(self.ep.is_registered())


if __name__ == "__main__":
    unittest.main()
