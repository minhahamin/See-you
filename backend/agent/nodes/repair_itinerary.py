"""일정 수리 노드: 검증에 실패한 항목만 규칙으로 고친다 (전체를 다시 생성하지 않는다)."""
import logging

from agent.repair import Context, repair_itinerary_plan
from agent.state import PlannerState
from config import get_settings

logger = logging.getLogger(__name__)


def repair_itinerary(state: PlannerState) -> dict:
    """실패한 검증 항목을 부분 수리한다. 수리는 안에서 반복하므로 한 번 실행하면 재시도 한도를 모두 쓴 것으로 본다."""
    repaired = repair_itinerary_plan(
        state["itinerary"], Context(state["request"], state["candidates"], state.get("review_summaries", {}))
    )
    logger.info("부분 수리 완료")
    return {"itinerary": repaired, "retry_count": get_settings().max_retry}
