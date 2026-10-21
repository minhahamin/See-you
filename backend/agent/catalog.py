"""생성된 장소·특성·후기 데이터에 대한 읽기 전용 조회 (프로세스당 1회 로드)."""
from collections import defaultdict
from functools import lru_cache

from ingest.build_index import dedupe_reviews, load_json
from models import Place, PlaceTraits, Review
from tools.grids import zone_of

POSITIVE_RATING = 4  # 추천 근거로 내세울 수 있는 후기의 최저 별점


@lru_cache(maxsize=1)
def places() -> dict[str, Place]:
    """place_id → 장소."""
    return {p["id"]: Place(**p) for p in load_json("places.json")}


@lru_cache(maxsize=1)
def traits() -> dict[str, PlaceTraits]:
    """place_id → 숨은 특성."""
    return {t["place_id"]: PlaceTraits(**t) for t in load_json("place_traits.json")}


@lru_cache(maxsize=1)
def reviews_by_place() -> dict[str, list[Review]]:
    """place_id → 후기 목록 (인덱싱과 같은 기준으로 중복 제거)."""
    grouped: dict[str, list[Review]] = defaultdict(list)
    for r in dedupe_reviews([Review(**r) for r in load_json("reviews.json")]):
        grouped[r.place_id].append(r)
    return dict(grouped)


def area_of(place: Place) -> str | None:
    """장소 주소에서 구역(제주시/서귀포시)을 구한다. 둘 다 아니면 None."""
    return next((a for a in ("서귀포시", "제주시") if a in place.address), None)


def weather_zone_of(place: Place) -> str | None:
    """장소의 날씨 조회 구역(읍면동 격자 단위, 예: '서귀포시 성산읍')."""
    return zone_of(place.address, place.lat, place.lng)


def place_ids_in_area(area: str) -> list[str]:
    """해당 구역에 있는 장소 id 목록."""
    return [p.id for p in places().values() if area_of(p) == area]


def review_ids(place_id: str) -> set[str]:
    """장소의 후기 id 집합."""
    return {r.review_id for r in reviews_by_place().get(place_id, [])}


def positive_first(place_id: str, ids: list[str]) -> list[str]:
    """추천 근거로 보여줄 후기 id를 별점 높은 순으로 정렬한다. 4점 이상이 있으면 그것만 남긴다."""
    ratings = {r.review_id: r.rating for r in reviews_by_place().get(place_id, [])}
    ordered = sorted(ids, key=lambda i: -ratings.get(i, 0))
    return [i for i in ordered if ratings.get(i, 0) >= POSITIVE_RATING] or ordered
