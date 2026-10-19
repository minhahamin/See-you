"""일정 부분 수리: 검증에서 실패한 항목만 규칙으로 고친다. LLM을 쓰지 않으므로 같은 입력이면 같은 결과가 나온다.

전체를 다시 생성하면 멀쩡하던 곳에서 새 위반이 생기므로, 위반 종류마다 해당 부분만 바꾼다.
- 구역·예산·동행·중복·우천 야외: 그 장소만 같은 분류의 적합한 후보로 교체
- 식사·관광지·방문 수 부족: 하루 동선 중심에서 가까운 적합 후보를 삽입
- 이동 과다: 이동이 가장 줄어드는 교체를 최대 몇 번 시도
- 영업시간: 시간만 영업시간 안으로 옮기고, 그래도 안 되면 그 장소를 교체
- 근거 없음: 후기 요약에서 이유와 근거 후기 id를 다시 붙임
"""
import logging
from typing import NamedTuple

from agent import catalog
from agent.moving import MoveError, relayout
from agent.nodes.validate_itinerary import (
    MAX_DAY_TRAVEL_MIN,
    MAX_LEG_MIN,
    MAX_OUTDOOR_SIGHTS_WHEN_RAIN,
    MIN_VISITS_PER_DAY,
    Check,
    parse_hours,
    run_checks,
)
from agent.planning import DURATION_MIN, SLOT_START_MIN, PlannedVisit, fmt_time, parse_time, schedule_day, to_planned
from agent.review_tools import fallback_summary
from agent.state import Candidate, DayPlan, Itinerary, ReviewSummary, Slot, TripRequest, Visit
from models import Category
from tools.route import haversine_km

logger = logging.getLogger(__name__)

MAX_PASSES = 3  # 수리 → 재검증을 이만큼 반복한다
MAX_TRAVEL_SWAPS = 3  # 하루 이동을 줄이려고 교체해 보는 최대 횟수
# 방문 수가 모자랄 때 채울 (분류, 시간대) 후보. 하루에 아직 없는 시간대부터 채운다.
# 분류별로 놓을 수 있는 시간대 (영업시간 때문에 하루 중 순서를 바꿀 때 이 안에서만 옮긴다)
SLOTS_BY_CATEGORY: dict[Category, list[Slot]] = {
    "관광지": ["morning", "afternoon", "cafe"],
    "카페": ["afternoon", "cafe"],
    "음식점": ["lunch", "dinner"],
    "숙소": ["stay"],
}
FILL_ORDER: list[tuple[Category, Slot]] = [("관광지", "afternoon"), ("카페", "cafe"), ("음식점", "lunch"), ("관광지", "morning"), ("음식점", "dinner")]


class Context(NamedTuple):
    """수리에 필요한 조건·후보·후기 요약."""

    request: TripRequest
    candidates: list[Candidate]
    summaries: dict[str, ReviewSummary]
    protected: frozenset[str] = frozenset()  # 사용자가 직접 요청해 수리가 바꾸면 안 되는 장소


def _coord(place_id: str) -> tuple[float, float]:
    """장소 좌표 (lat, lng)."""
    p = catalog.places()[place_id]
    return p.lat, p.lng


def _category(place_id: str) -> Category:
    """장소 분류."""
    return catalog.places()[place_id].category


def _summary(c: Candidate, ctx: Context) -> ReviewSummary:
    """후보의 후기 요약. 없으면 특성 기반 요약으로 대신한다."""
    return ctx.summaries.get(c.id) or fallback_summary(c)


def _fits_hours(place_id: str, slot: Slot) -> bool:
    """영업시간이 하나로 명확할 때, 그 시간대 시작 시각의 방문이 영업시간 안에 드는지 (모호하면 True)."""
    hours = parse_hours(catalog.places()[place_id].opening_hours)
    if not hours:
        return True
    start = SLOT_START_MIN[slot]
    return hours[0] <= start and start + DURATION_MIN[_category(place_id)] <= hours[1]


def _planned_for(c: Candidate, slot: Slot, ctx: Context) -> PlannedVisit | None:
    """후보로 방문을 만든다. 추천 이유나 근거 후기가 없으면 None."""
    s = _summary(c, ctx)
    if not s.pros or not s.evidence_review_ids:
        return None
    return PlannedVisit(place_id=c.id, slot=slot, reason=f"후기에서 '{s.pros[0]}'라는 평이 있어요.", evidence_review_ids=s.evidence_review_ids[:2])


def _eligible(c: Candidate, ctx: Context, used: set[str], category: Category, indoor_only: bool) -> bool:
    """후보가 조건(구역·예산·동행·중복·우천)을 모두 만족하는지."""
    req = ctx.request
    if c.category != category or (category != "숙소" and c.id in used):
        return False
    if req.area and catalog.area_of(catalog.places()[c.id]) != req.area:
        return False
    if req.budget is not None and c.price_level > req.budget:
        return False
    if indoor_only and not c.indoor:
        return False
    summary = ctx.summaries.get(c.id)
    return summary is None or summary.suitable


def _center(planned: list[PlannedVisit], skip: int | None = None) -> tuple[float, float] | None:
    """하루 동선의 중심 (숙소·제외한 방문을 뺀 좌표 평균)."""
    pts = [_coord(p.place_id) for i, p in enumerate(planned) if i != skip and _category(p.place_id) != "숙소"]
    return (sum(a for a, _ in pts) / len(pts), sum(b for _, b in pts) / len(pts)) if pts else None


def _pick(
    ctx: Context, used: set[str], category: Category, slot: Slot, near: tuple[float, float] | None, indoor_only: bool = False
) -> PlannedVisit | None:
    """조건을 만족하는 후보 중 영업시간이 맞고 기준점에 가장 가까운 것."""
    pool = [c for c in ctx.candidates if _eligible(c, ctx, used, category, indoor_only)]
    pool.sort(key=lambda c: (not _fits_hours(c.id, slot), haversine_km(*near, c.lat, c.lng) if near else 0.0, c.rank))
    return next((p for c in pool if (p := _planned_for(c, slot, ctx))), None)


def _swap(planned: list[PlannedVisit], i: int, new: PlannedVisit, used: set[str]) -> None:
    """i번째 방문을 새 방문으로 바꾸고 사용한 장소 목록을 갱신한다."""
    used.discard(planned[i].place_id)
    used.add(new.place_id)
    planned[i] = new


def _travel_score(planned: list[PlannedVisit]) -> tuple[int, int]:
    """(이동 상한 초과량, 총 이동시간). 작을수록 좋다."""
    legs = [v.travel_minutes_from_prev for v in schedule_day(planned)]
    return max(0, sum(legs) - MAX_DAY_TRAVEL_MIN) + max(0, max(legs, default=0) - MAX_LEG_MIN), sum(legs)


def _reduce_travel(planned: list[PlannedVisit], ctx: Context, used: set[str], indoor_only: bool) -> bool:
    """이동이 가장 크게 줄어드는 교체를 상한 안에 들 때까지 반복한다. 하나라도 바꿨으면 True."""
    changed = False
    for _ in range(MAX_TRAVEL_SWAPS):
        best, best_score = None, _travel_score(planned)
        if best_score[0] == 0:
            break
        for i, p in enumerate(planned):
            cat = _category(p.place_id)
            if p.place_id in ctx.protected:
                continue
            for c in ctx.candidates:
                if c.id == p.place_id or not _eligible(c, ctx, used, cat, indoor_only and cat == "관광지"):
                    continue
                new = _planned_for(c, p.slot, ctx)
                if not new or not _fits_hours(c.id, p.slot):
                    continue
                trial = [*planned[:i], new, *planned[i + 1 :]]
                if (score := _travel_score(trial)) < best_score:
                    best, best_score, best_i = trial, score, i
        if best is None:
            break
        _swap(planned, best_i, best[best_i], used)
        changed = True
    return changed


def _shift_into_hours(visits: list[Visit]) -> tuple[list[Visit], set[str]]:
    """영업시간을 벗어난 방문의 시간만 영업시간 안으로 옮기고 뒤 일정을 민다. (결과, 그래도 못 맞춘 장소 id)."""
    wanted: list[int] = []
    for v in visits:
        start, end = parse_time(v.start), parse_time(v.end)
        hours = parse_hours(catalog.places()[v.place_id].opening_hours)
        if hours and start < hours[0]:
            start = hours[0]
        elif hours and end > hours[1] and hours[1] - (end - start) >= hours[0]:
            start = hours[1] - (end - start)
        wanted.append(start)
    try:
        moved = relayout(visits, wanted)
    except MoveError:
        moved = visits
    stuck = {
        v.place_id
        for v in moved
        if (h := parse_hours(catalog.places()[v.place_id].opening_hours)) and not (h[0] <= parse_time(v.start) and parse_time(v.end) <= h[1])
    }
    return moved, stuck


def _reorder_for_hours(visits: list[Visit], stuck: set[str]) -> tuple[list[Visit], set[str]]:
    """시간만으로 영업시간을 못 맞춘 방문을 하루 중 다른 시간대로 옮겨 본다. 못 맞춘 방문이 가장 적어지는 배치를 쓴다."""
    best, best_stuck = visits, stuck
    for place_id in sorted(stuck):
        for slot in SLOTS_BY_CATEGORY[_category(place_id)]:
            plans = [p.model_copy(update={"slot": slot}) if p.place_id == place_id else p for p in to_planned(best)]
            trial, trial_stuck = _shift_into_hours(schedule_day(plans))
            if len(trial_stuck) < len(best_stuck):
                best, best_stuck = trial, trial_stuck
    return best, best_stuck


def _repair_once(itinerary: Itinerary, failed: list[Check], ctx: Context) -> Itinerary:
    """실패한 항목을 한 번 고친 일정을 돌려준다. 고칠 수 있는 게 없으면 같은 일정."""
    planned = {d.day: to_planned(d.visits) for d in itinerary.days}
    rainy = {d.day: bool(d.weather and d.weather.condition == "rain") for d in itinerary.days}
    used = {p.place_id for plans in planned.values() for p in plans if _category(p.place_id) != "숙소"}
    touched: set[int] = set()

    def replace_place(day: int, place_id: str, force_slot: bool = False) -> None:
        """하루 안의 한 장소를 같은 분류의 적합한 후보로 바꾼다. 없으면 그대로 둔다."""
        plans = planned[day]
        i = next((k for k, p in enumerate(plans) if p.place_id == place_id), None)
        if i is None or place_id in ctx.protected:
            return
        cat = _category(place_id)
        new = _pick(ctx, used, cat, plans[i].slot, _center(plans, skip=i), indoor_only=rainy[day] and cat == "관광지")
        if new:
            _swap(plans, i, new, used)
            touched.add(day)

    def insert(day: int, category: Category, slot: Slot) -> bool:
        """하루 동선 중심에서 가까운 적합 후보를 넣는다."""
        plans = planned[day]
        new = _pick(ctx, used, category, slot, _center(plans), indoor_only=rainy[day] and category == "관광지")
        if not new:
            return False
        plans.append(new)
        used.add(new.place_id)
        touched.add(day)
        return True

    by_kind = lambda kind: [c for c in failed if c.kind == kind]  # noqa: E731

    # 1) 조건에 맞지 않는 장소 교체
    for c in by_kind("area") + by_kind("unsuitable") + by_kind("budget"):
        replace_place(c.day, c.place_id)
    seen: set[str] = set()
    for day in sorted(planned):
        for p in list(planned[day]):
            if _category(p.place_id) == "숙소":
                continue
            if p.place_id in seen:
                replace_place(day, p.place_id)
                if p in planned[day]:  # 대체할 후보가 없으면 중복을 빼는 편이 낫다
                    planned[day].remove(p)
                    touched.add(day)
            seen.add(p.place_id)
    for c in by_kind("rain_outdoor"):
        outdoor = [p for p in planned[c.day] if _category(p.place_id) == "관광지" and not catalog.traits()[p.place_id].indoor]
        for p in outdoor[MAX_OUTDOOR_SIGHTS_WHEN_RAIN:]:
            replace_place(c.day, p.place_id)

    # 2) 빠진 것 채우기
    for c in by_kind("no_meal"):
        insert(c.day, "음식점", "lunch")
    for c in by_kind("no_sight"):
        insert(c.day, "관광지", "afternoon")
    for c in by_kind("few_visits"):
        for category, slot in FILL_ORDER:
            non_stay = [p for p in planned[c.day] if _category(p.place_id) != "숙소"]
            if len(non_stay) >= MIN_VISITS_PER_DAY:
                break
            if not any(p.slot == slot for p in planned[c.day]):
                insert(c.day, category, slot)

    # 3) 이동 줄이기
    for c in by_kind("travel"):
        if _reduce_travel(planned[c.day], ctx, used, rainy[c.day]):
            touched.add(c.day)

    # 4) 바뀐 날을 다시 배치하고 영업시간에 맞춘다
    fix_hours_days = touched | {c.day for c in by_kind("hours")}
    days: list[DayPlan] = []
    for d in itinerary.days:
        visits = schedule_day(planned[d.day]) if d.day in touched else d.visits
        if d.day in fix_hours_days:
            visits, stuck = _shift_into_hours(visits)
            for place_id in stuck:  # 시간만으로 안 되면 그 장소를 교체하고 다시 맞춘다
                if place_id in ctx.protected:
                    continue
                plans = to_planned(visits)
                i = next(k for k, p in enumerate(plans) if p.place_id == place_id)
                new = _pick(ctx, used, _category(place_id), plans[i].slot, _center(plans, skip=i), indoor_only=rainy[d.day] and _category(place_id) == "관광지")
                if new:
                    _swap(plans, i, new, used)
                    visits, stuck = _shift_into_hours(schedule_day(plans))
            if stuck:  # 바꿀 후보도 없으면 하루 중 더 이른(또는 늦은) 시간대로 옮긴다
                visits, _ = _reorder_for_hours(visits, stuck)
        days.append(d.model_copy(update={"visits": visits}))

    # 5) 근거 다시 붙이기
    valid_pairs = {(c.day, c.place_id) for c in by_kind("grounding")}
    for d in days:
        for i, v in enumerate(d.visits):
            if (d.day, v.place_id) in valid_pairs:
                cand = next((c for c in ctx.candidates if c.id == v.place_id), None)
                new = _planned_for(cand, v.slot or "afternoon", ctx) if cand else None
                if new:
                    d.visits[i] = v.model_copy(update={"reason": new.reason, "evidence_review_ids": new.evidence_review_ids})
    return itinerary.model_copy(update={"days": days})


def repair_itinerary_plan(itinerary: Itinerary, ctx: Context) -> Itinerary:
    """검증 → 수리를 더 고칠 게 없거나 MAX_PASSES번이 될 때까지 반복해 수리된 일정을 돌려준다."""
    current = itinerary
    for n in range(MAX_PASSES):
        failed = [c for c in run_checks(current, ctx.request, ctx.summaries) if not c.ok]
        if not failed:
            break
        repaired = _repair_once(current, failed, ctx)
        remaining = sum(not c.ok for c in run_checks(repaired, ctx.request, ctx.summaries))
        if repaired == current or remaining >= len(failed):  # 변화가 없거나 나아지지 않으면 이전 일정을 지킨다
            break
        logger.info("부분 수리 %d회차: 실패 %d건 처리", n + 1, len(failed))
        current = repaired
    return current


__all__ = ["Context", "repair_itinerary_plan", "fmt_time"]
