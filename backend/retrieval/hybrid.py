"""BM25 + 벡터 하이브리드 검색 (v3). 두 순위를 RRF로 결합한다."""
import logging
import re
from functools import lru_cache
from typing import Any

from rank_bm25 import BM25Okapi

from retrieval.vector import (
    allowed_place_ids,
    build_where,
    chunk_allowed,
    get_collection,
    search_chunks,
)

logger = logging.getLogger(__name__)

RRF_K = 60  # RRF 상수: 순위 차이의 영향을 완만하게 만든다
POOL = 50  # 각 검색에서 가져와 결합할 후보 수


def tokenize(text: str) -> list[str]:
    """한글 형태소 분석기 없이 쓸 수 있도록 어절 + 문자 바이그램으로 토큰화한다."""
    tokens: list[str] = []
    for word in re.findall(r"[0-9A-Za-z가-힣]+", text.lower()):
        tokens.append(word)
        tokens.extend(word[i : i + 2] for i in range(len(word) - 1))
    return tokens


@lru_cache(maxsize=1)
def _bm25_index() -> tuple[BM25Okapi, list[dict[str, Any]]]:
    """Chroma에 저장된 청크로 BM25 인덱스를 만든다 (프로세스당 1회)."""
    got = get_collection().get(include=["documents", "metadatas"])
    docs = [
        {"id": i, "text": d, "meta": m}
        for i, d, m in zip(got["ids"], got["documents"], got["metadatas"])
    ]
    return BM25Okapi([tokenize(d["text"]) for d in docs]), docs


def bm25_search(
    query: str, n: int, filters: dict[str, Any] | None = None, allowed: list[str] | None = None
) -> list[dict[str, Any]]:
    """BM25 점수순으로 청크를 반환한다. 필터를 통과한 청크만 대상으로 한다."""
    bm25, docs = _bm25_index()
    scores = bm25.get_scores(tokenize(query))
    order = sorted(range(len(docs)), key=lambda i: scores[i], reverse=True)
    hits = [
        {**docs[i], "score": float(scores[i])}
        for i in order
        if scores[i] > 0 and chunk_allowed(docs[i]["meta"], filters, allowed)
    ]
    return hits[:n]


def rrf_fuse(rankings: list[list[dict[str, Any]]], n: int) -> list[dict[str, Any]]:
    """여러 청크 순위를 Reciprocal Rank Fusion으로 합쳐 상위 n개를 반환한다."""
    fused: dict[str, float] = {}
    by_id: dict[str, dict[str, Any]] = {}
    for ranking in rankings:
        for rank, chunk in enumerate(ranking, start=1):
            fused[chunk["id"]] = fused.get(chunk["id"], 0.0) + 1 / (RRF_K + rank)
            by_id[chunk["id"]] = chunk
    best = sorted(fused, key=fused.get, reverse=True)[:n]  # type: ignore[arg-type]
    return [{**by_id[i], "rrf": fused[i]} for i in best]


def hybrid_search(query: str, n: int = 30, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """벡터와 BM25 결과를 결합한 청크 순위를 반환한다. 필터는 두 검색 모두에 적용한다."""
    allowed = allowed_place_ids(filters)
    if allowed == []:
        return []
    vector_hits = search_chunks(query, n_chunks=POOL, where=build_where(filters, allowed))
    bm25_hits = bm25_search(query, POOL, filters, allowed)
    return rrf_fuse([vector_hits, bm25_hits], n)
