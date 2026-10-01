"""Vérification de la connexion au NAS Synology (QuickConnect / SMB).

Détecte et rapporte avec un message clair les trois familles de pannes :
ID QuickConnect invalide, serveur injoignable (connexion refusée / timeout),
identifiants refusés (mauvais login ou mot de passe).
"""

import json
import shutil
import socket
import subprocess
from pathlib import Path
from typing import List, Optional
from urllib import error as urllib_error
from urllib import request as urllib_request

from .config import SyncConfig

QUICKCONNECT_API = "https://cnc.quickconnect.to/v1/get_server_info"
SMB_PORT = 445


class NasConnectionError(Exception):
    """Erreur de connexion au NAS, avec un message exploitable."""


def resolve_quickconnect(qc_id: str, timeout: float = 10.0) -> List[dict]:
    """Résout un ID QuickConnect et retourne la liste des serveurs.

    Lève NasConnectionError si l'ID est inconnu, le service QuickConnect
    est injoignable ou la réponse est invalide.
    """
    payload = json.dumps({"version": 1, "id": qc_id}).encode()
    req = urllib_request.Request(
        QUICKCONNECT_API, data=payload,
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib_request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
    except urllib_error.HTTPError as e:
        raise NasConnectionError(
            f"ID QuickConnect « {qc_id} » rejeté par le service (HTTP {e.code})")
    except (urllib_error.URLError, OSError, ValueError) as e:
        raise NasConnectionError(
            f"Service QuickConnect injoignable : {e}")
    if not isinstance(data, dict) or data.get("error_code"):
        code = data.get("error_code") if isinstance(data, dict) else None
        raise NasConnectionError(
            f"ID QuickConnect « {qc_id} » invalide (code erreur {code})")
    servers = data.get("servers") or []
    if not servers:
        raise NasConnectionError(
            f"Aucun serveur associé à l'ID QuickConnect « {qc_id} »")
    return servers


def _server_hosts(server: dict) -> List[str]:
    hosts = []
    for key in ("fqdn", "hostname"):
        val = (server.get("external") or {}).get(key) or server.get(key)
        if val:
            hosts.append(val)
    ext = (server.get("external") or {}).get("ip")
    if ext:
        hosts.append(ext)
    lan = (server.get("lan") or {}).get("ip")
    if lan:
        hosts.append(lan)
    return hosts


def is_reachable(host: str, port: int = SMB_PORT, timeout: float = 5.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def find_reachable_host(servers: List[dict], timeout: float = 5.0
                        ) -> Optional[str]:
    for server in servers:
        for host in _server_hosts(server):
            if is_reachable(host, SMB_PORT, timeout):
                return host
    return None


def smb_login_check(host: str, login: str, password: str,
                    timeout: float = 10.0) -> Optional[bool]:
    """Vérifie le couple login/mot de passe via smbclient (si installé).

    Retourne True/False selon l'authentification, None si smbclient
    n'est pas disponible (vérification impossible, pas d'erreur).
    """
    smbclient = shutil.which("smbclient")
    if not smbclient:
        return None
    try:
        proc = subprocess.run(
            [smbclient, "-L", host, "-U", f"{login}%{password}", "-m", "SMB3"],
            capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None
    out = (proc.stdout + proc.stderr).decode(errors="replace")
    if "NT_STATUS_LOGON_FAILURE" in out or "NT_STATUS_ACCOUNT_DISABLED" in out \
            or "NT_STATUS_BAD_PASSWORD" in out or "NT_STATUS_ACCESS_DENIED" in out:
        return False
    return proc.returncode == 0


def check_nas_connection(cfg: SyncConfig, timeout: float = 10.0) -> List[str]:
    """Vérifie la connexion au NAS ; retourne la liste des erreurs (vide = OK).

    En mode `local_root` (simulation/locale), vérifie uniquement
    l'accessibilité du répertoire Documents.
    """
    errors: List[str] = []
    if cfg.local_root:
        docs = Path(cfg.local_root) / "Documents"
        if not docs.is_dir():
            errors.append(
                f"Répertoire local « {docs} » inaccessible — "
                f"vérifiez le montage du NAS ou le champ local_root.")
        return errors
    try:
        servers = resolve_quickconnect(cfg.nas_quickconnect_id, timeout)
    except NasConnectionError as e:
        return [str(e)]
    host = find_reachable_host(servers, timeout / 2)
    if host is None:
        errors.append(
            f"NAS injoignable : connexion refusée ou timeout sur tous les "
            f"serveurs de l'ID « {cfg.nas_quickconnect_id} » "
            f"(port SMB {SMB_PORT}).")
        return errors
    auth = smb_login_check(host, cfg.nas_login, cfg.nas_password, timeout)
    if auth is False:
        errors.append(
            f"Authentification refusée par le NAS ({host}) : "
            f"login ou mot de passe incorrect.")
    return errors
