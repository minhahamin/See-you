"""기상청 단기예보 API 연동 자리.

TODO: 기상청 API 명세(엔드포인트, 격자 좌표 변환, 응답 필드)를 받은 뒤 구현한다.
명세를 추측해서 구현하지 않는다 (CLAUDE.md 10. 코딩 규칙). 그 전까지 check_weather 노드는
WeatherUnavailable을 받아 날씨 없이 일정을 만든다.
"""
import logging

from agent.state import Weather

logger = logging.getLogger(__name__)


class WeatherUnavailable(RuntimeError):
    """날씨를 가져올 수 없을 때 (미구현, 키 없음, 예보 범위 밖 등)."""


def get_forecast(dates: list[str], region: str) -> dict[str, Weather]:
    """날짜(YYYY-MM-DD)별 날씨를 반환한다. 아직 연동 전이라 항상 WeatherUnavailable."""
    raise WeatherUnavailable("기상청 API 연동 전입니다 (명세와 KMA_API_KEY 필요)")
