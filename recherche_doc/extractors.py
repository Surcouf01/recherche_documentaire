"""Extraction du texte des fichiers courants pour classification et tags."""

import zipfile
from pathlib import Path
from typing import Optional


def extract_text(path: str, max_chars: int = 8000) -> str:
    ext = Path(path).suffix.lower()
    try:
        if ext in (".txt", ".md", ".csv", ".log", ".eml", ".html", ".htm", ".json"):
            return _read_text(path, max_chars)
        if ext == ".pdf":
            return _extract_pdf(path, max_chars)
        if ext in (".docx", ".xlsx", ".pptx"):
            return _extract_ooxml(path, max_chars)
        if ext in (".jpg", ".jpeg", ".png", ".tiff", ".bmp", ".gif"):
            return _extract_image_meta(path, max_chars)
        if ext in (".mp4", ".mov", ".avi", ".mkv"):
            return Path(path).stem
    except Exception:
        return ""
    return ""


def _read_text(path: str, max_chars: int) -> str:
    with open(path, "rb") as f:
        data = f.read(max_chars * 4)
    for enc in ("utf-8", "latin-1"):
        try:
            return data.decode(enc)[:max_chars]
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")[:max_chars]


def _extract_pdf(path: str, max_chars: int) -> str:
    try:
        from pypdf import PdfReader
        reader = PdfReader(path)
        chunks = []
        total = 0
        for page in reader.pages:
            t = page.extract_text() or ""
            chunks.append(t)
            total += len(t)
            if total >= max_chars:
                break
        return "\n".join(chunks)[:max_chars]
    except Exception:
        return ""


def _extract_ooxml(path: str, max_chars: int) -> str:
    out = []
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            if name.endswith(".xml"):
                raw = z.read(name).decode("utf-8", errors="ignore")
                import re
                text = " ".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", raw)) or \
                       " ".join(re.findall(r"<t[^>]*>([^<]*)</t>", raw))
                if text.strip():
                    out.append(text)
    return " ".join(out)[:max_chars]


def _extract_image_meta(path: str, max_chars: int) -> str:
    try:
        from PIL import Image
        from PIL.ExifTags import TAGS
        with Image.open(path) as img:
            exif = img.getexif()
            vals = [f"{TAGS.get(k, k)}={v}" for k, v in exif.items()]
            return " ".join(vals)[:max_chars]
    except Exception:
        return ""
