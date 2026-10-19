"""읍면동 단위 날씨: 격자 찾기, 구역별 조회, 일차별 날씨 테스트."""
from agent import catalog
from agent.nodes.check_weather import check_weather
from agent.planning import day_weather
from agent.state import Candidate, TripRequest, Visit, Weather
from tools import grids
from tools.weather import REGION_GRIDS, get_forecast  # noqa: F401


def _w(condition: str) -> Weather:
    return Weather(condition=condition, temp_max=20, temp_min=12)


def test_zone_is_read_from_the_address_first() -> None:
    """주소에 읍면동 이름이 있으면 그 격자를 쓴다 (성산읍 60,37 / 안덕면 49,32)."""
    assert grids.zone_of("제주특별자치도 서귀포시 성산읍 일출로 1", 33.0, 126.0) == "서귀포시 성산읍"
    assert grids.zone_grid("서귀포시 성산읍") == (60, 37)
    assert grids.zone_grid("서귀포시 안덕면") == (49, 32)


def test_zone_falls_back_to_nearest_dong_by_coordinates() -> None:
    """주소에 읍면동이 없으면 좌표가 가장 가까운 읍면동을 쓴다."""
    g = grids.grids()["서귀포시 성산읍"]
    assert grids.zone_of("제주특별자치도 서귀포시 일출로", g.lat + 0.001, g.lng) == "서귀포시 성산읍"


def test_every_place_has_a_weather_zone_with_a_grid() -> None:
    """모든 장소가 격자를 가진 구역에 속하고, 구역의 시(city)가 주소의 시와 같다."""
    for p in catalog.places().values():
        zone = catalog.weather_zone_of(p)
        assert zone and grids.zone_grid(zone), p.name


def test_weather_is_fetched_per_candidate_zone(monkeypatch) -> None:
    """후보 장소가 있는 읍면동만 조회하고, 계획용 날씨는 그중 가장 나쁜 쪽이다."""
    asked: list[str] = []

    def forecast(dates: list[str], region: str) -> dict:
        asked.append(region)
        return {dates[0]: _w("rain" if "성산읍" in region else "sunny")}

    monkeypatch.setattr("agent.nodes.check_weather.get_forecast", forecast)
    places = [p for p in catalog.places().values() if catalog.weather_zone_of(p) in ("서귀포시 성산읍", "제주시 한림읍")]
    cands = [Candidate(**p.model_dump()) for p in places]
    if len({catalog.weather_zone_of(c) for c in cands}) < 2:
        cands = [Candidate(**catalog.places()[i].model_dump()) for i in list(catalog.places())[:12]]
    out = check_weather({"request": TripRequest(start_date="2026-11-14", days=1), "candidates": cands})
    assert sorted(asked) == sorted({catalog.weather_zone_of(c) for c in cands})
    assert set(out["area_weather"]) == set(asked)
    if any("성산읍" in z for z in asked):
        assert out["weather"]["2026-11-14"].condition == "rain"


def test_day_weather_prefers_the_zone_of_the_visits() -> None:
    """그날 방문지의 읍면동 날씨를 우선 쓰고, 없으면 시 단위로 대신한다."""
    place = next(p for p in catalog.places().values())
    zone, city = catalog.weather_zone_of(place), catalog.area_of(place)
    visit = Visit(place_id=place.id, start="09:00", end="10:00", slot="morning", reason="", evidence=[])
    state = {"area_weather": {zone: {"d": _w("rain")}, city: {"d": _w("sunny")}}, "weather": {"d": _w("cloudy")}}
    assert day_weather([visit], "d", state).condition == "rain"
    state["area_weather"].pop(zone)
    assert day_weather([visit], "d", state).condition == "sunny"
    state["area_weather"].pop(city)
    assert day_weather([visit], "d", state).condition == "cloudy"
