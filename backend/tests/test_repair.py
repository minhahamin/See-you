"""부분 수리(repair): 실패한 검증 항목만 고치고 나머지는 그대로 두는지 테스트."""
from agent import catalog
from agent.nodes.repair_itinerary import repair_itinerary
from agent.nodes.validate_itinerary import parse_hours, run_checks
from agent.planning import PlannedVisit, parse_time, schedule_day, to_candidate
from agent.repair import Context, repair_itinerary_plan
from agent.review_tools import fallback_summary
from agent.state import DayPlan, Itinerary, TripRequest, Weather


def _ctx(**req) -> Context:
    """모든 장소가 후보이고 대체 요약을 가진 수리 문맥."""
    cands = [to_candidate(pid, i) for i, pid in enumerate(sorted(catalog.places()))]
    request = TripRequest(start_date="2026-11-14", days=1, companions="커플", **req)
    return Context(request, cands, {c.id: fallback_summary(c) for c in cands})


def _visit(ctx: Context, place_id: str, slot: str) -> PlannedVisit:
    s = ctx.summaries[place_id]
    return PlannedVisit(place_id=place_id, slot=slot, reason=f"후기에서 '{s.pros[0]}'라는 평이 있어요.", evidence_review_ids=s.evidence_review_ids[:1])


def _itinerary(ctx: Context, days: list[list[tuple[str, str]]], weather: list[str | None] | None = None) -> Itinerary:
    plans = []
    for n, items in enumerate(days, 1):
        w = weather[n - 1] if weather else None
        plans.append(
            DayPlan(
                day=n,
                date=f"2026-11-{13 + n}",
                weather=Weather(condition=w, temp_max=20, temp_min=12) if w else None,
                visits=schedule_day([_visit(ctx, pid, slot) for pid, slot in items]),
            )
        )
    return Itinerary(title="t", region="제주", companions="커플", days=plans)


def _ids(ctx: Context, category: str, area: str | None = None, n: int = 3) -> list[str]:
    found = [
        c.id for c in ctx.candidates
        if c.category == category and (area is None or catalog.area_of(catalog.places()[c.id]) == area)
    ]
    return found[:n]


def _clean_day(ctx: Context, avoid: set[str] = frozenset(), area: str | None = None) -> list[tuple[str, str]]:
    """검증 위반이 하나도 없는 하루(관광지 2·음식점 1·카페 1)를 데이터에서 찾는다."""
    sights, foods, cafes = (_ids(ctx, c, area, 99) for c in ("관광지", "음식점", "카페"))
    ok = lambda ids: not (set(ids) & avoid)  # noqa: E731
    for f in filter(ok, foods):
        for c in filter(ok, cafes):
            for i, a in enumerate(filter(ok, sights)):
                for b in filter(ok, sights[i + 1 :]):
                    day = [(a, "morning"), (f, "lunch"), (b, "afternoon"), (c, "cafe")]
                    it = _itinerary(ctx, [day])
                    if all(c_.ok for c_ in run_checks(it, ctx.request, ctx.summaries)):
                        return day
    raise AssertionError("위반 없는 하루를 데이터에서 찾지 못했다")


def _failed(it: Itinerary, ctx: Context, kind: str) -> list:
    return [c for c in run_checks(it, ctx.request, ctx.summaries) if not c.ok and c.kind == kind]


def test_valid_itinerary_is_left_untouched() -> None:
    """검증을 통과한 일정은 수리하지 않는다."""
    ctx = _ctx()
    it = _itinerary(ctx, [_clean_day(ctx)])
    assert repair_itinerary_plan(it, ctx) == it

def test_missing_meal_and_sight_are_inserted_nearby() -> None:
    """식사와 관광지가 빠진 날에 음식점·관광지를 넣어 해당 검증을 통과시킨다."""
    ctx = _ctx()
    cafes = _ids(ctx, "카페", n=3)
    it = _itinerary(ctx, [[(cafes[0], "morning"), (cafes[1], "afternoon"), (cafes[2], "cafe")]])
    assert _failed(it, ctx, "no_meal") and _failed(it, ctx, "no_sight")

    fixed = repair_itinerary_plan(it, ctx)
    assert not _failed(fixed, ctx, "no_meal") and not _failed(fixed, ctx, "no_sight") and not _failed(fixed, ctx, "few_visits")
    assert not _failed(fixed, ctx, "duplicate")


def test_place_outside_requested_area_is_replaced_by_same_category() -> None:
    """요청한 구역 밖 장소는 같은 분류의 구역 안 장소로 바뀐다."""
    ctx = _ctx(area="서귀포시")
    sights = _ids(ctx, "관광지", "서귀포시", 2)
    food, cafe = _ids(ctx, "음식점", "서귀포시", 1)[0], _ids(ctx, "카페", "서귀포시", 1)[0]
    outside = _ids(ctx, "관광지", "제주시", 1)[0]
    it = _itinerary(ctx, [[(outside, "morning"), (food, "lunch"), (sights[0], "afternoon"), (cafe, "cafe")]])
    assert _failed(it, ctx, "area")

    fixed = repair_itinerary_plan(it, ctx)
    after = [v.place_id for v in fixed.days[0].visits]
    assert not _failed(fixed, ctx, "area") and outside not in after
    assert [catalog.places()[p].category for p in after] == ["관광지", "음식점", "관광지", "카페"]

def test_hours_violation_is_fixed_by_shifting_time() -> None:
    """영업시간 전에 시작하는 방문은 장소를 바꾸지 않고 시간만 영업시간 안으로 옮긴다."""
    ctx = _ctx()
    late_open = next(
        p for p in _ids(ctx, "관광지", n=99) if (h := parse_hours(catalog.places()[p].opening_hours)) and h[0] > 9 * 60 and h[1] - h[0] >= 180
    )
    others = [p for p in _ids(ctx, "관광지", n=99) if p != late_open]
    food, cafe = _ids(ctx, "음식점", n=1)[0], _ids(ctx, "카페", n=1)[0]
    it = _itinerary(ctx, [[(late_open, "morning"), (food, "lunch"), (others[0], "afternoon"), (cafe, "cafe")]])
    assert any(c.place_id == late_open for c in _failed(it, ctx, "hours"))

    fixed = repair_itinerary_plan(it, ctx)
    visit = next(v for v in fixed.days[0].visits if v.place_id == late_open)
    assert not any(c.place_id == late_open for c in _failed(fixed, ctx, "hours"))
    assert parse_time(visit.start) >= parse_hours(catalog.places()[late_open].opening_hours)[0]


def test_rain_day_outdoor_sights_are_swapped_for_indoor() -> None:
    """비 오는 날 야외 관광지가 상한을 넘으면 실내 관광지로 바꾼다."""
    ctx = _ctx()
    outdoor = [p for p in _ids(ctx, "관광지", n=99) if not catalog.traits()[p].indoor][:3]
    food, cafe = _ids(ctx, "음식점", n=1)[0], _ids(ctx, "카페", n=1)[0]
    it = _itinerary(ctx, [[(outdoor[0], "morning"), (food, "lunch"), (outdoor[1], "afternoon"), (outdoor[2], "afternoon"), (cafe, "cafe")]], ["rain"])
    assert _failed(it, ctx, "rain_outdoor")

    fixed = repair_itinerary_plan(it, ctx)
    assert not _failed(fixed, ctx, "rain_outdoor")


def test_repair_changes_only_the_failing_day() -> None:
    """위반이 없는 날은 수리 뒤에도 그대로이고, 식사가 빠진 날에는 식사가 채워진다."""
    ctx = _ctx()
    first = _clean_day(ctx)  # 1일 기준으로 위반 없는 하루를 찾은 뒤 2일 일정으로 쓴다
    ctx = ctx._replace(request=ctx.request.model_copy(update={"days": 2}))
    taken = {p for p, _ in first}
    rest = [c for c in ctx.candidates if c.id not in taken and c.category in ("관광지", "카페")]
    second = [(c.id, slot) for c, slot in zip(rest, ("morning", "afternoon", "cafe"))]
    it = _itinerary(ctx, [first, second])
    assert _failed(it, ctx, "no_meal")

    fixed = repair_itinerary_plan(it, ctx)
    assert fixed.days[0] == it.days[0]
    assert not _failed(fixed, ctx, "no_meal")

def test_node_uses_up_retry_budget_and_never_calls_llm(fake_llm) -> None:
    """수리 노드는 LLM 없이 동작하고, 한 번 실행하면 재시도 한도를 모두 쓴 것으로 기록한다."""
    ctx = _ctx()
    cafes = _ids(ctx, "카페", n=3)
    it = _itinerary(ctx, [[(cafes[0], "morning"), (cafes[1], "afternoon"), (cafes[2], "cafe")]])
    out = repair_itinerary({"itinerary": it, "request": ctx.request, "candidates": ctx.candidates, "review_summaries": ctx.summaries})
    assert out["retry_count"] == 2 and out["itinerary"] != it
