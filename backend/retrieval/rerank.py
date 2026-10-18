"""로컬 크로스 인코더 리랭커 (v4). 검색 후보를 (질문, 청크) 쌍으로 다시 점수화한다."""
import logging
import os
from functools import lru_cache
from typing import Any

# transformers가 설치된 TensorFlow/Keras 3를 불러오다 실패하지 않도록 PyTorch만 쓰게 한다.
os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("USE_FLAX", "0")

from sentence_transformers import CrossEncoder  # noqa: E402

from config import get_settings

logger = logging.getLogger(__name__)

MAX_LENGTH = 512  # 청크가 짧아서 충분하다. 길수록 CPU 추론이 느려진다.


@lru_cache(maxsize=1)
def _load_model() -> CrossEncoder:
    """리랭커 모델을 한 번만 로드한다 (첫 실행 시 Hugging Face에서 내려받는다)."""
    name = get_settings().reranker_model
    logger.info("리랭커 로드: %s", name)
    return CrossEncoder(name, max_length=MAX_LENGTH)


def rerank(query: str, chunks: list[dict[str, Any]], top_n: int | None = None) -> list[dict[str, Any]]:
    """청크를 질문과의 관련도 점수 순으로 재정렬한다."""
    if not chunks:
        return []
    scores = _load_model().predict([(query, c["text"]) for c in chunks], show_progress_bar=False)
    ranked = sorted(
        ({**c, "rerank_score": float(s)} for c, s in zip(chunks, scores)),
        key=lambda c: c["rerank_score"],
        reverse=True,
    )
    return ranked[:top_n] if top_n else ranked
