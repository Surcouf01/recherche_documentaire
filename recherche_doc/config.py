"""Chargement de la configuration YAML (briques plugin sync et agent courriel)."""

import os
from dataclasses import dataclass, field
from typing import List, Optional

import yaml


@dataclass
class SyncConfig:
    drive_letter: str = "R:"
    db_dir: Optional[str] = None
    local_root: Optional[str] = None

    @property
    def documents_dir(self) -> str:
        if self.local_root:
            return os.path.join(self.local_root, "Documents")
        return f"{self.drive_letter}\\Documents"

    @property
    def db_path(self) -> str:
        base = self.db_dir or os.path.join(
            os.environ.get("APPDATA", os.path.expanduser("~/.local/share")),
            "RechercheDocumentaire",
        )
        return os.path.join(base, "index.db")


@dataclass
class MailConfig:
    imap_url: str
    login: str
    password: str
    documents_dir: str
    last_run: Optional[str] = None


@dataclass
class AppConfig:
    sync: SyncConfig
    mail: Optional[MailConfig] = field(default=None)


def load_sync_config(path: str) -> SyncConfig:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)["sync"]
    return SyncConfig(
        drive_letter=data.get("drive_letter", "R:"),
        db_dir=data.get("db_dir"),
        local_root=data.get("local_root"),
    )


def load_mail_config(path: str) -> MailConfig:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)["mail"]
    return MailConfig(
        imap_url=data["imap_url"],
        login=data["login"],
        password=data["password"],
        documents_dir=data["documents_dir"],
        last_run=data.get("last_run"),
    )
