"""Analyse de fichiers .eml / courriels IMAP : corps, pièces jointes, dates, personnes."""

import email
import os
import re
import tempfile
from dataclasses import dataclass, field
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from pathlib import Path
from typing import List, Optional, Tuple


@dataclass
class ParsedEmail:
    subject: str
    from_addr: str
    from_name: str
    to_addrs: List[str]
    date: Optional[str]
    body_text: str = ""
    body_html: Optional[str] = None
    attachments: List[Tuple[str, bytes]] = field(default_factory=list)

    @property
    def full_text(self) -> str:
        return f"{self.subject}\n{self.from_name} {self.from_addr}\n{self.body_text}"


def parse_eml(path_or_bytes) -> ParsedEmail:
    if isinstance(path_or_bytes, (str, Path)):
        with open(path_or_bytes, "rb") as f:
            raw = f.read()
    else:
        raw = path_or_bytes
    msg: EmailMessage = BytesParser(policy=policy.default).parsebytes(raw)
    subject = str(msg.get("Subject", ""))
    from_ = email.utils.parseaddr(str(msg.get("From", "")))
    tos = [email.utils.parseaddr(str(t)) for t in msg.get_all("To", []) + msg.get_all("Cc", [])]
    date_hdr = msg.get("Date")
    body_text = ""
    body_html = None
    attachments = []
    for part in msg.walk():
        ctype = part.get_content_type()
        disp = str(part.get("Content-Disposition", ""))
        filename = part.get_filename()
        if filename:
            attachments.append((filename, part.get_payload(decode=True) or b""))
        elif ctype == "text/plain" and "attachment" not in disp:
            body_text += part.get_content()
        elif ctype == "text/html" and "attachment" not in disp and body_html is None:
            body_html = part.get_content()
    from_name = from_[0] or from_[1].split("@")[0].replace(".", " ").title()
    return ParsedEmail(
        subject=subject,
        from_addr=from_[1],
        from_name=from_name,
        to_addrs=[t[1] for t in tos if t[1]],
        date=date_hdr,
        body_text=body_text,
        body_html=body_html,
        attachments=attachments,
    )
