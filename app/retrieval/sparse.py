import hashlib
import math
from collections import Counter

from qdrant_client import models

from app.utils.text import compact_alphanumeric, tokenize

CHARACTER_NGRAM_SIZE = 5
CHARACTER_NGRAM_WEIGHT = 0.35


class LocalSparseEncoder:
    """Deterministic local lexical encoder; Qdrant applies collection-level IDF."""

    @staticmethod
    def _index(token: str) -> int:
        return int.from_bytes(hashlib.blake2b(token.encode(), digest_size=4).digest(), "big")

    def encode(self, text: str) -> models.SparseVector:
        counts = Counter(tokenize(text))
        weighted: dict[int, float] = {}
        for token, count in counts.items():
            index = self._index(f"word:{token}")
            weighted[index] = weighted.get(index, 0.0) + 1.0 + math.log(count)
        # PDF converters sometimes emit `whichindicateswhetherthemobile...` as one token.
        # Character n-grams keep sparse retrieval useful despite those missing spaces. They are
        # namespaced and down-weighted so normal word matches remain the strongest signal.
        compact = compact_alphanumeric(text)
        if len(compact) >= CHARACTER_NGRAM_SIZE:
            grams = {
                compact[offset : offset + CHARACTER_NGRAM_SIZE]
                for offset in range(len(compact) - CHARACTER_NGRAM_SIZE + 1)
            }
            for gram in grams:
                index = self._index(f"char{CHARACTER_NGRAM_SIZE}:{gram}")
                weighted[index] = weighted.get(index, 0.0) + CHARACTER_NGRAM_WEIGHT
        ordered = sorted(weighted.items())
        return models.SparseVector(
            indices=[item[0] for item in ordered],
            values=[item[1] for item in ordered],
        )
