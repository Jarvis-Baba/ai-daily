from dataclasses import dataclass
from enum import Enum

from src.models.article import Article


class Bucket(str, Enum):
    ALPHA = "ALPHA"
    BETA = "BETA"
    GAMMA = "GAMMA"


@dataclass
class ScoredArticle:
    """An Article with 3-dimensional scoring and a bucket label.

    Wraps an existing Article — does not mutate it.
    total_score is derived via the additive formula: 0.5×I + 0.3×N + 0.2×A
    """

    article: Article
    impact: int
    novelty: int
    actionability: int
    bucket: Bucket
    theme_id: str | None = None
    theme_confidence: float = 0.0
    trajectory: str = "NEW"

    @property
    def total_score(self) -> float:
        return 0.5 * self.impact + 0.3 * self.novelty + 0.2 * self.actionability
