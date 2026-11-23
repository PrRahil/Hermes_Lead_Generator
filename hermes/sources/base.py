from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class RawSignal:
    """A public posting / job / RFP signal before it becomes a CRM listing."""

    platform: str
    title: str
    snippet: str
    url: str = ""
    company_name: str = ""
    company_domain: str = ""
    industry: str = ""
    employee_count: Optional[int] = None
    revenue_usd: Optional[int] = None
    location: str = ""
    contact_name: str = ""
    contact_title: str = ""
    contact_email: str = ""
    contact_phone: str = ""
    requirement: str = ""
    tags: List[str] = field(default_factory=list)
    acquisition_source: str = ""
    posted_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    meta: dict = field(default_factory=dict)

    def text_blob(self) -> str:
        return " ".join(
            filter(
                None,
                [
                    self.title,
                    self.snippet,
                    self.requirement,
                    self.company_name,
                    self.industry,
                    self.contact_title,
                    " ".join(self.tags),
                ],
            )
        )


class SourceConnector:
    name: str = "base"

    def fetch(self, query: str = "", limit: int = 25) -> List[RawSignal]:
        raise NotImplementedError
