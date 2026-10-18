"""날씨 확인 노드: 여행 날짜별 날씨를 조회한다. 조회할 수 없으면 날씨 없이 진행한다."""
import logging
from datetime import date, timedelta

from agent.state import PlannerState
from tools.weather import WeatherUnavailable, get_forecast

logger = logging.getLogger(__name__)


def trip_dates(start_date: str | None, days: int | None) -> list[str]:
    """여행 일차별 날짜(YYYY-MM-DD) 목록."""
    if not start_date or not days:
        return []
    start = date.fromisoformat(start_date)
    return [(start + timedelta(days=i)).isoformat() for i in range(days)]


def check_weather(state: PlannerState) -> dict:
    """날짜별 날씨를 weather에 담는다. 실패하면 빈 dict (일정은 날씨 없이 생성)."""
    request = state["request"]
    dates = trip_dates(request.start_date, request.days)
    try:
        weather = get_forecast(dates, request.region)
    except WeatherUnavailable as exc:
        logger.warning("날씨 없이 진행: %s", exc)
        weather = {}
    return {"weather": weather}
