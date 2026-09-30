"""Moteur de synchro « Cloud Sync Engine API » (CfApi Windows) vers NAS Synology.

Sur Windows, la brique se présente comme un provider Cloud Sync Engine monté sur
une lettre de drive : les fichiers du répertoire « Documents » du NAS apparaissent
sous <Drive>:\\Documents, et toute création/modification de fichier déclenche le
pipeline d'indexation qui peuple <Drive>:\\<Catégorie>\\[<Tag>\\] de liens.

En environnement non-Windows, `LocalSyncEngine` simule le comportement avec un
répertoire racine local (observateur par scrutation).
Sur Windows, `WindowsSyncEngine` délègue au module `windows_provider` (cfapi).
"""

import time
from pathlib import Path
from typing import Callable, Optional

from .config import SyncConfig
from .database import DocumentDB
from .pipeline import IndexingPipeline


class BaseSyncEngine:
    def __init__(self, cfg: SyncConfig, pipeline: IndexingPipeline,
                 on_error: Optional[Callable[[str, Exception], None]] = None):
        self.cfg = cfg
        self.pipeline = pipeline
        self.on_error = on_error or (lambda p, e: None)

    def on_file_created(self, path: Path):
        try:
            return self.pipeline.process_file(path)
        except Exception as e:
            self.on_error(str(path), e)
            return None


class LocalSyncEngine(BaseSyncEngine):
    """Simulation locale : scrute « Documents » et indexe les nouveaux fichiers."""

    POLL_SECONDS = 2.0

    def __init__(self, cfg: SyncConfig, pipeline: IndexingPipeline,
                 on_error: Optional[Callable[[str, Exception], None]] = None):
        super().__init__(cfg, pipeline, on_error)
        self._known = {p.name for p in self.pipeline.documents_dir.rglob("*") if p.is_file()}
        self._stop = False

    def scan_once(self) -> int:
        n = 0
        for p in sorted(self.pipeline.documents_dir.rglob("*")):
            if p.is_file() and p.name not in self._known:
                self._known.add(p.name)
                if self.on_file_created(p):
                    n += 1
        return n

    def run(self):
        while not self._stop:
            self.scan_once()
            time.sleep(self.POLL_SECONDS)

    def stop(self):
        self._stop = True


def build_engine(cfg: SyncConfig, db: DocumentDB, pipeline: IndexingPipeline) -> BaseSyncEngine:
    if LocalSyncEngine is not None and (cfg.local_root or not hasattr(time, "windll")):
        return LocalSyncEngine(cfg, pipeline)
    try:
        from .windows_provider import WindowsSyncEngine
        return WindowsSyncEngine(cfg, pipeline)
    except ImportError:
        return LocalSyncEngine(cfg, pipeline)
