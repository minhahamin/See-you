"""일정 계획 공용 로직: LLM 계획 호출, 계획 정리, 시간 배치. build_itinerary와 apply_feedback이 함께 쓴다."""
import logging
from collections import Counter
from datetime import date, timedelta

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from agent import catalog
from agent.prompts import BUILD_ITINERARY_RETRY, BUILD_ITINERARY_SYSTEM
from agent.state import Candidate, Itinerary, PlannerState, ReviewSummary, Slot, TripRequest, Visit, Weather
from llm import structured_call
from models import Category
from tools.route import order_nearest, travel_minutes

logger = logging.getLogger(__name__)

COMPANION_PHRASE = {"혼자": "혼자서", "커플": "연인과", "친구": "친구들과", "가족": "가족과"}
CATEGORY_PHRASE: dict[Category, str] = {
    "관광지": "가기 좋은 관광지",
    "음식점": "가기 좋은 음식점",
    "카페": "가기 좋은 카페",
    "숙소": "묵기 좋은 숙소",
}

SLOT_ORDER: list[Slot] = ["morning", "lunch", "afternoon", "cafe", "dinner", "stay"]
SLOT_START_MIN = {"morning": 9 * 60, "lunch": 12 * 60, "afternoon": 13 * 60 + 30, "cafe": 15 * 60 + 30, "dinner": 18 * 60, "stay": 20 * 60}
DURATION_MIN = {"관광지": 90, "음식점": 60, "카페": 60, "숙소": 30}


class LLMVisit(BaseModel):
    """LLM이 계획한 방문 한 건."""

    place_id: str
    slot: Slot
    reason: str
    evidence_review_ids: list[str] = Field(default_factory=list)


class LLMDay(BaseModel):
    """LLM이 계획한 하루."""

    day: int
    visits: list[LLMVisit]


class LLMPlan(BaseModel):
    """LLM 출력: 일정 계획."""

    title: str
    days: list[LLMDay]


class PlannedVisit(BaseModel):
    """시간 배치 전의 방문. 정리된 LLM 계획이나 기존 일정에서 만든다."""

    place_id: str
    slot: Slot
    reason: str
    evidence_review_ids: list[str] = Field(default_factory=list)
    changed: bool = False


def fmt_time(minutes: int) -> str:
    """분 → HH:MM."""
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def parse_time(text: str) -> int:
    """HH:MM → 분."""
    h, m = text.split(":")
    return int(h) * 60 + int(m)


def to_candidate(place_id: str, rank: int = 0) -> Candidate:
    """place_id로 후보 객체를 만든다."""
    place, trait = catalog.places()[place_id], catalog.traits()[place_id]
    return Candidate(
        **place.model_dump(),
        indoor=trait.indoor,
        price_level=trait.price_level,
        good_for=list(trait.good_for),
        not_good_for=list(trait.not_good_for),
        rank=rank,
    )


def render_plan_candidates(candidates: list[Candidate], summaries: dict[str, ReviewSummary]) -> str:
    """일정 계획용 후보 목록 텍스트."""
    lines = []
    for c in candidates:
        s = summaries.get(c.id)
        lines.append(
            f"[{c.id}] {c.name} | {c.category} | 실내={c.indoor} | 가격대={c.price_level} | "
            f"지역 {' '.join(c.address.split()[1:3])} ({c.lat:.3f},{c.lng:.3f}) | "
            f"장점 {', '.join(s.pros) if s else '-'} | 단점 {', '.join(s.cons) if s else '-'} | "
            f"후기id {', '.join(s.evidence_review_ids) if s else '-'}"
        )
    return "\n".join(lines)


def plan_days(
    request: TripRequest,
    candidates: list[Candidate],
    summaries: dict[str, ReviewSummary],
    weather: dict[str, Weather],
    day_numbers: list[int],
    issues: list[str] | None = None,
    note: str = "",
) -> LLMPlan:
    """LLM에게 지정한 일차들의 일정 계획을 요청한다."""
    system = BUILD_ITINERARY_SYSTEM.format(
        days=len(day_numbers),
        companions=request.companions or "미정",
        budget={1: "저렴하게", 2: "보통", 3: "여유롭게"}.get(request.budget or 0, "미정"),
        preferences=", ".join(request.preferences) or "없음",
    )
    if issues:
        system += BUILD_ITINERARY_RETRY.format(issues="\n".join(f"- {i}" for i in issues))
    if note:
        system += note
    start = date.fromisoformat(request.start_date) if request.start_date else None
    day_lines = []
    for n in day_numbers:
        w = weather.get((start + timedelta(days=n - 1)).isoformat()) if start else None
        day_lines.append(f"{n}일차 날씨: {w.condition if w else '정보 없음'}")
    user = "\n".join(day_lines) + "\n\n후보 장소:\n" + render_plan_candidates(candidates, summaries)
    return structured_call(LLMPlan, [SystemMessage(system), HumanMessage(user)], temperature=0.3)


def sanitize_visits(
    visits: list[LLMVisit],
    candidates: list[Candidate],
    summaries: dict[str, ReviewSummary],
    exclude_ids: set[str] | None = None,
) -> list[PlannedVisit]:
    """LLM 계획을 정리한다: 모르는 장소·중복 제거, 근거 후기 id 검증, 빈 이유는 요약으로 대체."""
    valid_ids = {c.id for c in candidates}
    seen: set[str] = set(exclude_ids or ())
    cleaned: list[PlannedVisit] = []
    for v in visits:
        if v.place_id not in valid_ids or v.place_id in seen:
            continue
        seen.add(v.place_id)
        evidence = catalog.positive_first(v.place_id, [i for i in v.evidence_review_ids if i in catalog.review_ids(v.place_id)])
        summary = summaries.get(v.place_id)
        if not evidence and summary:
            evidence = summary.evidence_review_ids[:1]
        reason = v.reason.strip()
        if not reason and summary and summary.pros:
            reason = f"후기에서 '{summary.pros[0]}'라는 평이 있어요."
        cleaned.append(PlannedVisit(place_id=v.place_id, slot=v.slot, reason=reason, evidence_review_ids=evidence[:2]))
    return cleaned


def schedule_day(planned: list[PlannedVisit]) -> list[Visit]:
    """슬롯 순서대로 방문을 놓고, 같은 슬롯 안에서는 가까운 순으로 정렬해 시간과 이동시간을 계산한다."""
    all_places = catalog.places()
    ordered: list[PlannedVisit] = []
    last_coord: tuple[float, float] | None = None
    for slot in SLOT_ORDER:
        group = [p for p in planned if p.slot == slot]
        group = order_nearest(group, lambda p: (all_places[p.place_id].lat, all_places[p.place_id].lng), last_coord)
        ordered.extend(group)
        if group:
            last = all_places[group[-1].place_id]
            last_coord = (last.lat, last.lng)

    visits: list[Visit] = []
    cursor = 0
    prev: tuple[float, float] | None = None
    for p in ordered:
        place = all_places[p.place_id]
        coord = (place.lat, place.lng)
        travel = travel_minutes(prev, coord) if prev else 0
        start = max(cursor + travel, SLOT_START_MIN[p.slot])
        end = start + DURATION_MIN[place.category]
        visits.append(
            Visit(
                place_id=p.place_id,
                start=fmt_time(start),
                end=fmt_time(end),
                travel_minutes_from_prev=travel,
                reason=p.reason,
                evidence_review_ids=p.evidence_review_ids,
                changed=p.changed,
                slot=p.slot,
            )
        )
        cursor, prev = end, coord
    return visits


def day_weather(visits: list[Visit], day_date: str, state: PlannerState) -> Weather | None:
    """그날 방문지가 가장 많은 읍면동의 날씨. 그 구역 날씨가 없으면 시 단위, 그것도 없으면 계획에 쓴 날씨로 대신한다."""
    by_area = state.get("area_weather", {})
    places = [catalog.places()[v.place_id] for v in visits]
    for key in (catalog.weather_zone_of, catalog.area_of):
        counts = Counter(key(p) for p in places)
        top = counts.most_common(1)[0][0] if counts else None
        found = by_area.get(top, {}).get(day_date) if top else None
        if found:
            return found
    return state.get("weather", {}).get(day_date)


def refresh_weather(itinerary: Itinerary, state: PlannerState) -> Itinerary:
    """부분 수정으로 방문지가 바뀐 뒤, 각 일차의 날씨를 지금 방문지 기준으로 다시 붙인다."""
    days = [d.model_copy(update={"weather": day_weather(d.visits, d.date, state) or d.weather}) for d in itinerary.days]
    return itinerary.model_copy(update={"days": days})


def to_planned(visits: list[Visit]) -> list[PlannedVisit]:
    """기존 일정의 방문을 다시 배치할 수 있는 형태로 바꾼다 (changed는 초기화)."""
    return [
        PlannedVisit(
            place_id=v.place_id,
            slot=v.slot or "afternoon",
            reason=v.reason,
            evidence_review_ids=v.evidence_review_ids,
        )
        for v in visits
    ]
