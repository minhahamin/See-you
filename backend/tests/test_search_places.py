"""search_places, check_weather 단위 테스트."""
from agent.nodes.check_weather import check_weather, trip_dates
from agent.nodes.search_places import build_query, candidate_count, search_places
from agent.state import TripRequest, Weather


def test_build_query_combines_companion_category_and_preferences() -> None:
    """검색 질문은 동행, 분류, 취향을 이어 붙인다."""
    q = build_query(TripRequest(companions="가족", preferences=["바다 전망"]), "카페")
    assert q == "가족과 가기 좋은 카페 바다 전망"


def test_candidate_count_grows_with_days() -> None:
    """후보 수는 일수에 비례해 늘어난다."""
    assert candidate_count("관광지", 3) > candidate_count("관광지", 1)


def test_search_places_returns_candidates_per_category(fake_search) -> None:
    """분류별 후보가 모이고 rank와 특성이 채워진다."""
    out = search_places({"request": TripRequest(days=2, companions="커플", start_date="2026-11-14")})
    cands = out["candidates"]
    assert {c.category for c in cands} == {"관광지", "음식점", "카페", "숙소"}
    sights = [c for c in cands if c.category == "관광지"]
    assert [c.rank for c in sights] == list(range(len(sights)))
    assert all(isinstance(c.indoor, bool) for c in cands)


def test_trip_dates() -> None:
    """여행 일수만큼 연속된 날짜를 만든다."""
    assert trip_dates("2026-11-14", 3) == ["2026-11-14", "2026-11-15", "2026-11-16"]
    assert trip_dates(None, 3) == []


def test_check_weather_degrades_without_forecast() -> None:
    """날씨 연동 전에는 빈 dict로 진행한다."""
    out = check_weather({"request": TripRequest(start_date="2026-11-14", days=2)})
    assert out == {"weather": {}, "area_weather": {}}


def test_check_weather_uses_forecast_when_available(monkeypatch) -> None:
    """예보를 가져오면 그대로 state에 담는다."""
    forecast = {"2026-11-14": Weather(condition="rain", temp_max=15, temp_min=9)}
    monkeypatch.setattr("agent.nodes.check_weather.get_forecast", lambda dates, region: forecast)
    out = check_weather({"request": TripRequest(start_date="2026-11-14", days=1)})
    assert out["weather"]["2026-11-14"].condition == "rain"
