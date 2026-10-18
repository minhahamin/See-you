"""인덱싱: 청크 구성, 중복 후기 제거, 임베딩 캐시 테스트."""
from types import SimpleNamespace

import numpy as np
import pytest

from ingest import build_index as B
from models import Review


def review(rid: str, place_id: str, text: str) -> Review:
    """테스트용 후기."""
    return Review(review_id=rid, place_id=place_id, text=text, rating=4, author_type="가족", season="가을", visit_time="오후", created_at="2026-01-01")


def test_dedupe_reviews_only_within_same_place() -> None:
    """같은 장소의 동일 본문만 제거하고, 다른 장소의 같은 문장은 둘 다 남긴다."""
    out = B.dedupe_reviews([review("a-1", "a", "좋아요"), review("a-2", "a", "좋아요 "), review("b-1", "b", "좋아요")])
    assert [r.review_id for r in out] == ["a-1", "b-1"]


def test_build_chunks_one_per_place_and_review() -> None:
    """장소마다 1청크, 후기마다 1청크이고 메타데이터 필터에 필요한 값이 들어 있다."""
    ids, texts, metas = B.build_chunks()
    places = [m for m in metas if m["type"] == "place"]
    reviews = [m for m in metas if m["type"] == "review"]
    assert len(ids) == len(texts) == len(metas) == len(set(ids)) == len(places) + len(reviews)
    assert all({"place_id", "category", "lat", "lng", "indoor"} <= m.keys() for m in places)
    assert all({"place_id", "rating", "author_type", "season"} <= m.keys() for m in reviews)
    assert any(m["category"] == "관광지" and m["indoor"] for m in places)  # 실내 관광지(문화시설)가 포함돼 있다


def test_text_hash_changes_with_text() -> None:
    """본문이 바뀌면 해시가 달라져 캐시를 쓰지 않는다."""
    assert B.text_hash("a") == B.text_hash("a") and B.text_hash("a") != B.text_hash("b")


def test_cache_round_trip_and_model_mismatch(tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    """캐시는 저장·복원해도 id, 해시, 벡터가 그대로이고, 임베딩 모델이 바뀌면 쓰지 않는다."""
    settings = SimpleNamespace(data_dir=tmp_path, embedding_model="model-a")
    monkeypatch.setattr(B, "get_settings", lambda: settings)
    assert B.load_cache() == {}  # 파일이 없으면 빈 캐시
    cache = {"place-1": (B.text_hash("x"), np.array([0.1, 0.2, 0.3], dtype=np.float32)), "review-1": (B.text_hash("y"), np.array([1, 2, 3], dtype=np.float32))}
    B.save_cache(cache)
    loaded = B.load_cache()
    assert set(loaded) == set(cache)
    for k in cache:
        assert loaded[k][0] == cache[k][0]
        np.testing.assert_allclose(loaded[k][1], cache[k][1])

    settings.embedding_model = "model-b"  # 모델을 바꾸면 이전 벡터는 버린다
    assert B.load_cache() == {}
