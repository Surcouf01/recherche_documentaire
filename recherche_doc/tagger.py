"""Extraction des tags : personnes (destinataire/émetteur) et date principale."""

import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from dateutil import parser as date_parser

NAME_RE = re.compile(
    r"\b(?:destinataire|destinataire\s*:\s*|pour|adress[ée]e?\s+(?:à|a)|madame|monsieur|mme|m\.)\s*"
    r"([A-ZÉÈÀÂ][A-Za-zÉÈéèàâêÀÂÎîÔôÛûÇç-]{2,})",
    re.IGNORECASE,
)
EMITTER_RE = re.compile(
    r"\b(?:[ée]metteur|[ée]metteur\s*:\s*|exp[ée]diteur|de\s*:\s*|docteur|dr\.?)\s*"
    r"([A-ZÉÈÀÂ][A-Za-zÉÈéèàâêÀÂÎîÔôÛûÇç-]{2,})",
    re.IGNORECASE,
)
EMAIL_NAME_RE = re.compile(r'"?([A-ZÉÈÀÂ][\wéèàâêîôûç-]+(?:\s+[A-ZÉÈÀÂ][\wéèàâêîôûç-]+)+)"?\s*<')
DATE_PATTERNS = [
    (re.compile(r"\b(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\b"), "ymd"),
    (re.compile(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})\b"), "dmy"),
    (re.compile(r"\b(\d{1,2})(?:er)?\s+(janvier|février|fevrier|mars|avril|mai|juin|juillet|août|aout|septembre|octobre|novembre|décembre|decembre)\s+(\d{4})\b", re.IGNORECASE), "text"),
]
MONTHS = {
    "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5,
    "juin": 6, "juillet": 7, "août": 8, "aout": 8, "septembre": 9,
    "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12,
}


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def normalize_name(name: str) -> str:
    return _strip_accents(name).strip().title().replace(" ", "")


def extract_main_date(text: str, fallback: Optional[datetime] = None) -> Optional[datetime]:
    for pat, kind in DATE_PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        try:
            if kind == "ymd":
                return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            if kind == "dmy":
                return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            return datetime(int(m.group(3)), MONTHS[m.group(2).lower()], int(m.group(1)))
        except ValueError:
            continue
    if fallback is not None:
        return fallback
    for pat, kind in DATE_PATTERNS:
        for m in pat.finditer(text):
            try:
                if kind == "ymd":
                    return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                if kind == "dmy":
                    return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))
                return datetime(int(m.group(3)), MONTHS[m.group(2).lower()], int(m.group(1)))
            except ValueError:
                continue
    return None


def extract_tags(text: str, filename: str = "", doc_date: Optional[datetime] = None) -> Dict[str, Optional[str]]:
    """Retourne {recipient, emetteur, date} extraits du texte/du nom de fichier."""
    recipient = None
    emetteur = None
    for m in NAME_RE.finditer(text):
        v = m.group(1)
        if not recipient and _strip_accents(v).lower() not in ("la", "le", "les"):
            recipient = normalize_name(v)
    if not recipient:
        fm = EMAIL_NAME_RE.search(text)
        if fm:
            recipient = normalize_name(fm.group(1))
    for m in EMITTER_RE.finditer(text):
        v = m.group(1)
        if _strip_accents(v).lower() not in ("la", "le", "les"):
            emetteur = normalize_name(v)
            break
    date = extract_main_date(text)
    if date is None:
        date = doc_date
    return {"recipient": recipient, "emetteur": emetteur, "date": date}


def build_filename(category: str, tags: Dict[str, Optional[str]], ext: str, counter: int = 1) -> str:
    """Construit le nom concaténant catégorie + tags, format de date YYYYMM(_Counter)?."""
    parts = [category]
    if tags.get("recipient"):
        parts.append(tags["recipient"])
    if tags.get("emetteur"):
        parts.append(tags["emetteur"])
    if isinstance(tags.get("date"), datetime):
        date_s = tags["date"].strftime("%Y%m")
        parts.append(f"{date_s}_{counter}" if counter > 1 else date_s)
    elif tags.get("date"):
        parts.append(str(tags["date"]))
    return "".join(parts) + (ext if ext.startswith(".") else f".{ext}" if ext else "")


def dedupe_filename(base: str, existing: List[str]) -> str:
    """Assure l'unicité du nom en ajoutant/s'incrémentant le suffixe _N."""
    if base not in existing:
        return base
    stem, dot, ext = base.rpartition(".")
    if not dot:
        stem, ext = base, ""
    m = re.search(r"_(\d+)$", stem)
    n = int(m.group(1)) if m else 1
    while True:
        n += 1
        stem2 = re.sub(r"_\d+$", "", stem) if m else stem
        candidate = f"{stem2}_{n}" + (f".{ext}" if ext else "")
        if candidate not in existing:
            return candidate
