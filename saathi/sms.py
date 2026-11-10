"""SMS sending. The prototype only records messages in an outbox table (shown in the console).

To go live, implement `send` for an Indian SMS gateway with a DLT-registered template
(TRAI rules require registered sender IDs and templates for SMS in India).
"""
from __future__ import annotations

from typing import Optional

from .db import DB


class OutboxSMS:
    name = "outbox (not sent)"

    def __init__(self, db: DB):
        self.db = db

    def send(self, to_number: Optional[str], body: str, case_id: Optional[str] = None) -> str:
        status = "recorded" if to_number else "no-number"
        self.db.outbox(to_number or "", body, self.name, status, case_id)
        return status
