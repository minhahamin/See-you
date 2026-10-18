"""후기 분석 노드: 후보별 장단점을 요약하고 근거 후기 id를 붙인다. 조건과 맞지 않는 장소는 제외한다."""
import logging

from agent.review_tools import apply_exclusions, summarize
from agent.state import PlannerState

logger = logging.getLogger(__name__)


def analyze_reviews(state: PlannerState) -> dict:
    """후기를 요약하고 조건과 맞지 않는 후보를 제외한다."""
    request, candidates = state["request"], state["candidates"]
    by_id = summarize(candidates, request.companions or "미정")
    kept = apply_exclusions(candidates, by_id, request.days or 1)
    dropped = [c.name for c in candidates if c not in kept]
    logger.info("후기 분석 완료, 제외 %d곳: %s", len(dropped), dropped)
    return {"candidates": kept, "review_summaries": {c.id: by_id[c.id] for c in kept}}
