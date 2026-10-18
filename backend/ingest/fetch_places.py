"""TourAPI(KorService2)에서 제주 장소를 가져와 data/places.json을 만든다."""
import json
import logging
import re
import time
from typing import Any
from urllib.parse import unquote

import httpx

from config import get_settings, setup_logging
from models import Category, Place

logger = logging.getLogger(__name__)

BASE_URL = "https://apis.data.go.kr/B551011/KorService2/"
JEJU_REGION_CODE = "50"  # ldongCode2 조회 결과: 제주특별자치도
CAFE_CLS1, CAFE_CLS2 = "FD", "FD05"  # lclsSystmCode2 조회 결과: 음식 > 카페/찻집

# 카테고리별 (contentTypeId, 목표 개수). 카페는 음식점(39) 중 분류체계 FD05.
PLAN: dict[Category, tuple[str, int]] = {
    "관광지": ("12", 12),
    "음식점": ("39", 8),
    "카페": ("39", 5),
    "숙소": ("32", 5),
}
# detailIntro2에서 영업시간으로 쓰는 필드 (타입별로 다름). 숙박은 해당 필드가 없어 None.
OPEN_FIELD: dict[str, str] = {"12": "usetime", "39": "opentimefood"}

MIN_OVERVIEW_LEN = 40
CANDIDATES_PER_CATEGORY = 60
REQUEST_INTERVAL_SEC = 0.2


def _clean(text: str | None) -> str:
    """HTML 태그와 개행을 정리한 문자열을 반환한다."""
    if not text:
        return ""
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", text).strip()


class TourApiClient:
    """TourAPI 호출 클라이언트. 서비스키는 로그에 남기지 않는다."""

    def __init__(self) -> None:
        """설정에서 서비스키를 읽고 HTTP 클라이언트를 준비한다."""
        key = get_settings().tour_api_key
        if not key:
            raise ValueError("TOUR_API_KEY가 비어 있습니다. .env를 확인하세요.")
        # 인코딩된 키가 들어와도 이중 인코딩되지 않도록 디코딩해서 params로 넘긴다.
        self._key = unquote(key)
        self._http = httpx.Client(timeout=30)

    def call(self, operation: str, **params: Any) -> list[dict[str, Any]]:
        """오퍼레이션을 호출해 item 리스트를 반환한다. 실패 시 예외를 던진다."""
        query = {
            "serviceKey": self._key,
            "MobileOS": "ETC",
            "MobileApp": "TravelPlanner",
            "_type": "json",
            **params,
        }
        time.sleep(REQUEST_INTERVAL_SEC)
        try:
            resp = self._http.get(BASE_URL + operation, params=query)
            resp.raise_for_status()
            body = resp.json()["response"]
        except Exception as exc:  # URL(키 포함)이 로그에 남지 않도록 타입만 기록
            raise RuntimeError(f"{operation} 호출 실패: {type(exc).__name__}") from None
        header = body["header"]
        if header["resultCode"] != "0000":
            raise RuntimeError(f"{operation} 오류: {header['resultCode']} {header['resultMsg']}")
        items = body["body"].get("items")
        if not items:
            return []
        return items["item"]


def fetch_candidates(client: TourApiClient, category: Category) -> list[dict[str, Any]]:
    """카테고리의 후보 목록(지역기반 조회)을 가져온다. 대표 이미지가 있는 것을 우선한다."""
    content_type, _ = PLAN[category]
    params: dict[str, Any] = {
        "numOfRows": CANDIDATES_PER_CATEGORY,
        "pageNo": 1,
        "arrange": "Q",  # 수정일순, 대표 이미지가 있는 것만
        "contentTypeId": content_type,
        "lDongRegnCd": JEJU_REGION_CODE,
    }
    if category == "카페":
        params.update(lclsSystm1=CAFE_CLS1, lclsSystm2=CAFE_CLS2)
    items = client.call("areaBasedList2", **params)
    if category == "음식점":  # 카페는 별도 카테고리이므로 제외
        items = [it for it in items if it.get("lclsSystm2") != CAFE_CLS2]
    return items


def build_place(
    client: TourApiClient, category: Category, item: dict[str, Any]
) -> Place | None:
    """목록 항목에 개요·영업시간을 붙여 Place로 만든다. 소개문이 부족하면 None."""
    content_id = item["contentid"]
    content_type = item["contenttypeid"]
    common = client.call("detailCommon2", contentId=content_id)
    overview = _clean(common[0].get("overview")) if common else ""
    if len(overview) < MIN_OVERVIEW_LEN:
        return None

    opening_hours: str | None = None
    field = OPEN_FIELD.get(content_type)
    if field:
        intro = client.call("detailIntro2", contentId=content_id, contentTypeId=content_type)
        opening_hours = _clean(intro[0].get(field)) or None if intro else None

    return Place(
        id=content_id,
        name=item["title"],
        category=category,
        address=" ".join(filter(None, [item.get("addr1"), item.get("addr2")])),
        lat=float(item["mapy"]),
        lng=float(item["mapx"]),
        description=overview,
        opening_hours=opening_hours,
        image_url=item.get("firstimage") or None,
    )


def fetch_places() -> list[Place]:
    """PLAN에 따라 카테고리별로 장소를 수집한다."""
    client = TourApiClient()
    raw_dump: dict[str, list[dict[str, Any]]] = {}
    places: list[Place] = []
    for category, (_, target) in PLAN.items():
        candidates = fetch_candidates(client, category)
        raw_dump[category] = candidates
        picked = 0
        for item in candidates:
            if picked >= target:
                break
            if not item.get("mapx") or not item.get("mapy"):
                continue
            place = build_place(client, category, item)
            if place:
                places.append(place)
                picked += 1
        logger.info("%s: 후보 %d개 중 %d/%d개 선정", category, len(candidates), picked, target)
    settings = get_settings()
    raw_dir = settings.data_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / "places_raw.json").write_text(
        json.dumps(raw_dump, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return places


def main() -> None:
    """장소를 수집해 data/places.json으로 저장한다."""
    setup_logging()
    places = fetch_places()
    out = get_settings().data_dir / "places.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps([p.model_dump() for p in places], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("총 %d곳 저장: %s", len(places), out)


if __name__ == "__main__":
    main()
