"""벡터 검색 (v1). 청크 단위로 검색하고 장소 단위로 묶어 반환한다."""
import logging
from typing import Any

import chromadb

from config import get_settings
from ingest.build_index import COLLECTION_NAME
from llm import get_embeddings

logger = logging.getLogger(__name__)


def get_collection() -> chromadb.Collection:
    """저장된 Chroma 컬렉션을 연다."""
    client = chromadb.PersistentClient(path=str(get_settings().chroma_dir))
    return client.get_collection(COLLECTION_NAME)


def search_chunks(
    query: str, n_chunks: int = 30, where: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    """질문과 가까운 청크를 거리순으로 반환한다. where로 메타데이터 필터를 건다."""
    vector = get_embeddings().embed_query(query)
    res = get_collection().query(query_embeddings=[vector], n_results=n_chunks, where=where)
    return [
        {"id": i, "text": d, "meta": m, "distance": dist}
        for i, d, m, dist in zip(
            res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0]
        )
    ]


def rank_places(chunks: list[dict[str, Any]]) -> list[str]:
    """청크 순위를 장소 순위로 바꾼다 (장소별 가장 높은 청크 기준, 중복 제거)."""
    ranked: list[str] = []
    for c in chunks:
        pid = c["meta"]["place_id"]
        if pid not in ranked:
            ranked.append(pid)
    return ranked


def search_places(query: str, k: int = 5, where: dict[str, Any] | None = None) -> list[str]:
    """질문에 맞는 장소 id를 상위 k개 반환한다."""
    return rank_places(search_chunks(query, where=where))[:k]
