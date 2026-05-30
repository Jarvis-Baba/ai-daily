from dataclasses import dataclass, field
from datetime import datetime, date
from hashlib import sha256


@dataclass
class RawArticle:
    title: str
    link: str
    summary: str
    published: datetime
    source: str


@dataclass
class Article:
    title: str
    link: str
    summary: str
    published: datetime
    source: str
    content: str = ""
    score: int = 0

    @property
    def id(self) -> str:
        return sha256(self.link.encode()).hexdigest()


@dataclass
class BriefItem:
    title: str
    source: str
    score: int
    digest: str
    link: str


@dataclass
class Brief:
    date: date
    items: list[BriefItem]
