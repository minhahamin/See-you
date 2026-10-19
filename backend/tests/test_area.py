"""구역(제주시/서귀포시) 조건: 파싱 병합, 검색 필터, 검증 규칙 테스트."""
from collections import Counter
from datetime import date

from agent import catalog
from agent.nodes import search_places as search_module
from agent.nodes.build_itinerary import build_itinerary
from agent.nodes.check_weather import check_weather, combine
from agent.nodes.parse_request import ParsedRequest, merge_request
from agent.nodes.search_places import search_places
from agent.nodes.validate_itinerary import run_checks
from agent.planning import LLMPlan, to_candidate
from agent.review_tools import fallback_summary
from agent.state import DayPlan, Itinerary, TripRequest, Visit, Weather
from retrieval.vector import allowed_place_ids
from tests.conftest import plan_from_prompt

TODAY = date(2026, 10, 19)


def _ids(area: str) -> list[str]:
    return catalog.place_ids_in_area(area)


def test_every_place_has_an_area() -> None:
    """모든 장소의 주소에서 구역을 읽을 수 있고, 두 구역이 서로 겹치지 않는다."""
    assert all(catalog.area_of(p) for p in catalog.places().values())
    assert not set(_ids("제주시")) & set(_ids("서귀포시"))
    assert len(_ids("제주시")) + len(_ids("서귀포시")) == len(catalog.places())


def test_allowed_place_ids_filters_by_area_without_index() -> None:
    """area 필터만 있으면 인덱스 없이 주소로 거르고, 없으면 제한하지 않는다."""
    assert set(allowed_place_ids({"area": "서귀포시"})) == set(_ids("서귀포시"))
    assert allowed_place_ids({"author_type": "가족"}) is None


def test_area_is_kept_across_turns_unless_changed() -> None:
    """이전에 정한 구역은 새 발화에 구역이 없어도 유지되고, 새로 말하면 바뀐다."""
    first = merge_request(None, ParsedRequest(area="서귀포시"), TODAY)
    assert first.area == "서귀포시"
    assert merge_request(first, ParsedRequest(days=2), TODAY).area == "서귀포시"
    assert merge_request(first, ParsedRequest(area="제주시"), TODAY).area == "제주시"


def test_search_passes_area_filter(monkeypatch) -> None:
    """요청에 구역이 있으면 모든 분류 검색에 area 필터가 붙는다."""
    seen: list[dict] = []

    def fake(query: str, n: int = 30, filters: dict | None = None) -> list[dict]:
        seen.append(filters or {})
        return []

    monkeypatch.setattr(search_module, "hybrid_search", fake)
    search_places({"request": TripRequest(days=1, companions="커플", area="서귀포시")})
    assert seen and all(f.get("area") == "서귀포시" for f in seen)
    seen.clear()
    search_places({"request": TripRequest(days=1, companions="커플")})
    assert all("area" not in f for f in seen)


def test_validation_flags_places_outside_requested_area() -> None:
    """요청한 구역 밖의 장소는 검증에서 실패하고, 구역을 지정하지 않으면 검사하지 않는다."""
    inside, outside = _ids("서귀포시")[0], _ids("제주시")[0]

    def itinerary(place_id: str) -> Itinerary:
        visit = Visit(place_id=place_id, start="10:00", end="11:00", reason="r")
        return Itinerary(title="t", region="제주", companions="커플", days=[DayPlan(day=1, date="2026-11-14", visits=[visit])])

    def failures(place_id: str, area: str | None) -> list[str]:
        summaries = {place_id: fallback_summary(to_candidate(place_id))}  # 실제 흐름처럼 방문 장소의 요약을 채운다
        checks = run_checks(itinerary(place_id), TripRequest(days=1, area=area), summaries)
        return [c.message for c in checks if not c.ok and "지역" in c.message]

    assert failures(outside, "서귀포시")
    assert not failures(inside, "서귀포시")
    assert not failures(outside, None)


def _rain(temp: float = 15) -> Weather:
    return Weather(condition="rain", temp_max=temp, temp_min=temp - 5)


def _sunny(temp: float = 20) -> Weather:
    return Weather(condition="sunny", temp_max=temp, temp_min=temp - 5)


def test_weather_is_fetched_for_both_areas_unless_one_is_requested(monkeypatch) -> None:
    """구역을 지정하지 않으면 두 구역 날씨를 모두 조회하고, 지정하면 그 구역만 조회한다."""
    asked: list[str] = []

    def forecast(dates: list[str], region: str) -> dict:
        asked.append(region)
        return {dates[0]: _rain() if region == "서귀포시" else _sunny()}

    monkeypatch.setattr("agent.nodes.check_weather.get_forecast", forecast)
    out = check_weather({"request": TripRequest(start_date="2026-11-14", days=1)})
    assert asked == ["제주시", "서귀포시"]
    assert out["weather"]["2026-11-14"].condition == "rain"  # 계획용은 더 나쁜 쪽
    assert out["area_weather"]["제주시"]["2026-11-14"].condition == "sunny"

    asked.clear()
    check_weather({"request": TripRequest(start_date="2026-11-14", days=1, area="제주시")})
    assert asked == ["제주시"]


def test_combine_takes_worse_condition_and_widest_temperatures() -> None:
    """합친 날씨는 더 나쁜 상태를 따르고 기온은 가장 넓은 범위를 쓴다."""
    merged = combine([{"d": _sunny(20)}, {"d": _rain(15)}])["d"]
    assert (merged.condition, merged.temp_max, merged.temp_min) == ("rain", 20, 10)


def test_day_weather_follows_the_area_where_the_day_is_spent(fake_llm) -> None:
    """각 일차의 날씨는 그날 방문지가 많은 구역의 날씨이고, 구역별 날씨가 없으면 계획용 날씨로 대신한다."""
    fake_llm[LLMPlan] = plan_from_prompt
    cands = [to_candidate(pid, i) for i, pid in enumerate(sorted(catalog.places()))]
    state = {
        "request": TripRequest(start_date="2026-11-14", days=1, companions="커플"),
        "candidates": cands,
        "review_summaries": {c.id: fallback_summary(c) for c in cands},
        "weather": {"2026-11-14": _rain()},
        "area_weather": {"제주시": {"2026-11-14": _sunny()}, "서귀포시": {"2026-11-14": _rain()}},
    }
    day = build_itinerary(state)["itinerary"].days[0]
    areas = Counter(catalog.area_of(catalog.places()[v.place_id]) for v in day.visits)
    expected = state["area_weather"][areas.most_common(1)[0][0]]["2026-11-14"]
    assert day.weather == expected

    del state["area_weather"]
    assert build_itinerary(state)["itinerary"].days[0].weather == _rain()


def test_partial_edits_refresh_day_weather(fake_llm, fake_search) -> None:
    """방문을 다른 일차로 옮기면 두 일차의 날씨가 지금 방문지의 구역 기준으로 다시 정해진다."""
    from agent.nodes.apply_feedback import apply_feedback
    from tests.test_graph import _full_state

    fake_llm[LLMPlan] = plan_from_prompt
    state = _full_state()
    state["area_weather"] = {"제주시": {d.date: _sunny() for d in state["itinerary"].days}, "서귀포시": {d.date: _rain() for d in state["itinerary"].days}}
    state["weather"] = {}
    name = catalog.places()[state["itinerary"].days[0].visits[0].place_id].name
    state["feedback"] = f"1일차 1번째 방문({name})을 2일차 18:00로 옮겨줘"

    out = apply_feedback(state)["itinerary"]
    for day in out.days:
        areas = Counter(catalog.area_of(catalog.places()[v.place_id]) for v in day.visits)
        assert day.weather == state["area_weather"][areas.most_common(1)[0][0]][day.date]
