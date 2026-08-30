import hashlib
import math
from collections import Counter

from qdrant_client import models

from app.utils.text import tokenize


class LocalSparseEncoder:
    """Deterministic local lexical encoder; Qdrant applies collection-level IDF."""

    @staticmethod
    def _index(token: str) -> int:
        return int.from_bytes(hashlib.blake2b(token.encode(), digest_size=4).digest(), "big")

    def encode(self, text: str) -> models.SparseVector:
        counts = Counter(tokenize(text))
        weighted: dict[int, float] = {}
        for token, count in counts.items():
            index = self._index(token)
            weighted[index] = weighted.get(index, 0.0) + 1.0 + math.log(count)
        ordered = sorted(weighted.items())
        return models.SparseVector(
            indices=[item[0] for item in ordered],
            values=[item[1] for item in ordered],
        )
