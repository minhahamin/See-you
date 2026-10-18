"""build_itinerary, validate_itinerary, 시간 배치(schedule_day) 단위 테스트."""
from agent import catalog
from agent.nodes.build_itinerary import build_itinerary
from agent.nodes.validate_itinerary import parse_hours, validate_itinerary
from agent.planning import LLMPlan, PlannedVisit, plan_days, schedule_day, to_candidate
from agent.review_tools import fallback_summary
from agent.state import DayPlan, Itinerary, TripRequest, Visit, Weather

from tests.conftest import plan_from_prompt


def _state(days: int = 2, **req) -> dict:
    """모든 후보와 대체 요약을 가진 테스트용 상태."""
    request = TripRequest(start_date="2026-11-14", days=days, companions="커플", **req)
    cands = [to_candidate(pid, i) for i, pid in enumerate(sorted(catalog.places()))]
    return {
        "request": request,
        "candidates": cands,
        "review_summaries": {c.id: fallback_summary(c) for c in cands},
        "weather": {},
    }


def test_schedule_day_orders_by_slot_and_adds_travel() -> None:
    """슬롯 순서대로 놓이고 첫 방문 이동시간은 0, 이후는 양수이며 시간이 겹치지 않는다."""
    state = _state()
    by_cat = lambda c: [x.id for x in state["candidates"] if x.category == c]  # noqa: E731
    planned = [
        PlannedVisit(place_id=by_cat("카페")[0], slot="cafe", reason="r"),
        PlannedVisit(place_id=by_cat("관광지")[0], slot="morning", reason="r"),
        PlannedVisit(place_id=by_cat("음식점")[0], slot="lunch", reason="r"),
    ]
    visits = schedule_day(planned)
    assert [v.slot for v in visits] == ["morning", "lunch", "cafe"]
    assert visits[0].travel_minutes_from_prev == 0 and visits[1].travel_minutes_from_prev > 0
    assert all(a.end <= b.start for a, b in zip(visits, visits[1:]))  # HH:MM 문자열 비교


def test_build_itinerary_node(fake_llm) -> None:
    """LLM 계획이 일자별 시간표가 되고 중복 없이 일수만큼 만들어진다."""
    fake_llm[LLMPlan] = plan_from_prompt
    out = build_itinerary(_state(days=2))
    itin = out["itinerary"]
    assert [d.day for d in itin.days] == [1, 2] and itin.days[1].date == "2026-11-15"
    assert out["retry_count"] == 0
    ids = [v.place_id for d in itin.days for v in d.visits if catalog.places()[v.place_id].category != "숙소"]
    assert len(ids) == len(set(ids))


def test_build_itinerary_drops_unknown_places_and_counts_retry(fake_llm) -> None:
    """후보에 없는 장소는 버리고, 검증 문제가 있었으면 재시도 횟수를 올리며 문제를 프롬프트에 넣는다."""
    seen: dict = {}

    def handler(msgs: list) -> LLMPlan:
        seen["system"] = msgs[0].content
        plan = plan_from_prompt(msgs)
        plan.days[0].visits[0].place_id = "9999999"
        return plan

    fake_llm[LLMPlan] = handler
    state = {**_state(days=1), "validation_issues": ["1일차 이동이 과합니다"], "retry_count": 1}
    out = build_itinerary(state)
    assert out["retry_count"] == 2
    assert "1일차 이동이 과합니다" in seen["system"]
    assert "9999999" not in [v.place_id for v in out["itinerary"].days[0].visits]


def test_parse_hours_only_for_unambiguous_ranges() -> None:
    """시간대가 하나로 명확할 때만 파싱하고, 계절별 등 모호하면 None."""
    assert parse_hours("09:00~18:00 (입장 마감 17:00)") == (540, 1080)
    assert parse_hours("[하절기] 10:00~18:00 [동절기] 09:30~17:30") is None
    assert parse_hours("상시 개방") is None and parse_hours(None) is None


def _itinerary(visits: list[Visit], weather: Weather | None = None) -> Itinerary:
    return Itinerary(title="t", region="제주", companions="커플", days=[DayPlan(day=1, date="2026-11-14", weather=weather, visits=visits)])


def test_validate_generated_plan_only_flags_travel_and_hours(fake_llm) -> None:
    """테스트용 계획은 장소를 지리적으로 묶지도 영업시간을 보지도 않으므로, 이동 과다와 영업시간 외의 문제(근거·중복·식사)는 없어야 한다."""
    fake_llm[LLMPlan] = plan_from_prompt
    state = _state(days=1)
    state["itinerary"] = build_itinerary(state)["itinerary"]
    out = validate_itinerary(state)
    assert all(("이동이 과합니다" in i) or ("영업시간" in i) for i in out["validation_issues"])
    v = out["itinerary"].validation
    assert v.total > 0 and v.passed == v.total - len(out["validation_issues"])


def test_validate_flags_ungrounded_far_and_duplicate_visits() -> None:
    """근거 없는 추천, 과도한 이동, 중복 장소를 각각 잡아낸다."""
    state = _state(days=1)
    sight = next(c for c in state["candidates"] if c.category == "관광지")
    visits = [
        Visit(place_id=sight.id, start="09:00", end="10:30", travel_minutes_from_prev=0, reason="", evidence_review_ids=[]),
        Visit(place_id=sight.id, start="12:00", end="13:30", travel_minutes_from_prev=90, reason="r", evidence_review_ids=["nope"]),
    ]
    state["itinerary"] = _itinerary(visits)
    out = validate_itinerary(state)
    text = "\n".join(out["validation_issues"])
    assert "근거" in text and "이동이 과합니다" in text and "반복" in text and "최소 3곳" in text
    assert out["itinerary"].validation.passed < out["itinerary"].validation.total


def test_validate_flags_outdoor_sights_on_rainy_day() -> None:
    """비 오는 날 야외 관광지가 많으면 지적한다."""
    state = _state(days=1)
    outdoor = [c for c in state["candidates"] if c.category == "관광지" and not c.indoor][:2]
    ev = lambda c: sorted(catalog.review_ids(c.id))[:1]  # noqa: E731
    visits = [
        Visit(place_id=c.id, start=s, end=e, reason="r", evidence_review_ids=ev(c))
        for c, s, e in zip(outdoor, ["09:00", "11:00"], ["10:30", "12:30"])
    ]
    state["itinerary"] = _itinerary(visits, Weather(condition="rain", temp_max=15, temp_min=9))
    assert any("비 예보" in i for i in validate_itinerary(state)["validation_issues"])


def test_validate_flags_opening_hours_conflict() -> None:
    """영업시간이 명확한 장소를 그 시간 밖에 넣으면 지적한다."""
    state = _state(days=1)
    place = next(c for c in state["candidates"] if parse_hours(c.opening_hours))
    open_, close = parse_hours(place.opening_hours)
    late = f"{(close + 60) // 60:02d}:00"
    end = f"{(close + 60) // 60 + 1:02d}:00"
    visit = Visit(place_id=place.id, start=late, end=end, reason="r", evidence_review_ids=sorted(catalog.review_ids(place.id))[:1])
    state["itinerary"] = _itinerary([visit])
    assert any("영업시간" in i for i in validate_itinerary(state)["validation_issues"])


def test_plan_days_passes_weather_and_issues(fake_llm) -> None:
    """계획 프롬프트에 일차별 날씨와 이전 문제점이 들어간다."""
    seen: dict = {}

    def handler(msgs: list) -> LLMPlan:
        seen["system"], seen["user"] = msgs[0].content, msgs[1].content
        return LLMPlan(title="t", days=[])

    fake_llm[LLMPlan] = handler
    state = _state(days=1)
    w = {"2026-11-14": Weather(condition="rain", temp_max=1, temp_min=0)}
    plan_days(state["request"], state["candidates"], state["review_summaries"], w, [1], issues=["문제A"])
    assert "1일차 날씨: rain" in seen["user"] and "문제A" in seen["system"]


def test_validate_flags_day_without_sights() -> None:
    """식사·카페만으로 방문 수를 채운 날(관광지 0곳)을 지적한다."""
    state = _state(days=1)
    pick = lambda cat, n: [c for c in state["candidates"] if c.category == cat][:n]  # noqa: E731
    visits = [
        Visit(place_id=c.id, start=f"{9 + 2 * i:02d}:00", end=f"{10 + 2 * i:02d}:00", reason="r", evidence_review_ids=sorted(catalog.review_ids(c.id))[:1])
        for i, c in enumerate([*pick("음식점", 2), *pick("카페", 1)])
    ]
    state["itinerary"] = _itinerary(visits)
    assert any("관광지가 없습니다" in i for i in validate_itinerary(state)["validation_issues"])
