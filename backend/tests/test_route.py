"""tools/route.py 단위 테스트."""
from tools.route import haversine_km, order_nearest, travel_minutes

SEOUL = (37.5665, 126.9780)
BUSAN = (35.1796, 129.0756)


def test_haversine_known_distance() -> None:
    """서울-부산 직선거리는 약 325km."""
    assert 320 < haversine_km(*SEOUL, *BUSAN) < 330


def test_travel_minutes_is_rounded_and_has_minimum() -> None:
    """이동시간은 5분 단위이고 같은 위치여도 최소 5분."""
    assert travel_minutes(SEOUL, SEOUL) == 5
    assert travel_minutes((33.45, 126.94), (33.42, 126.93)) % 5 == 0


def test_order_nearest_prefers_close_items() -> None:
    """최근접 이웃 정렬은 가까운 점을 먼저 방문한다."""
    pts = {"a": (0.0, 0.0), "far": (0.0, 5.0), "near": (0.0, 0.1)}
    out = order_nearest(["a", "far", "near"], lambda k: pts[k])
    assert out == ["a", "near", "far"]


def test_order_nearest_with_start_and_empty() -> None:
    """시작 좌표를 주면 거기서 가장 가까운 항목부터 시작한다."""
    pts = {"x": (0.0, 3.0), "y": (0.0, 1.0)}
    assert order_nearest(["x", "y"], lambda k: pts[k], start=(0.0, 0.0)) == ["y", "x"]
    assert order_nearest([], lambda k: (0.0, 0.0)) == []
