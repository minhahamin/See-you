"""일정 생성 노드: 후보와 후기 요약으로 일자별 계획을 만들고 route 도구로 시간·동선을 배치한다."""
import logging
from datetime import date, timedelta

from agent import catalog
from agent.planning import day_weather, plan_days, sanitize_visits, schedule_day
from agent.state import DayPlan, Itinerary, PlannerState, Validation

logger = logging.getLogger(__name__)


def build_itinerary(state: PlannerState) -> dict:
    """LLM이 정한 일자별 방문 계획을 정리하고 시간표로 만든다. 검증 실패 후 재호출이면 문제점을 프롬프트에 넣는다."""
    request = state["request"]
    candidates, summaries = state["candidates"], state["review_summaries"]
    weather = state.get("weather", {})
    issues = state.get("validation_issues") or []
    retry_count = state.get("retry_count", 0) + (1 if issues else 0)

    day_count = request.days or 1
    plan = plan_days(request, candidates, summaries, weather, list(range(1, day_count + 1)), issues)
    llm_days = {d.day: d for d in plan.days}
    start = date.fromisoformat(request.start_date)
    all_places = catalog.places()

    used: set[str] = set()  # 숙소를 뺀 장소는 여러 날에 반복하지 않는다
    day_plans: list[DayPlan] = []
    for n in range(1, day_count + 1):
        llm_day = llm_days.get(n)
        planned = sanitize_visits(llm_day.visits if llm_day else [], candidates, summaries, exclude_ids=used)
        used |= {p.place_id for p in planned if all_places[p.place_id].category != "숙소"}
        day_date = (start + timedelta(days=n - 1)).isoformat()
        visits = schedule_day(planned)
        day_plans.append(DayPlan(day=n, date=day_date, weather=day_weather(visits, day_date, state), visits=visits))

    itinerary = Itinerary(
        title=plan.title or f"{request.region} {day_count}일 여행",
        region=request.region,
        companions=request.companions or "",
        days=day_plans,
        validation=Validation(),
    )
    logger.info("일정 생성 완료 (재시도 %d회차, 방문 %d곳)", retry_count, sum(len(d.visits) for d in day_plans))
    return {"itinerary": itinerary, "retry_count": retry_count}
