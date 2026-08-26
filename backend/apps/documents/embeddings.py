"""Embedding helpers — OpenAI or deterministic mock vectors for local/demo."""
from __future__ import annotations

import hashlib
import math
import struct

from django.conf import settings


def _mock_embedding(text: str, dims: int | None = None) -> list[float]:
    dims = dims or settings.EMBEDDING_DIMENSIONS
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    values: list[float] = []
    seed = digest
    while len(values) < dims:
        seed = hashlib.sha256(seed).digest()
        for i in range(0, len(seed), 4):
            if len(values) >= dims:
                break
            n = struct.unpack(">I", seed[i : i + 4])[0]
            values.append((n / 0xFFFFFFFF) * 2 - 1)
    # L2 normalize
    norm = math.sqrt(sum(v * v for v in values)) or 1.0
    return [v / norm for v in values]


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    if settings.USE_MOCK_EMBEDDINGS:
        return [_mock_embedding(t) for t in texts]

    from openai import OpenAI

    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    response = client.embeddings.create(
        model=settings.OPENAI_EMBEDDING_MODEL,
        input=texts,
    )
    # Ensure order
    by_index = {item.index: item.embedding for item in response.data}
    return [by_index[i] for i in range(len(texts))]


def embed_query(text: str) -> list[float]:
    return embed_texts([text])[0]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)
