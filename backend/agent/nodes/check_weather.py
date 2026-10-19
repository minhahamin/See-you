"""날씨 확인 노드: 여행 날짜별 날씨를 구역별로 조회한다. 조회할 수 없으면 날씨 없이 진행한다."""
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

from agent import catalog
from agent.state import PlannerState, Weather
from tools.weather import WeatherUnavailable, get_forecast

logger = logging.getLogger(__name__)

ALL_AREAS = ("제주시", "서귀포시")
MAX_PARALLEL = 6
SEVERITY = {"sunny": 0, "cloudy": 1, "rain": 2}


def trip_dates(start_date: str | None, days: int | None) -> list[str]:
    """여행 일차별 날짜(YYYY-MM-DD) 목록."""
    if not start_date or not days:
        return []
    start = date.fromisoformat(start_date)
    return [(start + timedelta(days=i)).isoformat() for i in range(days)]


def combine(forecasts: list[dict[str, Weather]]) -> dict[str, Weather]:
    """여러 구역의 날씨를 날짜별로 합친다. 어느 한 곳이라도 비가 오면 비로 보는 보수적 기준이다."""
    combined: dict[str, Weather] = {}
    for forecast in forecasts:
        for day, w in forecast.items():
            old = combined.get(day)
            if old is None:
                combined[day] = w
                continue
            worse = w if SEVERITY[w.condition] > SEVERITY[old.condition] else old
            combined[day] = Weather(condition=worse.condition, temp_max=max(old.temp_max, w.temp_max), temp_min=min(old.temp_min, w.temp_min))
    return combined


def candidate_zones(state: PlannerState) -> list[str]:
    """후보 장소가 있는 읍면동 구역들 (이름순). 후보가 없거나 격자 데이터가 없으면 빈 목록."""
    zones = {catalog.weather_zone_of(c) for c in state.get("candidates", [])}
    return sorted(z for z in zones if z)


def check_weather(state: PlannerState) -> dict:
    """읍면동 구역별 날씨를 area_weather에, 일정 계획에 쓸 합친 날씨를 weather에 담는다. 실패한 구역은 건너뛴다."""
    request = state["request"]
    dates = trip_dates(request.start_date, request.days)
    areas = candidate_zones(state) or ([request.area] if request.area else list(ALL_AREAS))
    def fetch(area: str) -> dict[str, Weather] | None:
        """구역 하나의 예보. 조회할 수 없으면 None."""
        try:
            return get_forecast(dates, area)
        except WeatherUnavailable as exc:
            logger.warning("%s 날씨 없이 진행: %s", area, exc)
            return None

    with ThreadPoolExecutor(max_workers=MAX_PARALLEL) as pool:  # 구역이 많아도 응답이 늘어나지 않게 병렬로 조회한다
        results = list(pool.map(fetch, areas))
    by_area = {a: f for a, f in zip(areas, results) if f}
    return {"weather": combine(list(by_area.values())), "area_weather": by_area}
