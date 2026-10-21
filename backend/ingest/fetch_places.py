"""TourAPI(KorService2)에서 제주 장소를 가져와 data/places.json을 만든다."""
import argparse
import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote

import httpx

from config import get_settings, setup_logging
from models import Category, Place

logger = logging.getLogger(__name__)

BASE_URL = "https://apis.data.go.kr/B551011/KorService2/"
JEJU_REGION_CODE = "50"  # ldongCode2 조회 결과: 제주특별자치도
CAFE_CLS1, CAFE_CLS2 = "FD", "FD05"  # lclsSystmCode2 조회 결과: 음식 > 카페/찻집

@dataclass(frozen=True)
class PlanItem:
    """수집 계획 한 줄: 어떤 콘텐츠타입에서 몇 곳을 어떤 분류로 담을지."""

    label: str
    category: Category
    content_type: str
    target: int
    title_keywords: tuple[str, ...] = ()  # 비어 있지 않으면 제목에 이 중 하나가 들어간 곳만 고른다


# 카페는 음식점(39) 중 분류체계 FD05. 문화시설(14)은 비 오는 날 갈 실내 관광지를 늘리려고 추가했고,
# 박물관·미술관·뮤지엄·아쿠아리움 계열만 '관광지' 분류로 담는다 (도서관·공연장 등은 제외).
PLAN: list[PlanItem] = [
    PlanItem("관광지", "관광지", "12", 12),
    PlanItem("음식점", "음식점", "39", 8),
    PlanItem("카페", "카페", "39", 5),
    PlanItem("숙소", "숙소", "32", 5),
    PlanItem("문화시설", "관광지", "14", 10, ("박물관", "미술관", "뮤지엄", "아쿠아")),
]
INDOOR_CULTURE_LABEL = "문화시설"
# detailIntro2에서 영업시간으로 쓰는 필드 (타입별로 다름). 숙박은 해당 필드가 없어 None.
OPEN_FIELD: dict[str, str] = {"12": "usetime", "14": "usetimeculture", "39": "opentimefood"}

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


def fetch_candidates(client: TourApiClient, item: PlanItem) -> list[dict[str, Any]]:
    """계획 한 줄의 후보 목록(지역기반 조회)을 가져온다. 대표 이미지가 있는 것을 우선한다."""
    params: dict[str, Any] = {
        "numOfRows": CANDIDATES_PER_CATEGORY,
        "pageNo": 1,
        "arrange": "Q",  # 수정일순, 대표 이미지가 있는 것만
        "contentTypeId": item.content_type,
        "lDongRegnCd": JEJU_REGION_CODE,
    }
    if item.category == "카페":
        params.update(lclsSystm1=CAFE_CLS1, lclsSystm2=CAFE_CLS2)
    items = client.call("areaBasedList2", **params)
    if item.category == "음식점":  # 카페는 별도 카테고리이므로 제외
        items = [it for it in items if it.get("lclsSystm2") != CAFE_CLS2]
    if item.title_keywords:
        items = [it for it in items if any(k in it["title"] for k in item.title_keywords)]
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


def fetch_places(
    only: set[str] | None = None,
    skip_ids: set[str] = frozenset(),  # type: ignore[assignment]
    add: int | None = None,
    area: str | None = None,
) -> list[Place]:
    """PLAN에 따라 장소를 수집한다. only로 계획 이름을 제한하고, skip_ids에 있는 장소는 건너뛴다.

    add가 있으면 계획의 목표 개수 대신 이 수만큼 새로 담는다 (이미 가진 장소 위에 추가할 때 쓴다).
    area가 있으면(예: 서귀포시) 주소에 그 구역이 들어 있는 후보만 담는다.
    """
    client = TourApiClient()
    raw_dump: dict[str, list[dict[str, Any]]] = {}
    places: list[Place] = []
    for plan in PLAN:
        if only and plan.label not in only:
            continue
        candidates = fetch_candidates(client, plan)
        if area:
            candidates = [it for it in candidates if area in (it.get("addr1") or "")]
        raw_dump[plan.label] = candidates
        target = add if add is not None else plan.target
        picked = 0
        for item in candidates:
            if picked >= target:
                break
            if item["contentid"] in skip_ids or not item.get("mapx") or not item.get("mapy"):
                continue
            place = build_place(client, plan.category, item)
            if place:
                places.append(place)
                picked += 1
        logger.info("%s: 후보 %d개 중 %d/%d개 선정", plan.label, len(candidates), picked, target)
    raw_dir = get_settings().data_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    suffix = ("_" + "_".join(sorted(only)) if only else "") + (f"_{area}" if area else "")
    (raw_dir / f"places_raw{suffix}.json").write_text(json.dumps(raw_dump, ensure_ascii=False, indent=2), encoding="utf-8")
    return places


def main() -> None:
    """장소를 수집해 data/places.json으로 저장한다.

    기본은 전체 수집. `--only 문화시설`처럼 계획 이름을 주면 그 계획만 수집해 기존 파일에 덧붙이고,
    이미 있는 장소(id)는 그대로 둔다 (기존 특성·후기와 id가 어긋나지 않게 한다).
    """
    setup_logging()
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", nargs="+", choices=[p.label for p in PLAN], help="이 계획만 수집해 기존 파일에 추가")
    parser.add_argument("--add", type=int, help="--only와 함께: 계획의 목표 대신 이 수만큼 새 장소를 추가")
    parser.add_argument("--area", choices=["제주시", "서귀포시"], help="주소에 이 구역이 들어 있는 장소만 수집")
    args = parser.parse_args()

    out = get_settings().data_dir / "places.json"
    existing: list[Place] = []
    if args.only and out.exists():
        existing = [Place(**p) for p in json.loads(out.read_text(encoding="utf-8"))]
    fetched = fetch_places(set(args.only) if args.only else None, {p.id for p in existing}, args.add, args.area)
    places = [*existing, *fetched]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps([p.model_dump() for p in places], ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("총 %d곳 저장 (이번에 추가 %d곳): %s", len(places), len(fetched), out)


if __name__ == "__main__":
    main()
