"""Pipeline d'indexation : détection d'un fichier dans « Documents » ->
classification CamemBERT -> extraction des tags -> base de données ->
arborescence de liens (catégorie / tag -> fichier)."""

import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional

from .classifier import DocumentClassifier
from .database import DocumentDB
from .links import link_file, make_category_dir, make_tag_dir
from .tagger import build_filename, dedupe_filename, extract_tags, normalize_name
from .extractors import extract_text


class IndexingPipeline:
    def __init__(self, root: Path, db: DocumentDB, classifier: Optional[DocumentClassifier] = None):
        self.root = Path(root)
        self.documents_dir = self.root / "Documents"
        self.categories_dir = self.root / "Categories"
        self.documents_dir.mkdir(parents=True, exist_ok=True)
        self.categories_dir.mkdir(parents=True, exist_ok=True)
        self.db = db
        self.classifier = classifier or DocumentClassifier()
        self._counters: Dict[str, int] = {}
        self._lock = threading.Lock()

    def process_file(self, path: Path, source_text: Optional[str] = None,
                     tags_override: Optional[Dict] = None) -> dict:
        path = Path(path)
        text = source_text if source_text is not None else extract_text(str(path))
        category, confidence = self.classifier.classify(text or path.stem)
        tags = tags_override if tags_override is not None else extract_tags(text, path.stem)
        tags.setdefault("date", None)
        ext = path.suffix
        counter = self._next_counter(category, tags)
        link_name = build_filename(category, tags, ext, counter)
        existing = [f for f in self.db.list_all() if f["filename"]]
        link_name = dedupe_filename(link_name, [f["filename"] for f in existing])
        tag_values = [v for v in (
            tags.get("recipient"), tags.get("emetteur"), tags.get("date").strftime("%Y%m") if isinstance(tags.get("date"), datetime) else None
        ) if v]
        with self._lock:
            self.db.upsert_file(
                filename=path.name,
                extension=ext,
                category=category,
                tags=tag_values,
                main_date=tags.get("date").strftime("%Y%m") if isinstance(tags.get("date"), datetime) else None,
                recipient=tags.get("recipient"),
                emetteur=tags.get("emetteur"),
                classified_by="camembert" if self.classifier.model_path else "lexical",
            )
            self._create_links(path, category, tag_values, link_name)
        return {"file": path.name, "category": category, "confidence": confidence,
                "tags": tags, "link_name": link_name}

    def _create_links(self, path: Path, category: str, tags: List[str], link_name: str):
        cat_dir = make_category_dir(self.categories_dir, category)
        link_file(path, cat_dir / link_name)
        for tag in tags:
            tag_dir = make_tag_dir(cat_dir, str(tag))
            link_file(path, tag_dir / link_name)

    def _next_counter(self, category: str, tags: Dict) -> int:
        key = f"{category}::{tags.get('recipient') or ''}::{tags.get('date').strftime('%Y%m') if isinstance(tags.get('date'), datetime) else ''}"
        self._counters[key] = self._counters.get(key, 0) + 1
        return self._counters[key]

    def index_existing(self, progress: Optional[Callable[[int], None]] = None) -> int:
        count = 0
        for f in sorted(self.documents_dir.rglob("*")):
            if f.is_file() and not f.is_symlink():
                self.process_file(f)
                count += 1
                if progress:
                    progress(count)
        return count

    def remove_file(self, filename: str) -> bool:
        rec = self.db.get_file(filename)
        if not rec:
            return False
        self.db.delete_file(filename)
        cat_dir = self.categories_dir / rec["category"]
        for entry in list(cat_dir.rglob("*")):
            try:
                if entry.is_symlink() and str(entry.resolve()) == str((self.documents_dir / filename).resolve()):
                    entry.unlink()
            except OSError:
                pass
        return True
