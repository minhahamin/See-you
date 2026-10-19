"""구역(제주시/서귀포시) 조건: 파싱 병합, 검색 필터, 검증 규칙 테스트."""
from datetime import date

from agent import catalog
from agent.nodes import search_places as search_module
from agent.nodes.parse_request import ParsedRequest, merge_request
from agent.nodes.search_places import search_places
from agent.nodes.validate_itinerary import run_checks
from agent.planning import to_candidate
from agent.review_tools import fallback_summary
from agent.state import DayPlan, Itinerary, TripRequest, Visit
from retrieval.vector import allowed_place_ids

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
