"""피드백 반영 노드: 수정 범위를 판단해 특정 방문·일차만 바꾸거나, 필요하면 전체 재검색을 요청한다."""
import logging
from datetime import date
from typing import Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel

from agent import catalog
from agent.moving import MoveError, move_visit, parse_move
from agent.planning import CATEGORY_PHRASE, PlannedVisit, plan_days, refresh_weather, sanitize_visits, schedule_day, to_candidate, to_planned
from agent.nodes.parse_request import ParsedRequest, merge_request
from agent.prompts import APPLY_FEEDBACK_SYSTEM, PARSE_REQUEST_SYSTEM, REPLACE_DAY_NOTE
from agent.review_tools import summarize
from agent.state import Area, DayPlan, Itinerary, PlannerState, TripRequest
from config import get_settings
from llm import structured_call
from retrieval.hybrid import hybrid_search
from retrieval.vector import rank_places

logger = logging.getLogger(__name__)

REPLACEMENT_POOL = 3
UNCLEAR_FEEDBACK_REPLY = "무엇을 바꾸고 싶으신지 잘 모르겠어요. 일정은 그대로 두었어요. 예: '2일차 점심을 흑돼지 식당으로 바꿔줘', 마음에 드시면 '이대로 확정'이라고 말해 주세요."


class FeedbackAction(BaseModel):
    """LLM이 해석한 수정 동작."""

    action: Literal["replace_visit", "replace_day", "rebuild", "accept", "unclear"]
    day: int | None = None
    visit_index: int | None = None  # 1부터
    constraint: str = ""
    area: Area | None = None  # rebuild에서 사용자가 구역을 바꾸라고 했을 때


def render_itinerary(itinerary: Itinerary) -> str:
    """피드백 해석용 일정 텍스트 (일차·순번·장소명·분류)."""
    all_places = catalog.places()
    lines = []
    for d in itinerary.days:
        items = ", ".join(
            f"{i}.{all_places[v.place_id].name}({all_places[v.place_id].category})" for i, v in enumerate(d.visits, 1)
        )
        lines.append(f"{d.day}일차: {items}")
    return "\n".join(lines)


def _used_ids(itinerary: Itinerary, skip_day: int | None = None) -> set[str]:
    """일정에서 이미 쓰는 장소 id (숙소 제외, 특정 일차 제외 가능)."""
    all_places = catalog.places()
    return {
        v.place_id
        for d in itinerary.days
        if d.day != skip_day
        for v in d.visits
        if all_places[v.place_id].category != "숙소"
    }


def _replace_day(state: PlannerState, action: FeedbackAction, day: DayPlan) -> DayPlan | None:
    """한 일차를 LLM으로 다시 짜고, 바뀐 방문에 changed를 표시한다. 계획이 비면 None."""
    itinerary, request = state["itinerary"], state["request"]
    candidates, summaries = state["candidates"], state["review_summaries"]
    used = _used_ids(itinerary, skip_day=day.day)
    all_places = catalog.places()
    note = REPLACE_DAY_NOTE.format(
        day=day.day, constraint=action.constraint or "다른 구성으로", used=", ".join(all_places[p].name for p in sorted(used)) or "없음"
    )
    plan = plan_days(request, candidates, summaries, state.get("weather", {}), [day.day], note=note)
    llm_day = next((d for d in plan.days if d.day == day.day), plan.days[0] if plan.days else None)
    planned = sanitize_visits(llm_day.visits if llm_day else [], candidates, summaries, exclude_ids=used)
    if not planned:
        return None
    old_ids = {v.place_id for v in day.visits}
    planned = [p.model_copy(update={"changed": p.place_id not in old_ids}) for p in planned]
    return day.model_copy(update={"visits": schedule_day(planned)})


def _replace_visit(
    state: PlannerState, action: FeedbackAction, day: DayPlan
) -> tuple[DayPlan, list, dict] | None:
    """방문 하나를 검색으로 찾은 새 장소로 바꾼다. 적합한 대체 장소가 없으면 None."""
    index = (action.visit_index or 0) - 1
    if not 0 <= index < len(day.visits):
        return None
    old = day.visits[index]
    category = catalog.places()[old.place_id].category
    request = state["request"]

    filters: dict = {"category": category}
    if request.companions:
        filters["author_type"] = request.companions
    if request.area:
        filters["area"] = request.area
    query = f"{action.constraint} {CATEGORY_PHRASE[category]}".strip()
    taken = _used_ids(state["itinerary"]) | {old.place_id}
    pool_ids = [p for p in rank_places(hybrid_search(query, n=30, filters=filters)) if p not in taken][:REPLACEMENT_POOL]
    if not pool_ids:
        return None

    summaries = dict(state["review_summaries"])
    fresh = [to_candidate(p, i) for i, p in enumerate(pool_ids) if p not in summaries]
    if fresh:
        summaries.update(summarize(fresh, request.companions or "미정"))
    chosen = next((p for p in pool_ids if summaries[p].suitable), None)
    if chosen is None:
        return None

    s = summaries[chosen]
    reason = (f"요청하신 '{action.constraint}'에 맞춰 골랐어요. " if action.constraint else "") + (
        f"후기에서 '{s.pros[0]}'라는 평이 있어요." if s.pros else ""
    )
    planned = to_planned(day.visits)
    planned[index] = PlannedVisit(
        place_id=chosen, slot=planned[index].slot, reason=reason.strip(), evidence_review_ids=s.evidence_review_ids[:2], changed=True
    )
    known = {c.id for c in state["candidates"]}
    candidates = [*state["candidates"], *[c for c in fresh if c.id not in known]]
    return day.model_copy(update={"visits": schedule_day(planned)}), candidates, summaries


def render_current_request(request: TripRequest) -> str:
    """파서가 상대적 변경('하루 미뤄줘')을 계산할 수 있도록 현재 조건을 한 줄로 보여 준다."""
    return (
        f"현재 조건: 출발일 {request.start_date or '미정'}, {request.days or '미정'}일, "
        f"동행 {request.companions or '미정'}, 예산 {request.budget or '미정'}"
    )


def apply_feedback(state: PlannerState) -> dict:
    """피드백을 해석해 수정 범위에 맞게 일정을 바꾼다. 처리한 피드백은 비운다."""
    itinerary, request = state["itinerary"], state["request"]

    # 타임라인에서 끌어다 놓은 이동은 문장 형식이 정해져 있어 LLM 없이 바로 처리한다
    move = parse_move(state["feedback"] or "")
    if move:
        # 이동 뒤에도 재생성하지 않고 검증 결과만 보여 준다 (재생성하면 옮긴 위치가 사라진다)
        base = {"feedback": None, "retry_count": get_settings().max_retry, "validation_issues": []}
        try:
            return {**base, "itinerary": refresh_weather(move_visit(itinerary, *move), state)}
        except MoveError as e:
            return {**base, "messages": [AIMessage(str(e))]}

    action = structured_call(
        FeedbackAction,
        [SystemMessage(APPLY_FEEDBACK_SYSTEM.format(itinerary=render_itinerary(itinerary))), HumanMessage(state["feedback"] or "")],
    )
    logger.info("피드백 해석: %s", action.model_dump())
    base: dict = {"feedback": None, "retry_count": 0, "validation_issues": []}

    if action.action == "accept":
        return {**base, "accepted": True}
    if action.action == "unclear":
        # 확정으로 오해해 대화를 끝내지 않고, 일정은 그대로 둔 채 다시 묻는다
        base["retry_count"] = get_settings().max_retry
        return {**base, "messages": [AIMessage(UNCLEAR_FEEDBACK_REPLY)]}
    if action.action == "rebuild":
        # 날짜·일수·동행·예산·구역이 바뀌었을 수 있으므로 처음 조건을 읽던 파서로 피드백을 다시 읽어 합친다
        today = date.today()
        parsed = structured_call(
            ParsedRequest,
            [SystemMessage(PARSE_REQUEST_SYSTEM.format(today=today.isoformat())), HumanMessage(f"{render_current_request(request)}\n사용자 피드백: {state['feedback'] or ''}")],
        )
        merged = merge_request(request, parsed, today)
        prefs = list(dict.fromkeys([*merged.preferences, *([action.constraint] if action.constraint else [])]))
        update = {"preferences": prefs, **({"area": action.area} if action.area and not parsed.area else {})}
        return {**base, "request": merged.model_copy(update=update), "rerun_search": True}

    # 부분 수정 뒤에는 검증 결과만 보여 주고 일정을 다시 만들지 않는다 (재생성하면 요청한 수정이 사라진다).
    base["retry_count"] = get_settings().max_retry
    day = next((d for d in itinerary.days if d.day == action.day), None)
    if day is None:
        return {**base, "messages": [AIMessage("어느 일차를 바꿀지 찾지 못해 일정을 그대로 두었어요.")]}

    update: dict = {}
    if action.action == "replace_day":
        new_day = _replace_day(state, action, day)
    else:
        result = _replace_visit(state, action, day)
        new_day = result[0] if result else None
        if result:
            update = {"candidates": result[1], "review_summaries": result[2]}
    if new_day is None:
        return {**base, "messages": [AIMessage("조건에 맞는 대체 장소를 찾지 못해 일정을 그대로 두었어요.")]}

    days = [new_day if d.day == day.day else d.model_copy(update={"visits": [v.model_copy(update={"changed": False}) for v in d.visits]}) for d in itinerary.days]
    return {**base, **update, "itinerary": refresh_weather(itinerary.model_copy(update={"days": days}), state)}
