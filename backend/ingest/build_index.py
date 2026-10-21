"""장소 소개·후기를 청킹·임베딩해 Chroma 인덱스를 만든다."""
import hashlib
import json
import logging
import time
from typing import Any

import chromadb
import numpy as np
from chromadb.api.models.Collection import Collection

from config import get_settings, setup_logging
from llm import get_embeddings
from models import Place, PlaceTraits, Review

logger = logging.getLogger(__name__)

COLLECTION_NAME = "travel"
CACHE_NAME = "embeddings.npz"  # 청크 id·본문 해시·벡터. 본문이 같으면 다시 임베딩하지 않는다.
# 무료 티어 임베딩 한도: 분당 100건(텍스트 1개 = 1건). 여유를 두고 20개/14초 간격으로 보낸다.
EMBED_BATCH = 20
BATCH_INTERVAL_SEC = 14
RETRY_WAIT_SEC = 30


def load_json(name: str) -> list[dict[str, Any]]:
    """data 폴더의 JSON 파일을 읽는다."""
    return json.loads((get_settings().data_dir / name).read_text(encoding="utf-8"))


def dedupe_reviews(reviews: list[Review]) -> list[Review]:
    """같은 장소 안에서 본문이 같은 후기를 제거한다 (원본 파일은 수정하지 않는다)."""
    seen: set[tuple[str, str]] = set()
    kept: list[Review] = []
    for r in reviews:
        key = (r.place_id, r.text.strip())
        if key not in seen:
            seen.add(key)
            kept.append(r)
    return kept


def build_chunks() -> tuple[list[str], list[str], list[dict[str, Any]]]:
    """장소 1청크 + 후기 1청크씩 (ids, texts, metadatas)를 만든다."""
    places = [Place(**p) for p in load_json("places.json")]
    traits = {t["place_id"]: PlaceTraits(**t) for t in load_json("place_traits.json")}
    reviews = dedupe_reviews([Review(**r) for r in load_json("reviews.json")])
    place_by_id = {p.id: p for p in places}

    ids: list[str] = []
    texts: list[str] = []
    metas: list[dict[str, Any]] = []
    for p in places:
        ids.append(f"place-{p.id}")
        texts.append(f"{p.name} ({p.category}) {p.address}. {p.description}")
        metas.append(
            {
                "type": "place",
                "place_id": p.id,
                "category": p.category,
                "lat": p.lat,
                "lng": p.lng,
                "indoor": traits[p.id].indoor,
            }
        )
    for r in reviews:
        p = place_by_id[r.place_id]
        ids.append(f"review-{r.review_id}")
        texts.append(f"{p.name} 후기: {r.text}")
        metas.append(
            {
                "type": "review",
                "place_id": r.place_id,
                "rating": r.rating,
                "author_type": r.author_type,
                "season": r.season,
            }
        )
    return ids, texts, metas


def text_hash(text: str) -> str:
    """청크 본문의 짧은 해시. 본문이 바뀌면 캐시를 쓰지 않는다."""
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def load_cache() -> dict[str, tuple[str, np.ndarray]]:
    """임베딩 캐시를 읽는다: id → (본문 해시, 벡터). 파일이 없으면 빈 dict."""
    path = get_settings().data_dir / CACHE_NAME
    if not path.exists():
        return {}
    with np.load(path, allow_pickle=False) as z:
        model = str(z["model"]) if "model" in z.files else ""
        if model != get_settings().embedding_model:  # 다른 모델의 벡터는 섞어 쓰지 않는다
            logger.info("임베딩 캐시의 모델(%s)이 현재 설정(%s)과 달라 쓰지 않습니다", model or "미기록", get_settings().embedding_model)
            return {}
        return {i: (h, v) for i, h, v in zip(z["ids"].tolist(), z["hashes"].tolist(), z["vectors"])}


def save_cache(cache: dict[str, tuple[str, np.ndarray]]) -> None:
    """임베딩 캐시를 저장한다 (압축 npz)."""
    ids = list(cache)
    np.savez_compressed(
        get_settings().data_dir / CACHE_NAME,
        ids=np.array(ids),
        hashes=np.array([cache[i][0] for i in ids]),
        vectors=np.stack([cache[i][1] for i in ids]).astype(np.float32),
        model=np.array(get_settings().embedding_model),
    )


def seed_cache_from_index(client: chromadb.ClientAPI, texts_by_id: dict[str, str]) -> dict[str, tuple[str, np.ndarray]]:
    """캐시가 없을 때, 기존 Chroma 인덱스의 벡터를 본문이 같은 청크에 한해 캐시로 옮긴다 (재임베딩 방지)."""
    try:
        collection = client.get_collection(COLLECTION_NAME)
        if (collection.metadata or {}).get("embedding_model") != get_settings().embedding_model:
            return {}  # 모델 기록이 없거나 다르면 벡터를 재사용하지 않는다
        got = collection.get(include=["documents", "embeddings"])
    except Exception:  # 기존 인덱스가 없다
        return {}
    seeded: dict[str, tuple[str, np.ndarray]] = {}
    for i, doc, vec in zip(got["ids"], got["documents"], got["embeddings"]):
        if texts_by_id.get(i) == doc:
            seeded[i] = (text_hash(doc), np.asarray(vec, dtype=np.float32))
    return seeded


def build_index() -> Collection:
    """Chroma 컬렉션을 새로 만든다. 캐시에 없는(새로 생기거나 본문이 바뀐) 청크만 임베딩한다."""
    ids, texts, metas = build_chunks()
    settings = get_settings()
    client = chromadb.PersistentClient(path=str(settings.chroma_dir))

    cache = load_cache() or seed_cache_from_index(client, dict(zip(ids, texts)))
    missing = [k for k, (i, t) in enumerate(zip(ids, texts)) if i not in cache or cache[i][0] != text_hash(t)]
    logger.info("청크 %d개 중 새로 임베딩할 것 %d개", len(ids), len(missing))

    embeddings = get_embeddings()
    for start in range(0, len(missing), EMBED_BATCH):
        batch = missing[start : start + EMBED_BATCH]
        try:
            vectors = embeddings.embed_documents([texts[k] for k in batch])
        except Exception as exc:  # 분당 한도 초과 시 한 번 기다렸다가 재시도
            logger.warning("임베딩 실패(%s), %d초 후 재시도", type(exc).__name__, RETRY_WAIT_SEC)
            time.sleep(RETRY_WAIT_SEC)
            vectors = embeddings.embed_documents([texts[k] for k in batch])
        for k, vec in zip(batch, vectors):
            cache[ids[k]] = (text_hash(texts[k]), np.asarray(vec, dtype=np.float32))
        save_cache({i: cache[i] for i in cache})  # 중간에 끊겨도 이어서 할 수 있게 매번 저장
        logger.info("임베딩 %d/%d", min(start + EMBED_BATCH, len(missing)), len(missing))
        time.sleep(BATCH_INTERVAL_SEC)

    keep = {i: cache[i] for i in ids}  # 더 이상 없는 청크는 캐시에서 버린다
    save_cache(keep)
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:  # 처음 만들 때는 컬렉션이 없다
        pass
    collection = client.create_collection(
        COLLECTION_NAME,
        # 청크가 1,000개를 넘으면 기본 임계값에서 쓰는 도중 HNSW 파일 기록이 깨져 다른 프로세스가 열지 못했다(1,510청크, chromadb 1.5.9).
        # 임계값을 청크 수보다 크게 둬서 쓰기 도중 디스크 동기화가 일어나지 않게 한다.
        metadata={
            "hnsw:space": "cosine",
            "hnsw:batch_size": 10000,
            "hnsw:sync_threshold": 10000,
            "embedding_model": settings.embedding_model,
        },
    )
    for start in range(0, len(ids), 200):
        sl = slice(start, start + 200)
        collection.add(
            ids=ids[sl],
            documents=texts[sl],
            metadatas=metas[sl],
            embeddings=[keep[i][1].tolist() for i in ids[sl]],
        )
    return collection


def main() -> None:
    """인덱스를 생성한다."""
    setup_logging()
    collection = build_index()
    logger.info("인덱스 완료: %d청크", collection.count())


if __name__ == "__main__":
    main()
