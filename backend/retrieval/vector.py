"""벡터 검색 (v1). 청크 단위로 검색하고 장소 단위로 묶어 반환한다."""
import logging
from typing import Any

import chromadb

from agent import catalog
from config import get_settings
from ingest.build_index import COLLECTION_NAME
from llm import embed_query_cached

logger = logging.getLogger(__name__)


def get_collection() -> chromadb.Collection:
    """저장된 Chroma 컬렉션을 연다."""
    client = chromadb.PersistentClient(path=str(get_settings().chroma_dir))
    return client.get_collection(COLLECTION_NAME)


def allowed_place_ids(filters: dict[str, Any] | None) -> list[str] | None:
    """category·indoor·area 필터를 만족하는 장소 id 목록을 구한다. 필터가 없으면 None(제한 없음).

    area는 인덱스 메타데이터가 아니라 장소 주소(catalog)로 거르므로 인덱스를 다시 만들 필요가 없다.
    """
    conds = [{k: filters[k]} for k in ("category", "indoor") if filters and k in filters]
    area = (filters or {}).get("area")
    if not conds and not area:
        return None
    ids = None
    if conds:
        got = get_collection().get(where={"$and": [{"type": "place"}, *conds]}, include=["metadatas"])
        ids = [m["place_id"] for m in got["metadatas"]]
    if area:
        in_area = set(catalog.place_ids_in_area(area))
        ids = sorted(in_area) if ids is None else [i for i in ids if i in in_area]
    return ids


def chunk_allowed(meta: dict[str, Any], filters: dict[str, Any] | None, allowed: list[str] | None) -> bool:
    """청크 메타데이터가 필터를 통과하는지 판정한다 (BM25 결과 필터링용).

    장소 소개 청크는 author_type이 없으므로 항상 통과하고, 후기 청크만 작성자 유형으로 거른다.
    """
    if allowed is not None and meta["place_id"] not in allowed:
        return False
    author = (filters or {}).get("author_type")
    return author is None or meta["type"] == "place" or meta.get("author_type") == author


def build_where(filters: dict[str, Any] | None, allowed: list[str] | None) -> dict[str, Any] | None:
    """Chroma where 조건을 만든다. 후기 청크는 작성자 유형으로만 제한한다."""
    clauses: list[dict[str, Any]] = []
    if allowed is not None:
        clauses.append({"place_id": {"$in": allowed}})
    author = (filters or {}).get("author_type")
    if author:
        clauses.append({"$or": [{"type": "place"}, {"author_type": author}]})
    if not clauses:
        return None
    return clauses[0] if len(clauses) == 1 else {"$and": clauses}


def search_chunks(
    query: str, n_chunks: int = 30, where: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    """질문과 가까운 청크를 거리순으로 반환한다. where로 메타데이터 필터를 건다."""
    vector = embed_query_cached(query)
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
