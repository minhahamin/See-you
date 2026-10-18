"""좌표 기반 이동 시간 추정과 동선 정렬. 실제 도로 경로가 아닌 근사치다."""
from math import asin, cos, radians, sin, sqrt
from typing import Callable, TypeVar

T = TypeVar("T")

EARTH_RADIUS_KM = 6371.0
ROAD_FACTOR = 1.3  # 직선거리 대비 도로 거리 보정 (가정값)
AVG_SPEED_KMH = 40.0  # 평균 주행 속도 (가정값)
OVERHEAD_MIN = 5  # 주차·승하차 시간 (가정값)
ROUND_TO_MIN = 5


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """두 좌표 사이의 직선거리(km)."""
    dlat, dlng = radians(lat2 - lat1), radians(lng2 - lng1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    return 2 * EARTH_RADIUS_KM * asin(sqrt(a))


def travel_minutes(a: tuple[float, float], b: tuple[float, float]) -> int:
    """두 좌표(lat, lng) 사이의 자동차 이동 시간(분)을 5분 단위로 추정한다."""
    km = haversine_km(a[0], a[1], b[0], b[1])
    minutes = km * ROAD_FACTOR / AVG_SPEED_KMH * 60 + OVERHEAD_MIN
    return max(ROUND_TO_MIN, int(round(minutes / ROUND_TO_MIN)) * ROUND_TO_MIN)


def order_nearest(
    items: list[T], coord: Callable[[T], tuple[float, float]], start: tuple[float, float] | None = None
) -> list[T]:
    """최근접 이웃 방식으로 이동거리가 짧은 순서로 정렬한다. start가 없으면 첫 항목에서 시작한다."""
    remaining = list(items)
    if not remaining:
        return []
    ordered: list[T] = []
    current = start
    if current is None:
        first = remaining.pop(0)
        ordered.append(first)
        current = coord(first)
    while remaining:
        nxt = min(remaining, key=lambda it: haversine_km(*current, *coord(it)))  # type: ignore[misc]
        remaining.remove(nxt)
        ordered.append(nxt)
        current = coord(nxt)
    return ordered
