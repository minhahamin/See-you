"""제주 읍면동 예보 격자: 장소가 어느 읍면동 격자에 속하는지 찾는다.

격자 목록은 기상청 가이드 엑셀(격자_위경도 2607)에서 뽑은 data/jeju_grids.json이다 (ingest/build_weather_grids.py).
주소에 '제주시 구좌읍'처럼 읍면동 이름이 있으면 그 행을 쓰고, 없으면(도로명만 있는 주소 등) 좌표가 가장 가까운 읍면동 행을 쓴다.
"""
import json
import math
from functools import lru_cache
from typing import NamedTuple

from config import get_settings


class Grid(NamedTuple):
    """읍면동 한 곳의 예보 격자."""

    zone: str  # '서귀포시 성산읍' 같은 구역 이름 (날씨 조회·표시의 키)
    nx: int
    ny: int
    lat: float
    lng: float


@lru_cache(maxsize=1)
def grids() -> dict[str, Grid]:
    """구역 이름 → 격자. 데이터 파일이 없으면 빈 dict."""
    path = get_settings().data_dir / "jeju_grids.json"
    if not path.exists():
        return {}
    rows = json.loads(path.read_text(encoding="utf-8"))
    return {f"{r['city']} {r['name']}": Grid(f"{r['city']} {r['name']}", r["nx"], r["ny"], r["lat"], r["lng"]) for r in rows}


def _km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """두 좌표 사이의 대략적인 거리(km, 평면 근사)."""
    return math.hypot((lat1 - lat2) * 111.0, (lng1 - lng2) * 111.0 * math.cos(math.radians(lat1)))


def zone_of(address: str, lat: float, lng: float) -> str | None:
    """장소의 읍면동 구역 이름. 격자 데이터가 없으면 None."""
    table = grids()
    for zone in table:
        if zone in address:
            return zone
    if not table:
        return None
    return min(table.values(), key=lambda g: _km(lat, lng, g.lat, g.lng)).zone


def zone_grid(zone: str) -> tuple[int, int] | None:
    """구역 이름의 (nx, ny). 모르는 이름이면 None."""
    g = grids().get(zone)
    return (g.nx, g.ny) if g else None
