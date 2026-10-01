"""Tests de la vérification de connexion NAS (QuickConnect, SMB, identifiants)."""

import unittest
from unittest import mock

from recherche_doc.config import SyncConfig
from recherche_doc.nas_connection import (
    NasConnectionError,
    check_nas_connection,
    find_reachable_host,
    resolve_quickconnect,
    smb_login_check,
)


def _cfg(**overrides):
    values = dict(
        nas_quickconnect_id="monid",
        nas_login="user",
        nas_password="secret",
        nas_documents_dir="/volume1/docs/Documents",
    )
    values.update(overrides)
    return SyncConfig(**values)


def _servers():
    return [{
        "external": {"ip": "203.0.113.10", "fqdn": "example.nas.fr"},
        "lan": {"ip": "192.168.1.10"},
    }]


class TestResolveQuickConnect(unittest.TestCase):
    def test_invalid_id_raises(self):
        with mock.patch("recherche_doc.nas_connection.urllib_request.urlopen") as up:
            up.return_value.__enter__.return_value.read.return_value = \
                b'{"error_code": 1}'
            with self.assertRaises(NasConnectionError):
                resolve_quickconnect("bad-id")

    def test_service_unreachable(self):
        import urllib.error
        with mock.patch("recherche_doc.nas_connection.urllib_request.urlopen",
                        side_effect=urllib.error.URLError("refused")):
            with self.assertRaisesRegex(NasConnectionError, "injoignable"):
                resolve_quickconnect("monid")

    def test_valid_id_returns_servers(self):
        with mock.patch("recherche_doc.nas_connection.urllib_request.urlopen") as up:
            up.return_value.__enter__.return_value.read.return_value = \
                b'{"error_code": 0, "servers": [{"external": {"ip": "1.2.3.4"}}]}'
            servers = resolve_quickconnect("monid")
            self.assertEqual(servers, [{"external": {"ip": "1.2.3.4"}}])


class TestCheckNasConnection(unittest.TestCase):
    def test_local_root_missing_dir(self):
        errors = check_nas_connection(_cfg(local_root="/nonexistent/path"))
        self.assertEqual(len(errors), 1)
        self.assertIn("inaccessible", errors[0])

    def test_local_root_ok(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            import os
            os.makedirs(os.path.join(tmp, "Documents"))
            self.assertEqual(check_nas_connection(_cfg(local_root=tmp)), [])

    def test_invalid_quickconnect_id_reported(self):
        with mock.patch("recherche_doc.nas_connection.resolve_quickconnect",
                        side_effect=NasConnectionError("ID invalide")):
            errors = check_nas_connection(_cfg())
            self.assertEqual(len(errors), 1)
            self.assertIn("ID invalide", errors[0])

    def test_unreachable_host_reported(self):
        with mock.patch("recherche_doc.nas_connection.resolve_quickconnect",
                        return_value=_servers()), \
             mock.patch("recherche_doc.nas_connection.is_reachable",
                        return_value=False):
            errors = check_nas_connection(_cfg())
            self.assertEqual(len(errors), 1)
            self.assertIn("injoignable", errors[0])

    def test_wrong_credentials_reported(self):
        with mock.patch("recherche_doc.nas_connection.resolve_quickconnect",
                        return_value=_servers()), \
             mock.patch("recherche_doc.nas_connection.is_reachable",
                        return_value=True), \
             mock.patch("recherche_doc.nas_connection.smb_login_check",
                        return_value=False):
            errors = check_nas_connection(_cfg())
            self.assertEqual(len(errors), 1)
            self.assertIn("Authentification refusée", errors[0])

    def test_good_credentials_no_errors(self):
        with mock.patch("recherche_doc.nas_connection.resolve_quickconnect",
                        return_value=_servers()), \
             mock.patch("recherche_doc.nas_connection.is_reachable",
                        return_value=True), \
             mock.patch("recherche_doc.nas_connection.smb_login_check",
                        return_value=True):
            self.assertEqual(check_nas_connection(_cfg()), [])


class TestHelpers(unittest.TestCase):
    def test_find_reachable_host(self):
        with mock.patch("recherche_doc.nas_connection.is_reachable",
                        side_effect=[False, True]):
            self.assertEqual(find_reachable_host(_servers()), "203.0.113.10")

    def test_find_reachable_host_none(self):
        with mock.patch("recherche_doc.nas_connection.is_reachable",
                        return_value=False):
            self.assertIsNone(find_reachable_host(_servers()))

    def test_smb_login_check_without_smbclient(self):
        with mock.patch("recherche_doc.nas_connection.shutil.which",
                        return_value=None):
            self.assertIsNone(smb_login_check("1.2.3.4", "u", "p"))


if __name__ == "__main__":
    unittest.main()
