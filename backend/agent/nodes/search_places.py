"""장소 검색 노드: 하이브리드 검색(v3) + 메타데이터 필터로 분류별 후보를 모은다."""
import logging

from agent.planning import CATEGORY_PHRASE, COMPANION_PHRASE, to_candidate
from agent.state import PlannerState, TripRequest
from models import Category
from retrieval.hybrid import hybrid_search
from retrieval.vector import rank_places

logger = logging.getLogger(__name__)


def candidate_count(category: Category, days: int) -> int:
    """일정에 필요한 수보다 여유 있게 가져올 후보 수."""
    need = {
        "관광지": days * 3 + 3,
        "음식점": days * 2 + 2,
        "카페": days + 2,
        "숙소": min(days, 3) + 1,
    }
    return need[category]


def build_query(request: TripRequest, category: Category) -> str:
    """조건을 검색 질문 문장으로 바꾼다."""
    phrase = COMPANION_PHRASE.get(request.companions or "", "")
    return " ".join(filter(None, [phrase, CATEGORY_PHRASE[category], *request.preferences]))


def search_places(state: PlannerState) -> dict:
    """분류별로 검색해 후보 목록을 만든다 (분류 안에서 검색 순위를 rank로 기록)."""
    request = state["request"]
    days = request.days or 1
    candidates = []
    for category in CATEGORY_PHRASE:
        filters: dict = {"category": category}
        if request.companions:
            filters["author_type"] = request.companions
        chunks = hybrid_search(build_query(request, category), n=30, filters=filters)
        for rank, pid in enumerate(rank_places(chunks)[: candidate_count(category, days)]):
            candidates.append(to_candidate(pid, rank))
    counts = {c: sum(x.category == c for x in candidates) for c in CATEGORY_PHRASE}
    logger.info("후보 %d곳: %s", len(candidates), counts)
    return {"candidates": candidates, "rerun_search": False}
