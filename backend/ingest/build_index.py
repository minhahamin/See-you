"""장소 소개·후기를 청킹·임베딩해 Chroma 인덱스를 만든다."""
import json
import logging
import time
from typing import Any

import chromadb
from chromadb.api.models.Collection import Collection

from config import get_settings, setup_logging
from llm import get_embeddings
from models import Place, PlaceTraits, Review

logger = logging.getLogger(__name__)

COLLECTION_NAME = "travel"
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


def build_index() -> Collection:
    """Chroma 컬렉션을 새로 만들어 청크를 임베딩해 저장한다."""
    ids, texts, metas = build_chunks()
    settings = get_settings()
    client = chromadb.PersistentClient(path=str(settings.chroma_dir))
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:  # 처음 만들 때는 컬렉션이 없다
        pass
    collection = client.create_collection(COLLECTION_NAME, metadata={"hnsw:space": "cosine"})

    embeddings = get_embeddings()
    for i in range(0, len(ids), EMBED_BATCH):
        sl = slice(i, i + EMBED_BATCH)
        try:
            vectors = embeddings.embed_documents(texts[sl])
        except Exception as exc:  # 분당 한도 초과 시 한 번 기다렸다가 재시도
            logger.warning("임베딩 실패(%s), %d초 후 재시도", type(exc).__name__, RETRY_WAIT_SEC)
            time.sleep(RETRY_WAIT_SEC)
            vectors = embeddings.embed_documents(texts[sl])
        collection.add(ids=ids[sl], documents=texts[sl], metadatas=metas[sl], embeddings=vectors)
        logger.info("임베딩 %d/%d", min(i + EMBED_BATCH, len(ids)), len(ids))
        time.sleep(BATCH_INTERVAL_SEC)
    return collection


def main() -> None:
    """인덱스를 생성한다."""
    setup_logging()
    collection = build_index()
    logger.info("인덱스 완료: %d청크", collection.count())


if __name__ == "__main__":
    main()
