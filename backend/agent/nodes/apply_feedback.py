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
from agent.nodes.validate_itinerary import run_checks
from agent.prompts import APPLY_FEEDBACK_SYSTEM, PARSE_REQUEST_SYSTEM, REPLACE_DAY_NOTE
from agent.repair import Context, _fits_hours, _travel_score, repair_itinerary_plan
from agent.review_tools import summarize
from agent.state import Area, DayPlan, Itinerary, PlannerState, TripRequest
from config import get_settings
from llm import structured_call
from retrieval.hybrid import hybrid_search
from retrieval.vector import rank_places

logger = logging.getLogger(__name__)

REPLACEMENT_POOL = 8
CONSTRAINT_SUMMARY_BATCH = 3  # 요청한 조건이 있으면 관련도 상위 이만큼만 먼저 요약한다 (후기 요약 LLM 호출이 후보 수에 비례해 느려진다)
UNCLEAR_FEEDBACK_REPLY = "무엇을 바꾸고 싶으신지 잘 모르겠어요. 일정은 그대로 두었어요. 예: '2일차 점심을 흑돼지 식당으로 바꿔줘', 마음에 드시면 '이대로 확정'이라고 말해 주세요."


class FeedbackAction(BaseModel):
    """LLM이 해석한 수정 동작."""

    action: Literal["replace_visit", "replace_day", "rebuild", "accept", "unclear"]
    day: int | None = None
    visit_index: int | None = None  # 1부터
    constraint: str = ""
    area: Area | None = None  # rebuild에서 사용자가 구역을 바꾸라고 했을 때
    keep: list[str] = []  # 그대로 두거나 꼭 넣고 싶은 장소·음식 키워드 (예: 흑돼지)


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


def _place_text(place_id: str) -> str:
    """키워드가 들어 있는지 볼 장소의 이름·소개·특성 텍스트."""
    place, trait = catalog.places()[place_id], catalog.traits()[place_id]
    return " ".join([place.name, place.description, *trait.pros, *trait.cons])


def find_pinned(keywords: list[str], itinerary: Itinerary, request: TripRequest) -> list[str]:
    """그대로 두거나 넣고 싶다고 한 키워드에 해당하는 장소 id. 현재 일정에서 먼저 찾고, 없으면 검색한다."""
    in_plan = [v.place_id for d in itinerary.days for v in d.visits]
    found: list[str] = []
    for kw in (k.strip() for k in keywords):
        if not kw:
            continue
        pid = next((p for p in in_plan if kw in _place_text(p)), None)
        if pid is None:
            filters = {"area": request.area} if request.area else {}
            pid = next((p for p in rank_places(hybrid_search(kw, n=10, filters=filters)) if kw in _place_text(p)), None)
        if pid and pid not in found:
            found.append(pid)
    return found


def _pin_slot(place_id: str) -> str:
    """꼭 넣을 장소가 들어갈 시간대. 식당은 영업시간이 맞는 점심/저녁, 그 밖에는 분류에 맞는 시간대."""
    category = catalog.places()[place_id].category
    if category == "음식점":
        return "lunch" if _fits_hours(place_id, "lunch") or not _fits_hours(place_id, "dinner") else "dinner"
    return {"카페": "cafe", "숙소": "stay"}.get(category, "afternoon")


def _replace_day(state: PlannerState, action: FeedbackAction, day: DayPlan) -> DayPlan | None:
    """한 일차를 LLM으로 다시 짜고, 바뀐 방문에 changed를 표시한다. 계획이 비면 None."""
    itinerary, request = state["itinerary"], state["request"]
    candidates, summaries = list(state["candidates"]), dict(state["review_summaries"])
    used = _used_ids(itinerary, skip_day=day.day)
    all_places = catalog.places()

    pinned = [p for p in find_pinned(action.keep, itinerary, request) if p not in used]
    fresh = [to_candidate(p, i) for i, p in enumerate(pinned) if p not in {c.id for c in candidates}]
    if fresh:
        candidates += fresh
        summaries.update(summarize(fresh, request.companions or "미정"))
    must = "".join(f"반드시 포함: {all_places[p].name}({all_places[p].category})\n" for p in pinned)
    note = REPLACE_DAY_NOTE.format(
        day=day.day,
        constraint=action.constraint or "다른 구성으로",
        must=must,
        used=", ".join(all_places[p].name for p in sorted(used)) or "없음",
    )
    plan = plan_days(request, candidates, summaries, state.get("weather", {}), [day.day], note=note)
    llm_day = next((d for d in plan.days if d.day == day.day), plan.days[0] if plan.days else None)
    planned = sanitize_visits(llm_day.visits if llm_day else [], candidates, summaries, exclude_ids=used)
    if not planned:
        return None

    for pid in pinned:  # LLM이 빠뜨렸거나 엉뚱한 시간대에 넣었어도 꼭 넣을 장소는 알맞은 시간대에 둔다
        slot = _pin_slot(pid)
        s = summaries.get(pid)
        entry = PlannedVisit(
            place_id=pid,
            slot=slot,
            reason="요청하신 대로 넣었어요. " + (f"후기에서 '{s.pros[0]}'라는 평이 있어요." if s and s.pros else ""),
            evidence_review_ids=s.evidence_review_ids[:2] if s else [],
        )
        category = all_places[pid].category
        planned = [p for p in planned if p.place_id != pid and not (all_places[p.place_id].category == category and p.slot == slot)]
        planned.append(entry)

    old_ids = {v.place_id for v in day.visits}
    scheduled = day.model_copy(update={"visits": schedule_day(planned)})
    trial = itinerary.model_copy(update={"days": [scheduled if d.day == day.day else d for d in itinerary.days]})
    fixed = repair_itinerary_plan(trial, Context(request, candidates, summaries, frozenset(pinned)))
    visits = next(d for d in fixed.days if d.day == day.day).visits  # 수리는 이 일차만 반영한다 (다른 일차는 그대로)
    visits = [v.model_copy(update={"changed": v.place_id not in old_ids}) for v in visits]
    return day.model_copy(update={"visits": visits})


def _replace_visit(
    state: PlannerState, action: FeedbackAction, day: DayPlan
) -> tuple[DayPlan, list, dict, str] | None:
    """방문 하나를 검색으로 찾은 새 장소로 바꾸고 그 일차를 부분 수리한다. (일차, 후보, 요약, 새 장소 id). 적합한 대체 장소가 없으면 None."""
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
    # 조건이 있으면 상위 후보만 먼저 요약하고, 그 안에 적합한 곳이 없을 때만 나머지를 요약한다
    batches = [fresh[:CONSTRAINT_SUMMARY_BATCH], fresh[CONSTRAINT_SUMMARY_BATCH:]] if action.constraint else [fresh]
    summarized: list = []
    for batch in batches:
        if batch:
            summaries.update(summarize(batch, request.companions or "미정"))
            summarized += batch
        if any(summaries[p].suitable for p in pool_ids if p in summaries):
            break
    fresh = summarized
    pool_ids = [p for p in pool_ids if p in summaries]
    planned = to_planned(day.visits)
    slot = planned[index].slot

    def fit(item: tuple[int, str]) -> tuple[bool, int, int]:
        """영업시간을 벗어나는지, 교체 뒤 이동 상한을 넘는 정도, 검색 순위. 작을수록 좋다."""
        rank, pid = item
        trial = [*planned[:index], PlannedVisit(place_id=pid, slot=slot, reason="", evidence_review_ids=[]), *planned[index + 1 :]]
        if action.constraint:  # 원하는 바를 말했으면 관련도가 먼저다 (이동 때문에 엉뚱한 곳으로 바꾸지 않는다)
            return (not _fits_hours(pid, slot), 0, rank)
        return (not _fits_hours(pid, slot), _travel_score(trial)[0], rank)

    suitable = [(i, p) for i, p in enumerate(pool_ids) if summaries[p].suitable]
    if not suitable:
        return None
    chosen = min(suitable, key=fit)[1]

    s = summaries[chosen]
    reason = (f"요청하신 '{action.constraint}'에 맞춰 골랐어요. " if action.constraint else "") + (
        f"후기에서 '{s.pros[0]}'라는 평이 있어요." if s.pros else ""
    )
    planned[index] = PlannedVisit(
        place_id=chosen, slot=slot, reason=reason.strip(), evidence_review_ids=s.evidence_review_ids[:2], changed=True
    )
    known = {c.id for c in state["candidates"]}
    candidates = [*state["candidates"], *[c for c in fresh if c.id not in known]]

    # 바꾼 장소 때문에 검증 실패가 늘어났을 때만 그 일차를 수리한다 (원래 있던 문제나 요청하지 않은 블록은 건드리지 않는다).
    # 사용자가 요청한 장소는 수리가 바꾸지 못하게 지킨다.
    itinerary = state["itinerary"]
    old_ids = {v.place_id for v in day.visits}
    scheduled = day.model_copy(update={"visits": schedule_day(planned)})
    trial = itinerary.model_copy(update={"days": [scheduled if d.day == day.day else d for d in itinerary.days]})
    summaries_now = {**state["review_summaries"], **summaries}

    def failures(it: Itinerary) -> int:
        """검증에 실패한 항목 수."""
        return sum(not c.ok for c in run_checks(it, request, summaries_now))

    if failures(trial) > failures(itinerary):
        fixed = repair_itinerary_plan(trial, Context(request, candidates, summaries, frozenset({chosen})))
        trial = fixed if failures(fixed) < failures(trial) else trial
    visits = next(d for d in trial.days if d.day == day.day).visits  # 수리는 이 일차만 반영한다 (다른 일차는 그대로)
    visits = [v.model_copy(update={"changed": v.place_id not in old_ids}) for v in visits]
    return day.model_copy(update={"visits": visits}), candidates, summaries, chosen


def render_feedback_input(state: PlannerState, limit: int = 6) -> str:
    """피드백 해석기에 줄 입력: 최근 대화(직전 요청과의 맥락)와 이번 피드백."""
    feedback = state["feedback"] or ""
    history = [m for m in state.get("messages", []) if m.type in ("human", "ai")][-limit - 1 : -1]
    if not history:
        return feedback
    lines = [f"{'사용자' if m.type == 'human' else '에이전트'}: {str(m.content)[:200]}" for m in history]
    return "최근 대화:\n" + "\n".join(lines) + f"\n\n이번 피드백: {feedback}"


def _note(text: str) -> dict:
    """사용자에게 알릴 말: 대화 기록에 남기고, 다음 일정 제시 때 함께 보여 준다."""
    return {"notice": text, "messages": [AIMessage(text)]}


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
            return {**base, **_note(str(e))}

    action = structured_call(
        FeedbackAction,
        [SystemMessage(APPLY_FEEDBACK_SYSTEM.format(itinerary=render_itinerary(itinerary))), HumanMessage(render_feedback_input(state))],
    )
    logger.info("피드백 해석: %s", action.model_dump())
    base: dict = {"feedback": None, "retry_count": 0, "validation_issues": []}

    if action.action == "accept":
        return {**base, "accepted": True}
    if action.action == "unclear":
        # 확정으로 오해해 대화를 끝내지 않고, 일정은 그대로 둔 채 다시 묻는다
        base["retry_count"] = get_settings().max_retry
        return {**base, **_note(UNCLEAR_FEEDBACK_REPLY)}
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
        return {**base, **_note("어느 일차를 바꿀지 찾지 못해 일정을 그대로 두었어요.")}

    update: dict = {}
    names = catalog.places()
    done = ""
    if action.action == "replace_day":
        new_day = _replace_day(state, action, day)
        done = f"{day.day}일차를 다시 짰어요."
    else:
        result = _replace_visit(state, action, day)
        new_day = result[0] if result else None
        if result:
            update = {"candidates": result[1], "review_summaries": result[2]}
            old_id, new_id = day.visits[(action.visit_index or 1) - 1].place_id, result[3]
            done = f"{day.day}일차 {action.visit_index}번째 방문 '{names[old_id].name}'을(를) '{names[new_id].name}'(으)로 바꿨어요."
            moved = sum(v.changed for v in new_day.visits) - 1
            if moved > 0:  # 바꾼 장소 때문에 생긴 이동·영업시간 문제를 고치려고 다른 방문도 조정한 경우
                done += f" 이동·영업시간 문제를 피하려고 같은 날 {moved}곳도 함께 조정했어요."
    if new_day is None:
        return {**base, **_note("조건에 맞는 대체 장소를 찾지 못해 일정을 그대로 두었어요.")}

    days = [new_day if d.day == day.day else d.model_copy(update={"visits": [v.model_copy(update={"changed": False}) for v in d.visits]}) for d in itinerary.days]
    return {**base, **update, **_note(done), "itinerary": refresh_weather(itinerary.model_copy(update={"days": days}), state)}
