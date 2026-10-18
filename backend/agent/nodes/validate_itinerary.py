"""일정 검증 노드: 이동 과다, 영업시간 충돌, 조건 위반, 근거 없는 추천을 규칙으로 검사한다."""
import logging
import re
from typing import NamedTuple

from agent import catalog
from agent.planning import parse_time
from agent.state import Itinerary, PlannerState, ReviewSummary, TripRequest, Validation

logger = logging.getLogger(__name__)

MAX_LEG_MIN = 60  # 한 번의 이동 상한
MAX_DAY_TRAVEL_MIN = 180  # 하루 총 이동 상한
MIN_VISITS_PER_DAY = 3  # 숙소를 뺀 하루 최소 방문 수
MIN_SIGHTS_PER_DAY = 1  # 하루 최소 관광지 수 (식사·카페만으로 채우지 않게)
DAY_START_MIN, DAY_END_MIN = 8 * 60, 22 * 60
MAX_OUTDOOR_SIGHTS_WHEN_RAIN = 1  # 비 오는 날 야외 관광지 상한

_RANGE = re.compile(r"(\d{1,2}):(\d{2})\s*[~\-–]\s*(\d{1,2}):(\d{2})")


class Check(NamedTuple):
    """검증 항목 하나의 결과. 실패했을 때만 message를 재생성 프롬프트에 쓴다."""

    ok: bool
    message: str


def parse_hours(text: str | None) -> tuple[int, int] | None:
    """영업시간 문자열에서 시간대가 하나로 명확할 때만 (열기, 닫기) 분을 반환한다. 모호하면 None."""
    if not text:
        return None
    ranges = _RANGE.findall(text)
    if len(ranges) != 1:
        return None
    h1, m1, h2, m2 = map(int, ranges[0])
    open_, close = h1 * 60 + m1, h2 * 60 + m2
    return (open_, close) if close > open_ else None


def _day_checks(day, summaries: dict[str, ReviewSummary]) -> list[Check]:
    """하루 단위 검사: 방문 수, 이동시간, 시간대, 우천 시 실내 비중."""
    all_places = catalog.places()
    traits = catalog.traits()
    non_stay = [v for v in day.visits if all_places[v.place_id].category != "숙소"]
    checks = [
        Check(
            len(non_stay) >= MIN_VISITS_PER_DAY,
            f"{day.day}일차 방문 장소가 {len(non_stay)}곳뿐입니다. 최소 {MIN_VISITS_PER_DAY}곳을 넣으세요.",
        )
    ]
    sights = [v for v in non_stay if all_places[v.place_id].category == "관광지"]
    checks.append(
        Check(
            len(sights) >= MIN_SIGHTS_PER_DAY,
            f"{day.day}일차에 관광지가 없습니다. 관광지를 {MIN_SIGHTS_PER_DAY}곳 이상 넣으세요.",
        )
    )
    has_meal = any(all_places[v.place_id].category == "음식점" for v in day.visits)
    checks.append(Check(has_meal, f"{day.day}일차에 식사(음식점)가 없습니다. 점심 식사를 넣으세요."))
    legs = [v.travel_minutes_from_prev for v in day.visits]
    total, longest = sum(legs), max(legs, default=0)
    checks.append(
        Check(
            total <= MAX_DAY_TRAVEL_MIN and longest <= MAX_LEG_MIN,
            f"{day.day}일차 이동이 과합니다(총 {total}분, 최장 {longest}분). 가까운 장소끼리 묶으세요.",
        )
    )
    if day.visits:
        first, last = parse_time(day.visits[0].start), parse_time(day.visits[-1].end)
        checks.append(
            Check(
                first >= DAY_START_MIN and last <= DAY_END_MIN,
                f"{day.day}일차 일정이 {day.visits[0].start}~{day.visits[-1].end}로 08:00~22:00을 벗어납니다.",
            )
        )
    if day.weather and day.weather.condition == "rain":
        outdoor = [v for v in day.visits if all_places[v.place_id].category == "관광지" and not traits[v.place_id].indoor]
        checks.append(
            Check(
                len(outdoor) <= MAX_OUTDOOR_SIGHTS_WHEN_RAIN,
                f"{day.day}일차는 비 예보인데 야외 관광지가 {len(outdoor)}곳입니다. 실내 장소로 바꾸세요.",
            )
        )
    return checks


def _visit_checks(day_no: int, visit, request: TripRequest, summaries: dict[str, ReviewSummary]) -> list[Check]:
    """방문 단위 검사: 영업시간, 근거, 예산·동행 적합성."""
    place = catalog.places()[visit.place_id]
    trait = catalog.traits()[visit.place_id]
    label = f"{day_no}일차 {place.name}"
    checks: list[Check] = []

    hours = parse_hours(place.opening_hours)
    if hours:
        start, end = parse_time(visit.start), parse_time(visit.end)
        checks.append(
            Check(
                hours[0] <= start and end <= hours[1],
                f"{label}: 방문 시간 {visit.start}~{visit.end}이 영업시간({place.opening_hours})을 벗어납니다.",
            )
        )

    valid = catalog.review_ids(visit.place_id)
    grounded = bool(visit.reason.strip()) and bool(visit.evidence_review_ids) and all(
        i in valid for i in visit.evidence_review_ids
    )
    checks.append(Check(grounded, f"{label}: 추천 이유에 근거가 되는 후기가 없거나 올바르지 않습니다."))

    summary = summaries.get(visit.place_id)
    within_budget = request.budget is None or trait.price_level <= request.budget
    suitable = summary is None or summary.suitable
    checks.append(
        Check(
            within_budget and suitable,
            f"{label}: "
            + ("예산(가격대)을 넘습니다." if not within_budget else f"동행 조건에 맞지 않습니다({summary.exclude_reason})."),
        )
    )
    return checks


def run_checks(itinerary: Itinerary, request: TripRequest, summaries: dict[str, ReviewSummary]) -> list[Check]:
    """일정 전체의 모든 검증 항목을 실행한다."""
    all_places = catalog.places()
    checks = [
        Check(
            len(itinerary.days) == (request.days or len(itinerary.days)),
            f"일정이 {len(itinerary.days)}일치입니다. {request.days}일 일정이어야 합니다.",
        )
    ]
    seen: set[str] = set()
    duplicates: set[str] = set()
    for day in itinerary.days:
        for v in day.visits:
            if all_places[v.place_id].category != "숙소":
                (duplicates if v.place_id in seen else seen).add(v.place_id)
        checks.extend(_day_checks(day, summaries))
        for v in day.visits:
            checks.extend(_visit_checks(day.day, v, request, summaries))
    names = ", ".join(all_places[p].name for p in sorted(duplicates))
    checks.append(Check(not duplicates, f"같은 장소가 반복됩니다: {names}"))
    return checks


def validate_itinerary(state: PlannerState) -> dict:
    """검증 결과를 일정의 validation과 validation_issues에 기록한다."""
    itinerary = state["itinerary"]
    checks = run_checks(itinerary, state["request"], state.get("review_summaries", {}))
    issues = [c.message for c in checks if not c.ok]
    validated = itinerary.model_copy(update={"validation": Validation(passed=len(checks) - len(issues), total=len(checks))})
    logger.info("검증 %d/%d 통과, 문제 %d건", validated.validation.passed, validated.validation.total, len(issues))
    return {"itinerary": validated, "validation_issues": issues}
